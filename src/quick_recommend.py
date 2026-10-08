"""Fresh, bounded MusicBrainz recommendations with reproducible artist sampling."""

import argparse
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import fcntl
import json
import math
import multiprocessing
from pathlib import Path
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from .build_graph import ROOT, load_rules
from .collect_song_graph import balanced_frontier
from .credits import SONGWRITING_IDS, extract_credits
from .fetch_musicbrainz import API, FetchError, digest, json_bytes, mbid, utc_now
from .library_job import atomic_json, read_json
from .match_recordings import MATCH_INCLUDES, load_input, normalize
from .seed_matching import (POLICY, choose_candidate, compatible, core_response_valid,
                            credit_diagnostics, identity_checks, main_artist_key, matching_allocation,
                            seed_query, title_keys, version_notice)
from .recommend_songs import load_weights, recommendation_report, write_song_review
from .song_policy import build_registry, candidate_eligibility, registry_digest
from .source_songs import assignment_evidence, source_song_groups


BROWSE_INCLUDES = "artist-credits+artist-rels+work-rels+work-level-rels"
PACING_DIRECTORY = ROOT / "data/cache/quick_musicbrainz_gate"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # An automatic redirect would send an uncharged extra HTTP attempt.
        return None


def open_fresh(request, *, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


class CollectionStopped(FetchError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def sample_likes(tracks, *, random_seed, seed_count=8):
    """Count distinct metadata rows, then draw weighted artists without replacement."""
    if type(random_seed) is not int or type(seed_count) is not int or seed_count < 1:
        raise ValueError("random_seed must be an integer and seed_count must be positive")
    groups = defaultdict(dict)
    for track in sorted(tracks, key=lambda t: t["line_number"]):
        key = tuple(normalize(track.get(field, "")) for field in
                    ("artist_text", "song_text", "album_text", "duration_text"))
        if track.get("recording_mbid"):
            mbid(track["recording_mbid"])
        existing = groups[key[0]].get(key)
        if existing:
            ids = {t.get("recording_mbid") for t in (existing, track) if t.get("recording_mbid")}
            if len(ids) > 1:
                raise ValueError("Identical favorite metadata has conflicting recording_mbid values")
            existing["source_lines"].append(track["line_number"])
            if ids:
                existing["recording_mbid"] = next(iter(ids))
        else:
            groups[key[0]][key] = track.copy() | {"source_lines": [track["line_number"]]}
    counts = {name: len(songs) for name, songs in groups.items()}
    weights = {name: 1 if n == 1 else 2 if n <= 10 else 3 for name, n in counts.items()}
    rng, remaining, chosen = random.Random(random_seed), sorted(groups), []
    for _ in range(min(seed_count, len(remaining))):
        draw = rng.randrange(sum(weights[name] for name in remaining))
        for name in remaining:
            draw -= weights[name]
            if draw < 0:
                break
        remaining.remove(name)
        songs = groups[name]
        track = songs[rng.choice(sorted(songs))]
        chosen.append({"artist_key": name, "liked_song_count": counts[name],
                       "sampling_weight": weights[name], "source_row": track})
    return chosen, {"artist_groups": len(groups), "distinct_liked_songs": sum(counts.values()),
                    "duplicate_rows": len(tracks) - sum(counts.values()),
                    "weight_tiers": {str(weight): count for weight, count in
                                     sorted(Counter(weights.values()).items())}}


class FreshClient:
    """Per-run response reuse; a separate shared gate persists pacing, never responses."""

    def __init__(self, directory, *, contact, max_requests, deadline, pacing_directory=PACING_DIRECTORY,
                 opener=open_fresh, clock=time.time, monotonic=time.monotonic, sleep=time.sleep):
        if not contact or not re.fullmatch(r"(?:[^\s@()]+@[^\s@()]+\.[^\s@()]+|https?://[^\s()]+)", contact):
            raise ValueError("Live collection needs a contact email or URL")
        self.directory, self.pacing_directory = Path(directory), Path(pacing_directory)
        self.deadline, self.max_requests = deadline, max_requests
        self.opener, self.clock, self.monotonic, self.sleep = opener, clock, monotonic, sleep
        self.contact = contact
        self.request_context = {}
        self.memo, self.events, self.last_source = {}, [], None
        self.stats = {"attempts": 0, "by_operation": {}, "within_run_reuses": 0,
                      "pacing_seconds": 0.0, "transport_seconds": 0.0}
        (self.directory / "responses").mkdir(parents=True, exist_ok=True)
        self.pacing_directory.mkdir(parents=True, exist_ok=True)
        self.save_stats()

    def remaining(self):
        value = self.deadline - self.monotonic()
        if value <= 0:
            raise CollectionStopped("deadline")
        return value

    def save_stats(self):
        atomic_json(self.directory / "requests.json", self.stats | {"events": self.events})

    @contextmanager
    def gate_lock(self):
        with (self.pacing_directory / "gate.lock").open("a") as lock:
            while True:
                self.remaining()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self.sleep(min(0.01, self.remaining()))
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def begin_attempt(self, operation, url):
        if self.stats["attempts"] >= self.max_requests:
            raise CollectionStopped("request_budget")
        marker = self.pacing_directory / "gate.json"
        paced_at = self.monotonic()
        while True:
            with self.gate_lock():
                gate = read_json(marker) if marker.exists() else {}
                wait = max(gate.get("last_sent_at", 0) + 1.1, gate.get("backoff_until", 0)) - self.clock()
                if wait <= 0:
                    self.remaining()
                    self.stats["pacing_seconds"] += self.monotonic() - paced_at
                    self.stats["attempts"] += 1
                    operations = self.stats["by_operation"]
                    operations[operation] = operations.get(operation, 0) + 1
                    self.events.append({"query": url, "operation": operation, "outcome": "in_progress",
                                        "started_at": self.clock(), **self.request_context})
                    # Charge and persist before transport, including a subsequently killed request.
                    self.save_stats()
                    gate["last_sent_at"] = self.clock()
                    atomic_json(marker, gate)
                    return
            if wait >= self.remaining():
                raise CollectionStopped("deadline")
            self.sleep(min(wait, 0.1))

    def honor_backoff(self, headers):
        retry = headers.get("Retry-After", "0") if headers else "0"
        try:
            delay = float(retry)
        except ValueError:
            try:
                delay = parsedate_to_datetime(retry).timestamp() - self.clock()
            except (TypeError, ValueError, OverflowError):
                delay = 0
        if math.isfinite(delay) and delay > 0:
            with self.gate_lock():
                marker = self.pacing_directory / "gate.json"
                gate = read_json(marker) if marker.exists() else {}
                gate["backoff_until"] = max(gate.get("backoff_until", 0), self.clock() + delay)
                atomic_json(marker, gate)

    def get(self, endpoint, *, operation, **params):
        self.remaining()
        url = API + endpoint + "?" + urlencode(sorted({"fmt": "json", **params}.items()))
        if url in self.memo:
            self.stats["within_run_reuses"] += 1
            self.save_stats()
            body, source, error = self.memo[url]
            self.last_source = source
            if error:
                raise FetchError(error)
            return body
        request = Request(url, headers={"User-Agent": f"music-credit-recommender/0.3.0 ({self.contact})",
                                        "Accept": "application/json"})
        self.begin_attempt(operation, url)
        started, raw, body, error, status = self.monotonic(), b"", None, None, None
        try:
            with self.opener(request, timeout=min(5.0, self.remaining())) as response:
                status = response.status
                raw = response.read(16 * 1024 * 1024 + 1)
            if status != 200 or len(raw) > 16 * 1024 * 1024:
                raise ValueError("Unexpected HTTP status or oversized response")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
        except HTTPError as failure:
            status, error = failure.code, f"HTTP {failure.code}"
            self.honor_backoff(failure.headers)
        except (URLError, OSError, ValueError) as failure:
            error = f"{type(failure).__name__}: {failure}"
        elapsed = self.monotonic() - started
        self.stats["transport_seconds"] += elapsed
        relative = f"responses/{digest(url.encode())}.json"
        source = {"query": url, "retrieved_at": utc_now(), "response_sha256": digest(raw),
                  "response_file": relative}
        atomic_json(self.directory / relative, source | {"status": status,
                    "response_text": raw.decode("utf-8", errors="replace"), "error": error})
        self.events[-1].update(source | {"status": status, "elapsed_seconds": elapsed,
                                       "outcome": "failed" if error else "completed", "error": error})
        self.save_stats()
        self.memo[url] = body, source, error
        self.last_source = source
        if error:
            raise FetchError(error)
        return body


def valid_record(record, *, releases=False):
    if (not core_response_valid(record) or not record.get("title")
            or not isinstance(record.get("artist-credit"), list) or not record["artist-credit"]
            or not isinstance(record.get("relations"), list)
            or (releases and not isinstance(record.get("releases"), list))):
        return False
    for relation in record["relations"]:
        if not isinstance(relation, dict):
            return False
        if relation.get("target-type") == "work":
            work = relation.get("work")
            if not isinstance(work, dict) or not isinstance(work.get("relations"), list):
                return False
    try:
        mbid(record["id"])
        extract_credits(record)
        return True
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def plausible(track, record, rules=None):
    """Fast-mode compatibility; historical matching helpers remain unchanged."""
    return compatible(track, record)


def choose_seed_candidate(track, candidates, rules=None):
    return choose_candidate(track, candidates)


class MatchingStageEnded(Exception):
    """End matching without ending collection or spending discovery's reserve."""


class QuickCollection:
    def __init__(self, directory, tracks, metadata, sampled, config, client, state):
        self.directory, self.tracks, self.metadata = Path(directory), tracks, metadata
        self.sampled, self.config, self.client, self.state = sampled, config, client, state
        self.known_favorites = {t["recording_mbid"] for t in tracks if t.get("recording_mbid")}
        self.seen, self.queued = set(), set()

    def save(self):
        atomic_json(self.directory / "checkpoint.json", self.state)

    def fetch(self, endpoint, operation, **params):
        try:
            return self.client.get(endpoint, operation=operation, **params)
        except CollectionStopped:
            raise
        except FetchError as error:
            self.state["failures"].append({"operation": operation, "endpoint": endpoint, "error": str(error)})
            return None

    def freeze(self, record):
        rid = record["id"]
        self.state["records"][rid] = record
        self.state["sources"][rid] = self.client.last_source | {
            "recording_id": rid, "snapshot_file": f"recordings/{rid}.json",
            "sha256": digest(json_bytes(record)), "source_url": f"https://musicbrainz.org/recording/{rid}"}
        atomic_json(self.directory / f"recordings/{rid}.json", record)

    def favorites(self):
        return sorted({r["recording_id"] for r in self.state["matching_outcomes"] if r["status"] == "accepted"})

    def registry(self):
        return build_registry(list(self.state["records"].values()), self.favorites(),
                              names=self.metadata["submitted_artists"], input_sha256=self.metadata["input_sha256"])

    def report(self):
        return recommendation_report(list(self.state["records"].values()), self.favorites(), registry=self.registry(),
                                     excluded_ids=self.known_favorites, limit=self.config["limit"],
                                     weights=self.config["role_weights"], saturation_k=self.config["saturation_k"],
                                     contributor_policy="penalized", seed_balancing=True, deduplicate_works=True)

    def failed_match_status(self):
        error = self.client.events[-1].get("error", "") if self.client.events else ""
        return "invalid_response" if error and error.startswith(("ValueError:", "JSONDecodeError:")) else "provider_failure"

    def matching_fetch(self, endpoint, operation, *, row=None, **params):
        url = API + endpoint + "?" + urlencode(sorted({"fmt": "json", **params}.items()))
        allocation = matching_allocation(self.client.max_requests)
        if url not in self.client.memo:
            if self.client.stats["attempts"] >= self.client.max_requests:
                raise CollectionStopped("request_budget")
            if self.client.stats["attempts"] >= allocation["matching_attempt_limit"]:
                raise MatchingStageEnded()
        if row is not None:
            row.setdefault("queries", []).append(params["query"])
            row["query_count"] = len(row["queries"])
            row["fallback_used"] = operation == "seed_search_fallback"
            self.save()
        return self.fetch(endpoint, operation, **params)

    def match_one(self, index, *, fallback=False):
        track = self.sampled[index]["source_row"]
        row = self.state["matching_outcomes"][index]
        row.update(status="in_progress", raw_title=track["song_text"], raw_artist=track["artist_text"],
                   normalized_title=title_keys(track["song_text"]), normalized_artist=main_artist_key(track["artist_text"]),
                   fallback_used=row.get("fallback_used", False))
        self.save()
        rid = track.get("recording_mbid")
        if not rid:
            query = seed_query(track, fallback=fallback)
            body = self.matching_fetch("recording", "seed_search_fallback" if fallback else "seed_search",
                                       row=row, query=query, limit=25, offset=0)
            if body is None:
                row["status"] = self.failed_match_status()
                self.save()
                return False
            rows, count = body.get("recordings"), body.get("count")
            if (not isinstance(rows, list) or type(count) is not int or count < len(rows)
                    or len(rows) > 25 or body.get("offset", 0) != 0):
                row["status"] = "invalid_response"
                self.save()
                return False
            row["search_truncated"] = row.get("search_truncated", False) or count > len(rows)
            row.setdefault("search_pages", []).append({"query": query, "reported_total": count,
                "returned": len(rows), "source": self.client.last_source, "alternatives": rows})
            alternatives = {r["id"]: r for r in rows if compatible(track, r)}
            row["plausible_candidates"] = len(alternatives)
            if not alternatives:
                row["status"] = "invalid_response" if rows and not any(core_response_valid(r) for r in rows) else "no_compatible_candidate"
                self.save()
                return row["status"] == "no_compatible_candidate" and not fallback
            rid = choose_candidate(track, alternatives.values())["id"]
            row["alternative_recording_ids"] = sorted(alternatives)
            row["selection_reason"] = "full_identity_version_then_album_then_duration_then_recording_id"
        else:
            row.update(selection_reason="supplied_recording_id", supplied_recording_id=rid, query_count=0)
        row["chosen_recording_id"] = rid
        self.save()
        record = self.state["records"].get(rid)
        if record is None:
            record = self.matching_fetch(f"recording/{rid}", "seed_lookup", inc=MATCH_INCLUDES)
        if record is None:
            row["status"] = self.failed_match_status()
        elif not core_response_valid(record) or record["id"] != rid:
            row["status"] = "invalid_response"
        else:
            row["checks"] = identity_checks(track, record)
            row["normalized_artist"] = row["checks"]["normalized_artist"]
            row["status"] = "accepted" if compatible(track, record) else "no_compatible_candidate"
            if row["status"] == "accepted":
                row.update(recording_id=rid, credit_coverage=credit_diagnostics(record),
                           representative_version_notice=version_notice(track, record))
                if rid not in self.state["records"]:
                    self.freeze(record)
        self.save()
        return False

    def match(self):
        fallbacks = []
        try:
            for index in range(len(self.sampled)):
                if self.match_one(index):
                    fallbacks.append(index)
            for index in fallbacks:
                self.state["matching_outcomes"][index]["fallback_pending"] = True
                self.save()
                self.match_one(index, fallback=True)
                self.state["matching_outcomes"][index]["fallback_pending"] = False
        except MatchingStageEnded:
            for row in self.state["matching_outcomes"]:
                if row["status"] in {"not_attempted", "in_progress"}:
                    row.update(status="stage_budget", stopping_reason="matching_stage_budget")
            for index in fallbacks:
                row = self.state["matching_outcomes"][index]
                if row["status"] == "no_compatible_candidate":
                    row["fallback_not_attempted_reason"] = "matching_stage_budget"
        finally:
            self.state["matching_attempts"] = self.client.stats["attempts"]
            self.save()

    def consider(self, record):
        rid = record.get("id") if isinstance(record, dict) else None
        if not rid or rid in self.seen or rid in self.state["records"]:
            return
        self.seen.add(rid)
        self.state["discovery"]["examined_recordings"] += 1
        reason = None
        if rid in self.known_favorites:
            reason = "submitted_favorite_recording"
        elif not valid_record(record):
            reason = "missing_credit_fields"
        else:
            eligible = candidate_eligibility(record, self.registry())
            if not eligible["eligible"]:
                reason = eligible["reason"]
            elif not ({c["artist"]["id"] for c in extract_credits(record) if c["category"]}
                      & set(self.state["discovery"]["contributor_queue"])):
                reason = "no_observed_shared_contributor"
        if reason:
            self.state["discovery"]["exclusions"].append({"recording_id": rid, "reason": reason})
        else:
            self.freeze(record)
            self.state["discovery"]["admitted_candidates"] += 1
        self.save()

    def browse(self, route, *, work=None):
        body = self.fetch("recording", "work_browse" if work else "artist_browse",
                          **({"work": work} if work else {"artist": route["artist_id"]}),
                          inc=BROWSE_INCLUDES, limit=25, offset=0)
        if body is None:
            return
        rows, count = body.get("recordings"), body.get("recording-count")
        if (not isinstance(rows, list) or len(rows) > 25 or type(count) is not int or count < len(rows)
                or body.get("recording-offset", 0) != 0):
            self.state["failures"].append({"operation": "browse", "error": "invalid browse response"})
            return
        route["pages"].append({"work_id": work, "returned": len(rows), "reported_total": count,
                               "unfetched": count - len(rows), "source": self.client.last_source})
        for record in rows:
            self.client.remaining()
            if not isinstance(record, dict):
                continue
            try:
                rid = mbid(record["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if valid_record(record):
                self.consider(record)
                if self.should_stop():
                    break
            elif rid not in self.queued and rid not in self.state["records"]:
                route["pending"].append(rid)
                self.queued.add(rid)
        self.save()

    def should_stop(self):
        if self.state["discovery"]["admitted_candidates"] >= 100:
            self.state["stop_reason"] = "candidate_limit"
            return True
        summary = self.report()["selection_summary"]
        if summary["returned"] >= self.config["limit"] and summary["source_coverage_shortfall"] == 0:
            self.state["stop_reason"] = "target_reached"
            return True
        return False

    def advance_route(self, route):
        """Advance one shared contributor route; perform at most one HTTP attempt."""
        aid, phase = route["artist_id"], route["phase"]
        allowed = load_rules()["eligible_relationships"]
        if phase == "artist":
            artist = self.fetch(f"artist/{aid}", "contributor_lookup", inc="recording-rels+work-rels")
            if artist is not None and artist.get("id") == aid and isinstance(artist.get("relations"), list):
                for relation in artist["relations"]:
                    if not isinstance(relation, dict) or any(a.casefold() == "executive" for a in relation.get("attributes", [])):
                        continue
                    target, kind = relation.get("target-type"), relation.get("type-id")
                    try:
                        if target == "recording" and kind in allowed:
                            rid = mbid(relation.get("recording", {}).get("id"))
                            if rid not in self.queued and rid not in self.state["records"]:
                                route["pending"].append(rid)
                                self.queued.add(rid)
                        elif target == "work" and kind in SONGWRITING_IDS:
                            route["work_ids"].append(mbid(relation.get("work", {}).get("id")))
                    except (ValueError, TypeError, AttributeError):
                        continue
            route["pending"].sort()
            route["work_ids"] = sorted(set(route["work_ids"]))
            route["phase"] = "browse"
        elif phase == "browse":
            self.browse(route)
            route["phase"] = "work"
        elif phase == "work":
            if route["work_ids"]:
                self.browse(route, work=route["work_ids"][0])
            route["phase"] = "lookup"
        else:
            while route["pending"] and (route["pending"][0] in self.seen or route["pending"][0] in self.state["records"]):
                route["pending"].pop(0)
            if route["pending"]:
                rid = route["pending"].pop(0)
                record = self.fetch(f"recording/{rid}", "candidate_lookup", inc=MATCH_INCLUDES)
                if record is not None and record.get("id") == rid:
                    self.consider(record)
                else:
                    self.seen.add(rid)
            else:
                route["exhausted"] = True

    def discover(self):
        training, frontier = set(self.favorites()), {}
        mapping, groups = source_song_groups(list(self.state["records"].values()), training)
        for rid in sorted(training):
            for credit in extract_credits(self.state["records"][rid]):
                if credit["category"]:
                    item = frontier.setdefault(credit["artist"]["id"], {"recording_ids": set()})
                    item["recording_ids"].add(rid)
        order = balanced_frontier(frontier, self.state["records"], training)
        discovery = self.state["discovery"]
        discovery["contributor_queue"] = order
        routes = {aid: {"artist_id": aid, "phase": "artist", "pending": [], "work_ids": [],
                       "pages": [], "exhausted": False,
                       "beneficiary_source_groups": sorted({mapping[rid] for rid in frontier[aid]["recording_ids"]})}
                  for aid in order}
        discovery["routes"] = list(routes.values())
        seeds = []
        for group, description in sorted(groups.items()):
            contributors = [aid for aid in order if group in routes[aid]["beneficiary_source_groups"]]
            seeds.append(description | {"contributors": contributors, "status": "unexplored"})
        discovery["per_seed"] = seeds
        discovery["count_interpretation"] = "Per-seed connections overlap; sponsored attempts sum to the global discovery attempt total."
        active = deque(seeds)
        while active:
            seed = active.popleft()
            before = self.client.stats["attempts"]
            seed["status"] = "active"
            # Reused evidence and zero-request transitions do not consume this seed's turn.
            while seed["contributors"]:
                self.client.remaining()
                aid = seed["contributors"][0]
                route = routes[aid]
                if route["exhausted"]:
                    seed["contributors"].pop(0)
                    continue
                self.client.request_context = {"sponsor_source_group": seed["source_group_id"],
                                               "beneficiary_source_groups": route["beneficiary_source_groups"]}
                try:
                    old_phase = route["phase"]
                    self.advance_route(route)
                finally:
                    self.client.request_context = {}
                if old_phase == "lookup" and not route["exhausted"]:
                    seed["contributors"].append(seed["contributors"].pop(0))
                self.save()
                if self.should_stop():
                    return
                if self.client.stats["attempts"] > before:
                    break
            if seed["contributors"]:
                active.append(seed)
            else:
                seed.update(status="exhausted", exhaustion_reason="routes_exhausted")
            self.save()
        self.state["stop_reason"] = "routes_exhausted"

    def run(self):
        started = time.monotonic()
        phase = "matching"
        try:
            self.match()
            self.state["stage_timings"][phase] = time.monotonic() - started
            phase, started = "discovery", time.monotonic()
            if self.config.get("matching_only"):
                self.state["stop_reason"] = "matching_complete"
            elif self.favorites():
                self.discover()
            else:
                self.state["stop_reason"] = "no_accepted_seeds"
        except CollectionStopped as stop:
            self.state["stop_reason"] = stop.reason
            for row in self.state["matching_outcomes"]:
                if row["status"] in {"not_attempted", "in_progress"}:
                    row.update(status="global_budget" if stop.reason == "request_budget" else "interrupted",
                               stopping_reason=stop.reason)
                elif row["status"] == "no_compatible_candidate" and row.get("query_count") == 1:
                    row["fallback_not_attempted_reason"] = stop.reason
        finally:
            self.state["stage_timings"][phase] = time.monotonic() - started
            self.save()


def _collection_worker(directory, tracks, metadata, sampled, config, deadline, contact, pacing_directory, opener):
    state = read_json(Path(directory) / "checkpoint.json")
    try:
        client = FreshClient(directory, contact=contact, max_requests=config["max_requests"], deadline=deadline,
                             pacing_directory=pacing_directory, opener=opener)
        QuickCollection(directory, tracks, metadata, sampled, config, client, state).run()
    except Exception as error:
        state["stop_reason"] = "collection_error"
        state["error"] = f"{type(error).__name__}: {error}"
        atomic_json(Path(directory) / "checkpoint.json", state)


def supervise_collection(target, args, *, deadline):
    """Use a process, rather than a thread timeout, to stop DNS/read/transport stalls."""
    worker = multiprocessing.get_context("spawn").Process(target=target, args=args)
    worker.start()
    try:
        worker.join(max(0, deadline - time.monotonic()))
        interrupted = worker.is_alive()
        if interrupted:
            worker.terminate()
            worker.join(0.2)
            if worker.is_alive():
                worker.kill()
                worker.join(0.2)
        return interrupted, worker.exitcode
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(0.2)
        worker.close()


def recommend_from_likes(input_path, *, random_seed, seed_count=8, limit=15, max_requests=35,
                         runtime_limit_seconds=55, contact, output_directory=None,
                         _pacing_directory=PACING_DIRECTORY, _opener=open_fresh,
                         _sampled_seeds=None, _matching_only=False):
    """Return a fresh recommendation run; output_directory must be new when supplied."""
    started = time.monotonic()
    for name, value in (("seed_count", seed_count), ("limit", limit), ("max_requests", max_requests)):
        if type(value) is not int or not 1 <= value <= 1000:
            raise ValueError(f"{name} must be an integer between 1 and 1000")
    if not isinstance(runtime_limit_seconds, (int, float)) or not math.isfinite(runtime_limit_seconds) or not 0 < runtime_limit_seconds <= 55:
        raise ValueError("runtime_limit_seconds must be positive and at most 55")
    if not contact or not re.fullmatch(r"(?:[^\s@()]+@[^\s@()]+\.[^\s@()]+|https?://[^\s()]+)", contact):
        raise ValueError("Live collection needs a contact email or URL")
    input_path = Path(input_path)
    tracks, metadata = load_input(input_path)
    sampled, sampling_summary = sample_likes(tracks, random_seed=random_seed, seed_count=seed_count)
    if _sampled_seeds is not None:
        sampled = _sampled_seeds
    weights = load_weights()
    config = {"random_seed": random_seed, "seed_count": seed_count, "limit": limit,
              "max_requests": max_requests, "runtime_limit_seconds": runtime_limit_seconds,
              "seed_matching_policy": POLICY, "matching_only": _matching_only,
              "selection_policy": "source_balanced_greedy_v1", "min_seed_groups": 3, "max_per_seed": 2,
              "deduplicate_known_works": True,
              **matching_allocation(max_requests),
              "role_weights": weights["role_weights"], "saturation_k": weights["saturation_k"]}
    directory = Path(output_directory) if output_directory is not None else ROOT / "data/private/quick_runs" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "inputs").mkdir()
    raw = input_path.read_bytes()
    if digest(raw) != metadata["input_sha256"]:
        raise ValueError("Favorites input changed while sampling")
    (directory / "inputs/favorites.json").write_bytes(raw)
    state = {"records": {}, "sources": {}, "failures": [], "stage_timings": {},
             "matching_outcomes": [{"source_lines": s["source_row"]["source_lines"],
                                     "status": "not_attempted", "recording_id": None,
                                     "raw_title": s["source_row"]["song_text"], "raw_artist": s["source_row"]["artist_text"],
                                     "normalized_title": title_keys(s["source_row"]["song_text"]),
                                     "normalized_artist": main_artist_key(s["source_row"]["artist_text"]),
                                     "query_count": 0, "fallback_used": False} for s in sampled],
             "discovery": {"contributor_queue": [], "routes": [], "exclusions": [],
                           "examined_recordings": 0, "admitted_candidates": 0}, "stop_reason": "collection_running"}
    atomic_json(directory / "checkpoint.json", state)
    atomic_json(directory / "requests.json", {"attempts": 0, "by_operation": {}, "events": [],
                                             "within_run_reuses": 0, "pacing_seconds": 0, "transport_seconds": 0})
    sampling_seconds = time.monotonic() - started
    deadline = started + runtime_limit_seconds - min(5, runtime_limit_seconds / 4)
    collection_started = time.monotonic()
    interrupted, exitcode = supervise_collection(_collection_worker,
        (directory, tracks, metadata, sampled, config, deadline, contact, Path(_pacing_directory), _opener), deadline=deadline)
    collection_seconds = time.monotonic() - collection_started
    state, requests = read_json(directory / "checkpoint.json"), read_json(directory / "requests.json")
    if interrupted:
        state["stop_reason"] = "deadline"
        for event in requests["events"]:
            if event["outcome"] == "in_progress":
                event["outcome"] = "interrupted"
                event["elapsed_seconds"] = max(0, time.time() - event["started_at"])
                requests["transport_seconds"] += event["elapsed_seconds"]
        atomic_json(directory / "requests.json", requests)
    elif exitcode != 0:
        state["stop_reason"] = "worker_failed"
    for row in state["matching_outcomes"]:
        if row["status"] in {"in_progress", "not_attempted"}:
            row.update(status="interrupted", stopping_reason=state["stop_reason"])
        if row["status"] == "no_compatible_candidate" and row.get("query_count") == 1:
            row.setdefault("fallback_not_attempted_reason", state["stop_reason"])
    records = list(state["records"].values())
    favorites = sorted({r["recording_id"] for r in state["matching_outcomes"] if r["status"] == "accepted"})
    registry = build_registry(records, favorites, names=metadata["submitted_artists"], input_sha256=metadata["input_sha256"])
    score_started = time.monotonic()
    report = recommendation_report(records, favorites, registry=registry, limit=limit,
                                   excluded_ids={t["recording_mbid"] for t in tracks if t.get("recording_mbid")},
                                   weights=config["role_weights"], saturation_k=config["saturation_k"],
                                   contributor_policy="penalized", seed_balancing=True, deduplicate_works=True)
    scoring_seconds = time.monotonic() - score_started
    matching_counts = dict(Counter(r["status"] for r in state["matching_outcomes"]))
    discovery = state["discovery"]
    if discovery.get("per_seed"):
        from .recommend_songs import score_song_candidates
        mapping, groups = source_song_groups(records, favorites)
        scored = score_song_candidates(records, favorites, weights=config["role_weights"], saturation_k=config["saturation_k"])
        assignments = {r["recording"]["id"]: assignment_evidence(r, mapping) for r in scored}
        for seed in discovery["per_seed"]:
            group = seed["source_group_id"]
            events = [e for e in requests["events"] if e.get("sponsor_source_group") == group]
            connected = [rid for rid, evidence in assignments.items() if group in evidence]
            eligible = [rid for rid in connected if candidate_eligibility(state["records"][rid], registry)["eligible"]]
            routes = [r for r in discovery["routes"] if group in r["beneficiary_source_groups"]]
            seed.update(attempts_sponsored=len(events), operations=dict(Counter(e["operation"] for e in events)),
                        contributors_explored=sum(r["phase"] != "artist" for r in routes),
                        candidates_connected=len(connected), candidates_eligible=len(eligible),
                        candidates_selected=report["selection_summary"]["recommendations_per_source"].get(group, 0),
                        unexplored_routes=sum(r["phase"] == "artist" for r in routes),
                        unexhausted_routes=sum(not r["exhausted"] for r in routes), paused=False)
            if seed["status"] != "exhausted":
                seed["stopping_reason"] = state["stop_reason"]
    result = report | {"format_version": 1, "kind": "quick_recommendation_run", "created_at": utc_now(),
                       "output_directory": str(directory.resolve()), "input_sha256": metadata["input_sha256"],
                       "configuration": config, "fresh_api_data": True, "sampled_seeds": sampled,
                       "sampling_summary": sampling_summary, "matching_outcomes": state["matching_outcomes"],
                       "matching_summary": {"sampled": len(sampled), "accepted_recordings": len(favorites),
                                            "accepted_sampled_rows": matching_counts.get("accepted", 0),
                                            "match_rate": matching_counts.get("accepted", 0) / len(sampled) if sampled else None,
                                            "seeds_with_additional_credits": sum(r.get("credit_coverage", {}).get("additional_contributor_credits_observed", False) for r in state["matching_outcomes"]),
                                            "matching_attempts": state.get("matching_attempts", requests["attempts"]),
                                            **matching_allocation(max_requests), "outcomes": matching_counts},
                       "favorite_recording_ids": favorites, "requests": requests,
                       "stop_reason": state["stop_reason"], "failures": state["failures"],
                       "candidate_coverage": discovery | {"explored_routes": sum(r["phase"] != "artist" for r in discovery["routes"]),
                           "unexplored_routes": sum(r["phase"] == "artist" for r in discovery["routes"]),
                           "unexhausted_routes": sum(not r["exhausted"] for r in discovery["routes"]), "exhaustive": False},
                       "stage_timings": state["stage_timings"] | {"sampling": sampling_seconds,
                           "collection_total": collection_seconds, "scoring": scoring_seconds},
                       "runtime_target_seconds": 60, "limitations": [
                           "A random seed reproduces sampling, not changing live responses or deadline-dependent coverage.",
                           "No Apple availability filter or claim is applied.",
                           "Recording identities and listening quality have not been independently audited."]}
    if "error" in state:
        result["error"] = state["error"]
    export_started = time.monotonic()
    atomic_json(directory / "manifest.json", {"format_version": 1, "kind": "quick contributor song graph",
                "input_sha256": metadata["input_sha256"], "sources": list(state["sources"].values()),
                "artist_registry_sha256": registry_digest(registry), "collection_status": state["stop_reason"]})
    atomic_json(directory / "profile.json", {"format_version": 1, "input_sha256": metadata["input_sha256"],
                "artist_registry": registry, "favorites": [{"recording_id": rid,
                    "source_sha256": state["sources"][rid]["sha256"], "source_lines": sorted({n for row in state["matching_outcomes"]
                        if row["recording_id"] == rid for n in row["source_lines"]})} for rid in favorites]})
    write_song_review(directory / "SONG_REVIEW.md", report)
    write_run_diagnostics(directory / "SONG_REVIEW.md", result)
    result["elapsed_seconds"] = time.monotonic() - started
    atomic_json(directory / "recommendations.json", result)
    result["stage_timings"]["final_export"] = time.monotonic() - export_started
    result["elapsed_seconds"] = time.monotonic() - started
    result["runtime_target_met"] = result["elapsed_seconds"] < 60
    atomic_json(directory / "recommendations.json", result)
    return result


def write_run_diagnostics(path, result):
    """Keep sampling and partial-coverage diagnostics beside the listening list."""
    coverage, requests = result["candidate_coverage"], result["requests"]
    lines = ["", "## Live run diagnostics", "",
             f"Stopped because: {result['stop_reason']}. Fresh responses; no Apple requests.",
             f"Matched {result['matching_summary']['accepted_sampled_rows']}/{len(result['sampled_seeds'])} sampled rows ({result['matching_summary']['match_rate']:.1%}); {result['matching_summary']['accepted_recordings']} distinct recordings; {result['matching_summary']['seeds_with_additional_credits']} rows with additional eligible credits.",
             f"HTTP attempts: {requests['attempts']}/{result['configuration']['max_requests']}.",
             f"Candidates admitted: {coverage['admitted_candidates']}/100; unexplored contributor routes: {coverage['unexplored_routes']}; unexhausted routes: {coverage['unexhausted_routes']}.",
             "Coverage is partial. All submitted artist names remain excluded.", "",
             "Requests by operation:", ""]
    lines.extend(f"- {operation}: {count}" for operation, count in sorted(requests["by_operation"].items()))
    lines += ["", "Sampled favorites and matching outcomes:", ""]
    for sample, outcome in zip(result["sampled_seeds"], result["matching_outcomes"]):
        track = sample["source_row"]
        lines.append(f"- {track['artist_text']} — {track['song_text']} (source rows {', '.join(map(str, track['source_lines']))}; {sample['liked_song_count']} distinct liked songs; sampling weight {sample['sampling_weight']}): {outcome['status']}.")
    lines += ["", "Completed stage timings (collection total includes worker startup and interrupted transport):", ""]
    lines.extend(f"- {stage}: {seconds:.3f} seconds" for stage, seconds in result["stage_timings"].items())
    lines += ["", "See recommendations.json for total elapsed time, export timing, request evidence, and complete coverage.", ""]
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def add_run_arguments(parser):
    parser.add_argument("--input", type=Path, default=ROOT / "data/private/favorites.json")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--max-requests", type=int, default=35)
    parser.add_argument("--runtime-limit-seconds", type=float, default=55)
    parser.add_argument("--contact-file", type=Path, required=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_arguments(parser)
    parser.add_argument("--random-seed", type=int, required=True)
    parser.add_argument("--seed-count", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = recommend_from_likes(args.input, random_seed=args.random_seed, seed_count=args.seed_count,
            limit=args.limit, max_requests=args.max_requests, runtime_limit_seconds=args.runtime_limit_seconds,
            contact=args.contact_file.read_text().strip(), output_directory=args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"output": result["output_directory"], "elapsed_seconds": result["elapsed_seconds"],
                      "http_attempts": result["requests"]["attempts"], "matching": result["matching_summary"],
                      "recommendations": result["selection_summary"]["returned"], "stop_reason": result["stop_reason"]}, indent=2))
    if result["stop_reason"] in {"collection_error", "worker_failed"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
