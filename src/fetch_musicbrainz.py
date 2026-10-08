"""Collect a bounded recording-credit pilot, or rebuild it from the local cache."""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from .build_graph import ROOT, build_graph, load_rules, relationship_exclusion
from .recommend import explain_contribution, recommend


API = "https://musicbrainz.org/ws/2/"
RECORDING_INCLUDES = "artist-credits+artist-rels+work-rels+work-level-rels"
CACHE_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json_bytes(value))
    temporary.replace(path)


def mbid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError(f"Noncanonical MusicBrainz ID: {value}")
    return value


@dataclass(frozen=True)
class Limits:
    seed_recordings: int = 8
    intermediaries_per_seed: int = 2
    expansion_recordings: int = 6
    expansion_depth: int = 1
    max_requests: int = 100
    min_interval_seconds: float = 1.1
    timeout_seconds: float = 20
    max_response_bytes: int = 16 * 1024 * 1024
    retries: int = 1

    def __post_init__(self):
        for field in ("seed_recordings", "expansion_recordings"):
            if type(getattr(self, field)) is not int or not 1 <= getattr(self, field) <= 100:
                raise ValueError(f"{field} must be an integer between 1 and 100")
        for field in ("intermediaries_per_seed", "max_requests", "max_response_bytes"):
            if type(getattr(self, field)) is not int or getattr(self, field) < 1:
                raise ValueError(f"{field} must be a positive integer")
        if self.expansion_depth != 1 or type(self.expansion_depth) is not int:
            raise ValueError("Only one intermediary expansion round is supported")
        if type(self.retries) is not int or not 0 <= self.retries <= 1:
            raise ValueError("Allow zero or one transient retry")
        for field in ("min_interval_seconds", "timeout_seconds"):
            value = getattr(self, field)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid {field}")
        if self.min_interval_seconds < 1:
            raise ValueError("MusicBrainz requires at least one second between requests")


class FetchError(Exception):
    pass


class MusicBrainzClient:
    """URL-addressed raw-response cache. Offline mode never calls the transport."""

    api = API
    query_defaults = {"fmt": "json"}
    requires_contact = True

    def __init__(self, cache_dir: Path, limits: Limits, *, contact: str | None = None,
                 offline: bool = False, retry_failures: bool = False,
                 opener=urlopen, clock=time.time, sleep=time.sleep, before_attempt=None):
        if offline and retry_failures:
            raise ValueError("Cannot retry failures offline")
        if not offline and self.requires_contact and (not contact or not re.fullmatch(
                r"(?:[^\s@()]+@[^\s@()]+\.[^\s@()]+|https?://[^\s()]+)", contact)):
            raise ValueError("Live collection needs a contact email or URL")
        self.cache_dir, self.limits = cache_dir, limits
        self.offline, self.retry_failures = offline, retry_failures
        self.user_agent = (f"music-credit-recommender/0.2.0 ({contact})" if contact else
                           "music-credit-recommender/0.2.0" if not offline else None)
        self.opener, self.clock, self.sleep = opener, clock, sleep
        self.network_attempts = 0
        self.request_budget = None
        self.events = []
        self.before_attempt = before_attempt
        self._lock = None

    def __enter__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = (self.cache_dir / ".collection.lock").open("a")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._lock.close()
            self._lock = None
            raise FetchError("Another collector is using this cache directory") from error
        return self

    def __exit__(self, *args):
        if self._lock:
            self._lock.close()
            self._lock = None

    def _pace(self, not_before: float = 0) -> None:
        marker = self.cache_dir / ".last_request"
        last = float(marker.read_text()) if marker.exists() else 0
        delay = max(last + self.limits.min_interval_seconds, not_before) - self.clock()
        if delay > 0:
            self.sleep(delay)
        marker.write_text(str(self.clock()))

    def get(self, endpoint: str, **params) -> dict:
        if self._lock is None:
            raise RuntimeError(f"Use {type(self).__name__} as a context manager")
        url = self.api + endpoint + "?" + urlencode(sorted({**self.query_defaults, **params}.items()))
        path = self.cache_dir / (digest(url.encode()) + ".json")
        if path.exists():
            try:
                envelope = json.loads(path.read_bytes())
                if (envelope["format_version"] != CACHE_VERSION or envelope["query"] != url
                        or digest(envelope["response_text"].encode()) != envelope["response_sha256"]):
                    raise ValueError("invalid cache metadata or hash")
            except (ValueError, KeyError, TypeError) as error:
                raise FetchError(f"Corrupt cache entry for {url}: {error}") from error
            if not envelope["error"] or not self.retry_failures:
                self.events.append(self._event(envelope, path, "cache"))
                if envelope["error"]:
                    raise FetchError(f"Cached failure: {envelope['error']}")
                return json.loads(envelope["response_text"])
        if self.offline:
            self.events.append({"query": url, "mode": "offline-miss", "error": "cache miss"})
            raise FetchError(f"Offline cache miss: {url}")
        attempts, not_before = [], 0
        for attempt in range(self.limits.retries + 1):
            if self.network_attempts >= (self.limits.max_requests if self.request_budget is None else self.request_budget):
                if attempts:
                    self.events.append(self._event(envelope, path, "network"))
                self.events.append({"query": url, "mode": "budget", "error": "request budget exhausted"})
                raise FetchError("Request budget exhausted")
            self._pace(not_before)
            if self.before_attempt is not None:
                self.before_attempt(url, attempt)
            self.network_attempts += 1
            text, status, error, transient = "", None, None, False
            started_at = utc_now()
            try:
                request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
                # Record the actual send boundary, after request preparation, so a slow
                # preparation cannot shorten the interval before the following request.
                (self.cache_dir / ".last_request").write_text(str(self.clock()))
                with self.opener(request, timeout=self.limits.timeout_seconds) as response:
                    status = response.status
                    raw = response.read(self.limits.max_response_bytes + 1)
                if len(raw) > self.limits.max_response_bytes:
                    raise ValueError("Response exceeds configured byte limit")
                text = raw.decode("utf-8")
                body = json.loads(text)
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                if status != 200:
                    raise ValueError(f"Unexpected HTTP status {status}")
            except HTTPError as failure:
                status = failure.code
                text = failure.read(self.limits.max_response_bytes).decode("utf-8", errors="replace")
                error = f"HTTP {status}"
                transient = status in {429, 500, 502, 503, 504}
                retry_after = failure.headers.get("Retry-After", "0") if failure.headers else "0"
                try:
                    backoff = float(retry_after)
                    if not math.isfinite(backoff) or backoff < 0:
                        backoff = 0
                except ValueError:
                    try:
                        backoff = max(0, parsedate_to_datetime(retry_after).timestamp() - self.clock())
                    except (ValueError, TypeError, OverflowError):
                        backoff = 0
                # Do not wait unboundedly on a server hint; preserve the failure instead.
                transient = transient and backoff <= 60
                not_before = self.clock() + max(2, backoff)
                failure.close()
            except (URLError, OSError, TimeoutError) as failure:
                error, transient = type(failure).__name__, True
                not_before = self.clock() + 2
            except (ValueError, UnicodeError) as failure:
                error = str(failure)
            attempts.append({"started_at": started_at, "status": status, "error": error})
            envelope = {"format_version": CACHE_VERSION, "query": url,
                        "retrieved_at": utc_now(), "user_agent": self.user_agent,
                        "status": status, "error": error, "attempts": attempts,
                        "response_text": text, "response_sha256": digest(text.encode())}
            save_json(path, envelope)
            if not error or not transient or attempt == self.limits.retries:
                self.events.append(self._event(envelope, path, "network"))
                if error:
                    raise FetchError(error)
                return body
        raise AssertionError("Retry loop must return or raise")

    @staticmethod
    def _event(envelope: dict, path: Path, mode: str) -> dict:
        return {k: envelope[k] for k in ("query", "retrieved_at", "status", "error", "attempts", "response_sha256")} | {
            "cache_file": path.name, "mode": mode}


def load_seeds(path: Path) -> tuple[list[dict], dict]:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata["format_version"] != 1:
        raise ValueError("Unsupported seed-file version")
    seeds = metadata["seeds"]
    if not seeds or len({s["id"] for s in seeds}) != len(seeds):
        raise ValueError("Need a nonempty list of distinct verified seeds")
    for seed in seeds:
        mbid(seed["id"])
        if not seed.get("name") or not seed.get("verification", {}).get("source_url"):
            raise ValueError("Each seed needs a name and identity verification source")
    return seeds, metadata


def collect_sample(client: MusicBrainzClient, seeds: list[dict], seed_metadata: dict,
                   output: Path, rules: dict) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    (output / "recordings").mkdir()
    started = utc_now()
    seed_ids = {s["id"] for s in seeds}
    records, sources, failures, selections, artists = {}, {}, [], [], {}
    limits = client.limits

    def fetch(endpoint, context, **params):
        try:
            return client.get(endpoint, **params)
        except FetchError as error:
            failures.append({"context": context, "endpoint": endpoint, "params": params, "error": str(error)})
            return None

    def artist_lookup(aid):
        result = fetch(f"artist/{aid}", {"stage": "artist", "artist_id": aid}, inc="recording-rels")
        if result is not None:
            if result.get("id") != aid or not result.get("name") or not isinstance(result.get("relations"), list):
                failures.append({"context": {"stage": "artist", "artist_id": aid}, "error": "Malformed artist response"})
                return None
            artists[aid] = result
        return result

    def browse(aid, limit):
        result = fetch("recording", {"stage": "browse", "artist_id": aid},
                       artist=aid, inc="artist-credits", limit=limit, offset=0)
        if result is None:
            return [], {"reported_total": None, "returned_ids": [], "browse_incomplete": True}
        try:
            rows = result["recordings"]
            if not isinstance(rows, list) or len(rows) > limit:
                raise ValueError("Invalid browse page size")
            ids = [mbid(r["id"]) for r in rows]
            total = result["recording-count"]
            if type(total) is not int or total < len(rows):
                raise ValueError("Invalid browse total")
        except (KeyError, ValueError, TypeError) as error:
            failures.append({"context": {"stage": "browse", "artist_id": aid}, "error": str(error)})
            return [], {"reported_total": None, "returned_ids": [], "browse_incomplete": True}
        return ids, {"reported_total": total, "returned_ids": ids,
                     "offset": 0, "limit": limit, "browse_incomplete": len(ids) < total,
                     "unfetched_count": total - len(ids), "order": "MusicBrainz returned order"}

    def recording_lookup(rid, aid, stage, routes):
        origin = {"stage": stage, "artist_id": aid, "routes": routes}
        if rid in records:
            sources[rid]["origins"].append(origin)
            return
        result = fetch(f"recording/{rid}", {"stage": stage, "recording_id": rid, "artist_id": aid},
                       inc=RECORDING_INCLUDES)
        if result is None:
            return
        try:
            if result.get("id") != rid or not result.get("title") or not isinstance(result.get("artist-credit"), list):
                raise ValueError("Malformed recording response")
            if not isinstance(result.get("relations"), list):
                raise ValueError("Missing requested recording relationships")
            # Validate relationship structure using the same graph builder used in ranking.
            build_graph([result], rules)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"context": origin | {"recording_id": rid}, "error": str(error)})
            return
        records[rid] = result
        relative = f"recordings/{rid}.json"
        data = json_bytes(result)
        (output / relative).write_bytes(data)
        event = client.events[-1]
        sources[rid] = {"recording_id": rid, "source_url": f"https://musicbrainz.org/recording/{rid}",
                        "snapshot_file": relative, "sha256": digest(data), "query": event["query"],
                        "retrieved_at": event["retrieved_at"], "response_sha256": event["response_sha256"],
                        "cache_file": event["cache_file"], "origins": [origin]}

    for seed in seeds:
        aid = seed["id"]
        identity = artist_lookup(aid)
        if identity and (identity["name"].casefold() != seed["name"].casefold()
                         or identity.get("type") != seed.get("type")):
            failures.append({"context": {"stage": "seed", "artist_id": aid},
                             "error": "Seed identity differs from verified name/type; skipped"})
            continue
        ids, coverage = browse(aid, limits.seed_recordings)
        selections.append({"stage": "seed", "artist_id": aid, "browse": coverage, "selected_ids": ids})
        for rid in ids:
            recording_lookup(rid, aid, "seed", ["primary-credit browse"])

    seed_graph = build_graph(list(records.values()), rules)
    seed_recording_ids = set(records)
    frontiers = []
    selected_intermediaries = set()
    for aid in sorted(seed_ids):
        neighbors = seed_graph.adjacency.get(aid, {})
        ordered = sorted((i for i in neighbors if i not in seed_ids), key=lambda i: (-len(neighbors[i]), i))
        chosen = ordered[:limits.intermediaries_per_seed]
        selected_intermediaries.update(chosen)
        frontiers.append({"seed_id": aid, "eligible_intermediaries": len(ordered), "selected_ids": chosen,
                          "omitted_ids": ordered[len(chosen):],
                          "selection_evidence": [{"artist_id": i, "shared_recording_ids": [e["recording"]["id"] for e in neighbors[i]]}
                                                 for i in chosen]})

    for aid in sorted(selected_intermediaries):
        artist = artist_lookup(aid)
        relation_routes, rejected = {}, []
        if artist:
            for relation in artist["relations"]:
                if relation.get("target-type") != "recording":
                    continue
                rid = relation.get("recording", {}).get("id")
                reason = relationship_exclusion(relation, rules, relation.get("level", "recording"))
                if reason:
                    rejected.append({"recording_id": rid, "role": relation.get("type"),
                                     "relationship_type_id": relation.get("type-id"), "reason": reason})
                else:
                    try:
                        rid = mbid(rid)
                    except (ValueError, TypeError, AttributeError):
                        failures.append({"context": {"stage": "expansion", "artist_id": aid}, "error": "Invalid related recording ID"})
                        continue
                    relation_routes.setdefault(rid, []).append("eligible recording relationship")
        ids, coverage = browse(aid, limits.expansion_recordings)
        for rid in ids:
            relation_routes.setdefault(rid, []).append("primary-credit browse")
        pool = sorted(set(relation_routes) - records.keys())
        chosen = pool[:limits.expansion_recordings]
        selection = {"stage": "expansion", "artist_id": aid, "browse": coverage,
                     "artist_relationships_returned": len(artist["relations"]) if artist else None,
                     "relationship_list_completeness": "Not certified; artist relationships have no paging interface",
                     "excluded_discovery_relationships": rejected,
                     "already_collected_ids": sorted(set(relation_routes) & records.keys()),
                     "selected_ids": chosen, "omitted_ids": pool[len(chosen):],
                     "eligible_discovery_ids": sorted(relation_routes)}
        selections.append(selection)
        for rid in chosen:
            recording_lookup(rid, aid, "expansion", sorted(set(relation_routes[rid])))

    graph = build_graph(list(records.values()), rules)
    usable_seeds = sorted(seed_ids & graph.artists.keys())
    rankings = {method: recommend(graph, usable_seeds, method) for method in ("direct", "two-hop")}
    seed_rankings = {method: recommend(seed_graph, sorted(seed_ids & seed_graph.artists.keys()), method)
                     for method in ("direct", "two-hop")}

    def reach(rows):
        return {r["artist"]["id"] for r in rows if r["score"] > 0}

    role_counts = Counter(c["role"] for by_artist in graph.credits.values() for credits in by_artist.values() for c in credits)
    exclusion_counts = Counter((e["level"], e["credit"]["role"], e["reason"]) for e in graph.exclusions)
    observed = {"eligible_role_counts": dict(sorted(role_counts.items())),
                "excluded_role_counts": [{"level": level, "role": role, "reason": reason, "count": count}
                                         for (level, role, reason), count in sorted(exclusion_counts.items())]}
    seed_snapshot = [{"recording_id": rid, "sha256": sources[rid]["sha256"]} for rid in sorted(records)]
    fingerprint = digest(json_bytes({"seeds": sorted(seed_ids), "limits": asdict(limits), "rules": rules, "sources": seed_snapshot}))
    manifest = {"format_version": 1, "cache_format_version": CACHE_VERSION, "kind": "bounded API pilot",
                "sample_id": fingerprint, "started_at": started, "completed_at": utc_now(),
                "seed_artist_ids": sorted(seed_ids), "usable_seed_ids": usable_seeds,
                "missing_seed_ids": sorted(seed_ids - graph.artists.keys()), "seed_selection": seed_metadata,
                "limits": asdict(limits), "graph_rules": rules, "sources": [sources[r] for r in sorted(sources)],
                "artist_metadata": [{k: artists[a].get(k) for k in ("id", "name", "type", "disambiguation")} for a in sorted(artists)],
                "frontiers": frontiers, "selections": selections, "failures": failures,
                "requests": client.events, "network_attempts": client.network_attempts, "offline": client.offline,
                "collection_status": "partial" if failures or seed_ids - graph.artists.keys() else "complete_with_declared_limits",
                "stats": graph.stats(), "observed_relationships": observed,
                "coverage": {"seed_recordings": len(seed_recording_ids), "additional_recordings": len(records) - len(seed_recording_ids),
                             "seed_only_stats": seed_graph.stats(),
                             "seed_only_direct_candidates": len(reach(seed_rankings["direct"])),
                             "seed_only_two_hop_candidates": len(reach(seed_rankings["two-hop"])),
                             "expanded_direct_candidates": len(reach(rankings["direct"])),
                             "expanded_two_hop_candidates": len(reach(rankings["two-hop"])),
                             "new_two_hop_candidate_ids": sorted(reach(rankings["two-hop"]) - reach(seed_rankings["two-hop"])),
                             "per_seed": [{"seed_id": aid, "recordings": len([r for r in graph.credits if aid in graph.credits[r]]),
                                           "direct_neighbors": len(graph.adjacency.get(aid, {}))} for aid in sorted(seed_ids)]},
                "limitations": ["Favorites song identities are not matched; this is not a library-coverage or recall estimate.",
                                "First browse pages and a selected frontier are a convenience sample, not a random sample.",
                                "Missing relationships, release-only credits, recording versions, and prolific intermediaries affect coverage.",
                                "All eligible artist entities remain candidates, including engineers and producers.",
                                "No dump, degree penalty, role weights, or preference-quality measurement."],
                "inspection": {"agent_source_review": "pending", "independent_human_review": "pending"}}
    save_json(output / "manifest.json", manifest)
    save_json(output / "exclusions.json", graph.exclusions)
    for method, rows in rankings.items():
        save_json(output / f"recommendations_{method}.json", rows)
    write_review(output, graph, rankings, manifest)
    return manifest


def write_review(output, graph, rankings, manifest):
    rows = rankings["two-hop"]
    positive = [r for r in rows if r["score"] > 0]
    # A review sample, never presented as independently confirmed source evidence.
    selected = positive[:3]
    novel = next((r for r in positive if r["direct_score"] == 0 and r["two_hop_score"]), None)
    if novel and novel not in selected:
        selected.append(novel)
    for seed in manifest["usable_seed_ids"]:
        ordered = sorted(positive, key=lambda r: (
            -sum(c["value"] for c in r["contributions"] if c["seed_id"] == seed),
            r["artist"]["name"].casefold(), r["artist"]["id"]))
        if ordered and any(c["seed_id"] == seed for c in ordered[0]["contributions"]) and ordered[0] not in selected:
            selected.append(ordered[0])
    production_roles = {"producer", "mix", "engineer", "audio", "sound", "recording"}
    for row in positive:
        roles = {c["role"] for by_artist in graph.credits.values()
                 for c in by_artist.get(row["artist"]["id"], [])}
        if roles and roles <= production_roles:
            if row not in selected:
                selected.append(row)
            break
    lines = ["# Real-data source review", "", f"Sample ID: `{manifest['sample_id']}`", "",
             "Independent human review: **pending**. Agent page review: **pending**.", "",
             "Check artist identities, recording versions and durations, both eligible roles on each leg,",
             "and excluded work/recording relationships. A valid credit path does not establish listening appeal.", "",
             f"Collection: {manifest['collection_status']}; {len(manifest['failures'])} failures.", "",
             "Counts and limits: see manifest.json. Full contribution sums: recommendations_two-hop.json.", ""]
    if not selected:
        lines += ["No positive recommendation paths were collected. Report this coverage result before expanding.", ""]
    for row in selected:
        lines += [f"## {row['artist']['name']}", "", f"Artist ID: `{row['artist']['id']}`; score {row['score']} = "
                  f"direct {row['direct_score']} + two-hop {row['two_hop_score']}.", "",
                  "This sheet shows example contributions only; the JSON contains every contribution.", ""]
        contributions = [next((c for c in row["contributions"] if c["kind"] == kind and c["seed_id"] == seed), None)
                         for seed in manifest["usable_seed_ids"] for kind in ("direct", "two-hop")]
        for contribution in filter(None, contributions):
            # Show the original path count and one witness; the JSON retains every path.
            explanation = explain_contribution(graph, contribution)
            lines += ["- " + line for line in explanation[:2]] + [""]
            edges = [contribution["evidence"]] if contribution["kind"] == "direct" else [
                contribution["paths"][0]["first_edge"], contribution["paths"][0]["second_edge"]]
            for edge in edges:
                rid = edge["recording"]["id"]
                metadata = edge["recording"]
                lines += [f"Recording `{rid}`: version `{metadata['disambiguation'] or 'unspecified'}`, "
                          f"duration {metadata['length_ms']} ms, first release {metadata['first_release_date']}.", ""]
                excluded = [e for e in graph.exclusions if e["recording_id"] == rid]
                lines += [f"- Excluded: {e['artist']['name']} / {e['credit']['role']} / {e['reason']}" for e in excluded] + [""]
        lines += ["Human review notes: pending.", ""]
    (output / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, default=ROOT / "data/private/sample_artists.json")
    parser.add_argument("--limits", type=Path, default=ROOT / "config/sample_limits.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache/musicbrainz")
    parser.add_argument("--output", type=Path, required=True, help="New ignored sample directory; never overwritten")
    parser.add_argument("--contact-file", type=Path, help="Local file containing the contact email or URL")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-failures", action="store_true", help="Explicitly retry cached failed requests")
    args = parser.parse_args()
    try:
        seeds, seed_metadata = load_seeds(args.seeds)
        values = json.loads(args.limits.read_text())
        if values.pop("format_version") != 1:
            raise ValueError("Unsupported limit-file version")
        limits = Limits(**values)
        contact = args.contact_file.read_text().strip() if args.contact_file else None
        with MusicBrainzClient(args.cache, limits, contact=contact, offline=args.offline,
                              retry_failures=args.retry_failures) as client:
            manifest = collect_sample(client, seeds, seed_metadata, args.output, load_rules())
    except (OSError, ValueError, TypeError, KeyError, FetchError) as error:
        parser.error(str(error))
    stats, coverage = manifest["stats"], manifest["coverage"]
    print(f"Saved {stats['recordings']} recordings, {stats['artists']} artists, {stats['edges']} edges to {args.output}.")
    print(f"Positive two-hop candidates: {coverage['seed_only_two_hop_candidates']} before expansion, "
          f"{coverage['expanded_two_hop_candidates']} after. HTTP attempts: {manifest['network_attempts']}.")
    print(f"Status: {manifest['collection_status']}; failures: {len(manifest['failures'])}. Human review pending.")
    if manifest["collection_status"] == "partial":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
