"""Process an entire supplied favorites file with durable, bounded collection."""

import argparse
from collections import Counter
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

from .apple_music import AppleClient, collect_availability, dataset_fingerprint, load_apple_rules, validate_availability
from .build_graph import ROOT, load_dataset, load_rules
from .credits import credit_coverage
from .fetch_musicbrainz import FetchError, Limits, MusicBrainzClient, digest, json_bytes, utc_now
from .library_discovery import discover, discovery_snapshot
from .library_job import CheckpointClient, LibraryJob, StageBudgetReached, atomic_bytes, atomic_json, balanced_rows, read_json
from .match_recordings import MatchRules, load_input, match_batch
from .recommend_songs import CATEGORIES, load_weights, profile_favorites, recommendation_report, write_playlist_preparation, write_song_review
from .song_policy import registry_digest, registry_for


def load_configuration(path: Path) -> dict:
    config = read_json(path)
    if config.get("format_version") != 1:
        raise ValueError("Unsupported full-library limits")
    for stage in ("matching", "discovery", "apple"):
        budget = config[stage]
        if set(budget) != {"tranche_attempts", "total_attempts"}:
            raise ValueError("Stage budgets need tranche_attempts and total_attempts")
        if any(type(value) is not int or value < 1 for value in budget.values()):
            raise ValueError("Request allowances must be positive integers")
        if budget["tranche_attempts"] > budget["total_attempts"]:
            raise ValueError("Tranche allowance exceeds total allowance")
    rules = config["discovery_rules"]
    expected = {"candidate_target", "minimum_routes", "recordings_per_contributor", "candidate_lookups_per_contributor",
                "browse_page_size", "max_browse_pages", "works_per_contributor"}
    if set(rules) != expected or any(type(v) is not int or v < 1 for v in rules.values()):
        raise ValueError("Invalid full-library discovery rules")
    if rules["browse_page_size"] > 100 or type(config["requested_songs"]) is not int or config["requested_songs"] < 1:
        raise ValueError("Invalid page or batch size")
    return config


def import_binding(path: Path | None, filenames: tuple[str, ...]):
    return None if path is None else {name: digest((path / name).read_bytes()) for name in filenames}


def publish_dataset(job, label, records, sources, profile, extra=None, matches=None):
    """Publish a complete generation atomically, then move the manifest pointer."""
    by_id, source_index = {}, {}
    for record, source in zip(records, sources, strict=True):
        rid = record["id"]
        if source["recording_id"] != rid or source["sha256"] != digest(json_bytes(record)):
            raise ValueError("Snapshot source checksum mismatch")
        if rid in by_id and by_id[rid] != record:
            raise ValueError(f"Conflicting duplicate recording snapshots: {rid}")
        by_id[rid], source_index[rid] = record, source | {"snapshot_file": f"recordings/{rid}.json"}
    manifest = {"format_version": 1, "kind": f"full library {label}", "input_sha256": profile["input_sha256"],
                "artist_registry_sha256": registry_digest(profile["artist_registry"]),
                "sources": [source_index[rid] for rid in sorted(by_id)],
                "candidate_collection_training_recording_ids": sorted(f["recording_id"] for f in profile["favorites"]),
                **(extra or {})}
    fingerprint = digest(json_bytes({"manifest": manifest, "profile": profile, "matches": matches}))
    manifest["sample_id"] = fingerprint
    snapshots = job.directory / "snapshots"
    snapshots.mkdir(exist_ok=True)
    target = snapshots / f"{label}-{fingerprint}"
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=snapshots, prefix=".publishing-") as temporary:
            pending = Path(temporary) / "dataset"
            pending.mkdir()
            (pending / "recordings").mkdir()
            for rid, record in sorted(by_id.items()):
                atomic_json(pending / "recordings" / f"{rid}.json", record)
            atomic_json(pending / "profile.json", profile)
            atomic_json(pending / "credit_audit.json", credit_coverage(list(by_id.values())))
            if matches is not None:
                atomic_json(pending / "matches.json", matches)
            atomic_json(pending / "manifest.json", manifest)
            pending.rename(target)
    _, published_manifest = load_dataset(target)
    profile_favorites(target / "profile.json", published_manifest)
    job.state["datasets"][label] = str(target.relative_to(job.directory))
    job.save()
    return target


class LibraryWorkflow:
    def __init__(self, input_path: Path, output: Path, *, limits_path=ROOT / "config/full_library_limits.json",
                 matching_rules_path=ROOT / "config/matching_rules.json",
                 collection_rules_path=ROOT / "config/song_collection_limits.json",
                 apple_rules_path=ROOT / "config/apple_lookup_rules.json", weights_path=ROOT / "config/song_weights.json",
                 overrides_path=None, pilot=None, seed_graph=None, apple_snapshot=None,
                 reuse_cache=False, fresh_apple=False, resume=False, offline=False, contact=None, wait_for_job=False,
                 retry_failures=False, musicbrainz_cache=None, apple_cache=None, provider_options=None, progress=None):
        self.input_path, self.output = input_path, output
        self.tracks, self.metadata = load_input(input_path)
        self.config = load_configuration(limits_path)
        matching = read_json(matching_rules_path)
        if matching.pop("format_version") != 1:
            raise ValueError("Unsupported matching rules")
        self.match_rules = MatchRules(**{k: matching[k] for k in MatchRules.__dataclass_fields__})
        self.mb_limits = Limits(**{k: v for k, v in matching.items() if k not in MatchRules.__dataclass_fields__})
        self.apple_rules = load_apple_rules(apple_rules_path)
        self.weights = load_weights(weights_path)
        self.pilot, self.seed_graph, self.apple_snapshot = pilot, seed_graph, apple_snapshot
        self.overrides_path = overrides_path
        if offline and retry_failures:
            raise ValueError("Cannot retry failures offline")
        if fresh_apple and apple_snapshot:
            raise ValueError("A fresh Apple snapshot cannot import old Apple responses")
        if (musicbrainz_cache or apple_cache) and not reuse_cache:
            raise ValueError("Explicit external caches require --reuse-cache")
        self.mb_cache = musicbrainz_cache or (ROOT / "data/cache/musicbrainz" if reuse_cache else output / "raw/musicbrainz")
        self.apple_cache = apple_cache or (ROOT / "data/cache/apple_itunes" if reuse_cache and not fresh_apple else output / "raw/apple")
        self.resume, self.offline, self.contact = resume, offline, contact
        self.wait_for_job = wait_for_job
        self.retry_failures, self.provider_options, self.progress = retry_failures, provider_options or {}, progress
        self._rows = None
        self.binding = {"input_sha256": self.metadata["input_sha256"], "country": "DE",
                        "rules": {path.name: digest(path.read_bytes()) for path in
                                  (limits_path, matching_rules_path, collection_rules_path, apple_rules_path, weights_path)},
                        "credit_rules_sha256": digest(json_bytes(load_rules())),
                        "policy_overrides_sha256": digest(overrides_path.read_bytes()) if overrides_path else None,
                        "pilot": import_binding(pilot, ("manifest.json", "matches.json", "profile.json")),
                        "seed_graph": import_binding(seed_graph, ("manifest.json", "profile.json")),
                        "apple_snapshot": import_binding(apple_snapshot, ("availability.json",)),
                        "cache_policy": {"musicbrainz": str(self.mb_cache.resolve()), "apple": str(self.apple_cache.resolve()),
                                         "reuse_cache": reuse_cache, "fresh_apple": fresh_apple}}
        self.budgets = {stage: self.config[stage] for stage in ("matching", "discovery", "apple")}
        self.frozen_inputs = {"favorites.json": input_path, "full_library_limits.json": limits_path,
                              "matching_rules.json": matching_rules_path, "song_collection_limits.json": collection_rules_path,
                              "apple_lookup_rules.json": apple_rules_path, "song_weights.json": weights_path}
        if overrides_path:
            self.frozen_inputs["policy_overrides.json"] = overrides_path

    def client(self, job, stage):
        if stage == "apple":
            provider = AppleClient(self.apple_cache, self.apple_rules, offline=self.offline,
                                   retry_failures=self.retry_failures, **self.provider_options)
            provider.request_budget = self.config[stage]["total_attempts"] + 1
        else:
            values = asdict(self.mb_limits) | {"max_requests": self.config[stage]["total_attempts"]}
            provider = MusicBrainzClient(self.mb_cache, Limits(**values), offline=self.offline, contact=self.contact,
                                        retry_failures=self.retry_failures, **self.provider_options)
            provider.request_budget = self.config[stage]["total_attempts"] + 1
        return provider

    def row_path(self, line):
        return self.output / "rows" / f"{line}.json"

    def row_checkpoints(self):
        if self._rows is None:
            self._rows = {t["line_number"]: read_json(self.row_path(t["line_number"]))
                          for t in self.tracks if self.row_path(t["line_number"]).exists()}
        return self._rows

    def import_pilot(self, job):
        if not self.pilot or job.state.get("pilot_imported"):
            return
        records, manifest = load_dataset(self.pilot)
        if manifest.get("input_sha256") != self.metadata["input_sha256"] or manifest["rules"] != asdict(self.match_rules):
            raise ValueError("Pilot input or matching rules do not match this job")
        rows = read_json(self.pilot / "matches.json")
        metadata = {k: manifest[k] for k in ("input_sha256", "input_rows", "format_review_rows", "submitted_artists",
                                            "selection_sha256", "reviews_sha256") if k in manifest}
        if manifest["sample_id"] != digest(json_bytes({"metadata": metadata, "rules": manifest["rules"], "matches": rows})):
            raise ValueError("Pilot matching decisions fingerprint mismatch")
        profile_favorites(self.pilot / "profile.json", manifest)
        by_line = {t["line_number"]: t for t in self.tracks}
        by_id, sources = {r["id"]: r for r in records}, {s["recording_id"]: s for s in manifest["sources"]}
        for row in rows:
            line = row["source_row"]["line_number"]
            if row["source_row"] != by_line.get(line):
                raise ValueError("Pilot row does not match original source row")
            needed = {c["recording_id"] for c in row["candidates"] if c["lookup_status"] == "complete"}
            for candidate in row["candidates"]:
                if candidate["lookup_status"] == "complete" and candidate["source"]["sha256"] != sources[candidate["recording_id"]]["sha256"]:
                    raise ValueError("Pilot candidate snapshot hash mismatch")
            failures = [f for f in manifest["failures"] if f.get("context", {}).get("line_number") == line]
            checkpoint = {"row": row, "outcome": "failed" if failures else "processed", "failures": failures,
                          "records": [by_id[rid] for rid in sorted(needed)],
                          "sources": [sources[rid] for rid in sorted(needed)], "imported_pilot": True}
            existing = self.row_path(line)
            if existing.exists() and read_json(existing) != checkpoint:
                raise ValueError("Pilot import conflicts with existing row checkpoint")
            atomic_json(existing, checkpoint)
            self.row_checkpoints()[line] = checkpoint
        job.state["pilot_imported"] = True
        job.state["historical_pilot_attempts"] = manifest["network_attempts"]
        job.save()

    def match(self, job):
        self.import_pilot(job)
        checkpoints = self.row_checkpoints()
        if job.state.get("active_row") in checkpoints:
            job.state["active_row"] = None
        scheduled = [track for track in balanced_rows(self.tracks)
                     if track["line_number"] not in checkpoints or
                     (self.retry_failures and checkpoints[track["line_number"]]["outcome"] == "failed")]
        scratch = self.output / "scratch"
        scratch.mkdir(exist_ok=True)
        attempts_before = job.state["counters"]["matching"]["attempts"]
        observations = job.state.setdefault("matching_observations", {"additional_rows": 0, "elapsed_seconds": 0,
                                                                       "attempts_start": attempts_before})
        if scheduled:
            with self.client(job, "matching") as provider:
                client = CheckpointClient(provider, job, "matching")
                for track in scheduled:
                    client.events.clear()
                    row_started = time.monotonic()
                    line = track["line_number"]
                    job.state["active_row"] = line
                    job.state["stages"]["matching"] = "running"
                    job.save()
                    with tempfile.TemporaryDirectory(dir=scratch, prefix="row-") as temporary:
                        target = Path(temporary) / "result"
                        manifest = match_batch(client, [track], self.metadata, target, self.match_rules)
                        records, _ = load_dataset(target)
                        row = read_json(target / "matches.json")[0]
                        checkpoint = {"row": row, "outcome": "failed" if manifest["failures"] else "processed",
                                      "failures": manifest["failures"], "records": records, "sources": manifest["sources"]}
                        atomic_json(self.row_path(line), checkpoint)
                        self.row_checkpoints()[line] = checkpoint
                    job.state["active_row"] = None
                    if observations["additional_rows"] < 100:
                        observations["additional_rows"] += 1
                        observations["elapsed_seconds"] += time.monotonic() - row_started
                    if observations["additional_rows"] == 100 and "first_additional_100_rows" not in job.state:
                        elapsed = observations["elapsed_seconds"]
                        job.state["first_additional_100_rows"] = {
                            "rows": 100, "elapsed_seconds": elapsed,
                            "http_attempts": job.state["counters"]["matching"]["attempts"] - observations["attempts_start"],
                            "remaining_seconds_estimate": elapsed / 100 * (len(self.tracks) - len(self.row_checkpoints()))}
                    job.save()
                    if self.progress:
                        self.progress("matching", {"processed_rows": len(self.row_checkpoints()), "total_rows": len(self.tracks),
                                                   "last_status": row["status"], "attempts": job.state["counters"]["matching"]["attempts"]})
        checkpoints = self.row_checkpoints()
        job.state["stages"]["matching"] = ("complete" if len(checkpoints) == len(self.tracks) and
                                             all(c["outcome"] == "processed" for c in checkpoints.values()) else "incomplete")
        job.save()
        return self.consolidate(job)

    def consolidate(self, job):
        checkpoints = self.row_checkpoints()
        by_id, sources, rows, accepted = {}, {}, [], {}
        for track in sorted(self.tracks, key=lambda t: t["line_number"]):
            line = track["line_number"]
            checkpoint = checkpoints.get(line)
            if checkpoint is None:
                rows.append({"source_row": track, "status": "interrupted" if job.state.get("active_row") == line else "not_attempted",
                             "accepted_recording_id": None, "operational_outcome": "deferred"})
                continue
            row = checkpoint["row"] | {"operational_outcome": checkpoint["outcome"]}
            if row["source_row"] != track:
                raise ValueError("Row checkpoint belongs to a different source row")
            rows.append(row)
            for record, source in zip(checkpoint["records"], checkpoint["sources"], strict=True):
                rid = record["id"]
                if source["sha256"] != digest(json_bytes(record)):
                    raise ValueError("Row checkpoint snapshot checksum mismatch")
                if rid in by_id and by_id[rid] != record:
                    raise ValueError(f"Conflicting duplicate recording snapshots: {rid}")
                by_id[rid] = record
                sources.setdefault(rid, source)
            if checkpoint["outcome"] == "processed" and row["accepted_recording_id"]:
                accepted.setdefault(row["accepted_recording_id"], []).append(line)
        profile = {"format_version": 1, "input_sha256": self.metadata["input_sha256"],
                   "favorites": [{"recording_id": rid, "source_lines": sorted(lines), "source_sha256": sources[rid]["sha256"],
                                  "primary_artist_ids": sorted({c["artist"]["id"] for c in by_id[rid]["artist-credit"] if isinstance(c, dict)})}
                                 for rid, lines in sorted(accepted.items())],
                   "independent_human_audit": "pending", "unknown_cross_id_equivalence": True}
        profile["artist_registry"] = registry_for(list(by_id.values()), sorted(accepted), profile=profile,
                                                  input_path=self.input_path, overrides_path=self.overrides_path)
        status = self.coverage(job)
        path = publish_dataset(job, "matching", [by_id[rid] for rid in sorted(by_id)], [sources[rid] for rid in sorted(by_id)],
                               profile, {"collection_status": job.state["stages"].get("matching", "incomplete"),
                                         "matching_coverage": status["matching"]}, rows)
        atomic_json(path / "favorite_credit_coverage.json", credit_coverage([by_id[rid] for rid in sorted(accepted)]))
        return path, profile

    def apple(self, job, graph, profile):
        records, manifest = load_dataset(graph)
        favorites = profile_favorites(graph / "profile.json", manifest)
        unfiltered = recommendation_report(records, favorites, registry=profile["artist_registry"],
                                            weights=self.weights["role_weights"], saturation_k=self.weights["saturation_k"])
        skip = {s["recording_id"] for s in unfiltered["skipped_candidates"]
                if s["reason"] not in {"contributor_already_selected", "musician_already_selected", "familiar_collaboration_limit", "requested_limit_reached"}}
        # Include every policy-eligible positive-score candidate, including selection conflicts.
        candidate_ids = sorted(set(r["id"] for r in records) - set(favorites) - skip)
        destination = self.output / "apple"
        destination.mkdir(exist_ok=True)
        checkpoints = destination / "candidates"
        checkpoints.mkdir(exist_ok=True)
        frozen_fingerprint = dataset_fingerprint(records)
        binding = {"dataset_sha256": frozen_fingerprint, "rules": asdict(self.apple_rules), "candidate_ids": candidate_ids}
        binding_path = destination / "binding.json"
        if binding_path.exists() and read_json(binding_path) != binding:
            raise ValueError("Apple checkpoints belong to another frozen dataset")
        atomic_json(binding_path, binding)
        if self.apple_snapshot and not job.state.get("apple_responses_imported"):
            previous = read_json(self.apple_snapshot / "availability.json")
            if previous["country"] != "DE" or previous["rules"] != asdict(self.apple_rules):
                raise ValueError("Imported Apple responses have incompatible country or rules")
            # Import raw envelopes only; decisions must be recomputed for this dataset.
            for item in previous["recordings"]:
                for query in item["queries"]:
                    if query.get("cache_file"):
                        envelope = read_json(self.apple_snapshot / "responses" / query["cache_file"])
                        if (envelope["response_sha256"] != query["response_sha256"]
                                or digest(envelope["response_text"].encode()) != query["response_sha256"]
                                or envelope["query"] != query["query"]
                                or query["cache_file"] != digest(query["query"].encode()) + ".json"):
                            raise ValueError("Imported Apple response hash mismatch")
                        path = self.output / "operations/apple" / query["cache_file"]
                        if path.exists() and read_json(path) != envelope:
                            raise ValueError("Conflicting Apple response snapshots")
                        atomic_json(path, envelope)
            job.state["apple_responses_imported"] = True
            job.save()
        scratch = self.output / "scratch"
        scratch.mkdir(exist_ok=True)
        try:
            with self.client(job, "apple") as provider:
                client = CheckpointClient(provider, job, "apple")
                for rid in candidate_ids:
                    client.events.clear()
                    path = checkpoints / f"{rid}.json"
                    if path.exists() and not (self.retry_failures and read_json(path)["reason"] == "request_failure"):
                        continue
                    job.state["active_candidate"] = rid
                    job.save()
                    with tempfile.TemporaryDirectory(dir=scratch, prefix="apple-") as temporary:
                        report = collect_availability(client, records, [rid], rules=self.apple_rules,
                                                      output=Path(temporary) / "result", favorite_ids=favorites)
                        # Transport mode belongs to job accounting, not the frozen source evidence.
                        report["recordings"][0]["queries"] = [
                            {k: v for k, v in query.items() if k != "mode"}
                            for query in report["recordings"][0]["queries"]]
                        atomic_json(path, report["recordings"][0])
                    job.state["active_candidate"] = None
                    job.save()
                    if self.progress:
                        self.progress("apple", {"checked_candidates": len(list(checkpoints.glob("*.json"))),
                                                "total_candidates": len(candidate_ids), "last_reason": report["recordings"][0]["reason"]})
        finally:
            rows = [read_json(checkpoints / f"{rid}.json") for rid in candidate_ids if (checkpoints / f"{rid}.json").exists()]
            report = {"format_version": 1, "provider": "apple_itunes_search", "country": "DE", "dataset_sha256": frozen_fingerprint,
                      "rules": asdict(self.apple_rules), "rules_sha256": digest(json_bytes(asdict(self.apple_rules))),
                      "favorite_recording_ids": sorted(favorites), "recordings": rows,
                      "summary": {"candidates": len(candidate_ids), "checked": len(rows), "deferred": len(candidate_ids) - len(rows),
                                  "network_attempts": job.state["counters"]["apple"]["attempts"],
                                  "reason_counts": dict(Counter(r["reason"] for r in rows))}}
            validate_availability(report, records)
            for row in rows:
                for query in row["queries"]:
                    if query.get("cache_file"):
                        source = self.output / "operations/apple" / query["cache_file"]
                        atomic_bytes(destination / "responses" / query["cache_file"], source.read_bytes())
            atomic_json(destination / "availability.json", report)
        job.state["stages"]["apple"] = "complete" if len(rows) == len(candidate_ids) and not any(r["reason"] == "request_failure" for r in rows) else "incomplete"
        job.save()
        return report

    def export(self, job, graph, profile, availability):
        records, manifest = load_dataset(graph)
        favorites = profile_favorites(graph / "profile.json", manifest)
        target = self.output / "exports"
        if job.state["stages"].get("export") == "complete":
            return
        versions = [("weighted", self.weights["role_weights"], self.weights["saturation_k"], "none"),
                    ("equal", {c: 1.0 for c in CATEGORIES}, self.weights["saturation_k"], "none"),
                    ("weighted_without_saturation", self.weights["role_weights"], None, "none"),
                    ("weighted_contributor_diversity", self.weights["role_weights"], self.weights["saturation_k"], "contributors")]
        with tempfile.TemporaryDirectory(dir=self.output, prefix=".exporting-") as temporary:
            pending = Path(temporary) / "exports"
            pending.mkdir()
            for name, weights, k, diversity in versions:
                started = time.monotonic()
                report = recommendation_report(records, favorites, registry=profile["artist_registry"], weights=weights,
                                               saturation_k=k, diversity=diversity, availability=availability,
                                               limit=self.config["requested_songs"])
                report["input_coverage"] = self.coverage(job)["matching"]
                atomic_json(pending / f"recommendations_{name}.json", report)
                write_song_review(pending / f"SONG_REVIEW_{name}.md", report)
                with (pending / f"SONG_REVIEW_{name}.md").open("a") as handle:
                    handle.write(f"\nScoring profile: {len(favorites)} distinct accepted recordings; "
                                 f"{report['input_coverage']['accepted_rows']}/{len(self.tracks)} supplied rows accepted.\n")
                if name == "weighted":
                    write_playlist_preparation(pending / "playlist_preparation.json", report)
                    job.state["selection_summary"] = report["selection_summary"]
                    job.state["selection_exclusions"] = dict(Counter(s["reason"] for s in report["skipped_candidates"]))
                job.state.setdefault("local_scoring", {})[name] = {
                    "elapsed_seconds": time.monotonic() - started,
                    "output_bytes": (pending / f"recommendations_{name}.json").stat().st_size}
            if not target.exists():
                pending.rename(target)
            else:
                # A crash after the atomic directory publication needs only pointer repair.
                if any((target / path.name).read_bytes() != path.read_bytes() for path in pending.iterdir()):
                    fingerprint = digest(json_bytes({"dataset": dataset_fingerprint(records), "availability": availability}))
                    target = self.output / f"exports-{fingerprint}"
                    if not target.exists():
                        pending.rename(target)
                    elif any((target / path.name).read_bytes() != path.read_bytes() for path in pending.iterdir()):
                        raise ValueError("Published exports conflict with deterministic replay")
        job.state["exports_directory"] = str(target.relative_to(self.output))
        job.state["stages"]["export"] = "complete"
        job.save()

    def coverage(self, job):
        checkpoints = self.row_checkpoints()
        processed = [c for c in checkpoints.values() if c["outcome"] == "processed"]
        accepted = [c["row"] for c in processed if c["row"]["accepted_recording_id"]]
        recordings = {r["accepted_recording_id"] for r in accepted}
        artists = {credit["artist"]["id"] for c in processed for record in c["records"]
                   if record["id"] in recordings for credit in record["artist-credit"] if isinstance(credit, dict)}
        status = {"input_rows": len(self.tracks), "format_review_rows": self.metadata["format_review_rows"],
                  "stages": job.state["stages"], "matching": {
                      "processed_rows": len(processed), "attempted_rows": len(checkpoints), "accepted_rows": len(accepted),
                      "accepted_recordings": len(recordings), "accepted_artists": len(artists),
                      "unresolved_rows": len(processed) - len(accepted), "failed_rows": len(checkpoints) - len(processed),
                      "not_attempted_rows": len(self.tracks) - len(checkpoints) - int(job.state.get("active_row") is not None and job.state["active_row"] not in checkpoints),
                      "interrupted_rows": int(job.state.get("active_row") is not None and job.state["active_row"] not in checkpoints
                                              and not getattr(job, "collector_active", False)),
                      "in_progress_rows": int(job.state.get("active_row") is not None and job.state["active_row"] not in checkpoints
                                              and getattr(job, "collector_active", False)),
                      "statuses": dict(Counter(c["row"]["status"] for c in processed)),
                      "terminal_outcomes": dict(Counter(
                          c["row"]["status"] if c["row"]["status"] in {"accepted", "no_result"} else
                          "ambiguous" if sum(candidate["qualifies"] for candidate in c["row"]["candidates"]) > 1 else "no_confident_match"
                          for c in processed)),
                      "failure_causes": dict(Counter(f["error"] for c in checkpoints.values() for f in c["failures"]))},
                  "requests": {stage: counter | {"remaining_attempts": self.budgets[stage]["total_attempts"] - counter["attempts"]}
                               for stage, counter in job.state["counters"].items()},
                  "datasets": job.state["datasets"], "independent_precision_audit": "pending", "listening_quality": "pending"}
        if "matching" in job.state["datasets"]:
            path = self.output / job.state["datasets"]["matching"] / "favorite_credit_coverage.json"
            if path.exists():
                credits = read_json(path)
                status["credits"] = {key: value for key, value in credits.items() if key != "recordings"} | {
                    "recordings_with_detailed_performance": sum(r["detailed_performance_credits_observed"] for r in credits["recordings"])}
        path = self.output / "discovery_state.json"
        if path.exists():
            state = read_json(path)
            status["discovery"] = state.get("summary", {"eligible_candidates": len(state["eligible_ids"]),
                                                        "explored_routes": sum(r["initialized"] for r in state["routes"].values()),
                                                        "frontier_routes": len(state["order"])})
        path = self.output / "apple/availability.json"
        if path.exists():
            status["apple"] = read_json(path)["summary"]
        for key in ("selection_summary", "selection_exclusions", "local_scoring", "first_additional_100_rows", "exports_directory", "offline_replay"):
            if key in job.state:
                status[key] = job.state[key]
        return status

    def run(self, *, stage="all", status_only=False):
        with LibraryJob(self.output, self.binding, self.budgets, resume=self.resume, wait=self.wait_for_job) as job:
            if status_only:
                return self.coverage(job)
            for name, source in self.frozen_inputs.items():
                destination = self.output / "inputs" / name
                raw = source.read_bytes()
                if destination.exists() and destination.read_bytes() != raw:
                    raise ValueError("Frozen input or rules changed")
                if not destination.exists():
                    atomic_bytes(destination, raw)
            try:
                matching, profile = self.match(job)
                # Explicit failure retry enables two additional persisted passes;
                # the first conservative pass always finishes before these start.
                while (self.retry_failures and job.state["stages"]["matching"] == "incomplete"
                       and job.state.get("matching_failure_passes", 0) < 2):
                    job.state["matching_failure_passes"] = job.state.get("matching_failure_passes", 0) + 1
                    job.save()
                    matching, profile = self.match(job)
                if stage == "matching" or job.state["stages"]["matching"] != "complete":
                    return self.coverage(job)
                if self.retry_failures and "discovery" in job.state["datasets"] and read_json(self.output / "discovery_state.json")["failures"]:
                    job.state.setdefault("dataset_history", []).append(job.state["datasets"].pop("discovery"))
                    job.state["stages"].pop("export", None)
                    # Apple candidate decisions must be rebound when the graph changes.
                    old_apple = self.output / "apple"
                    if old_apple.exists():
                        old_apple.rename(self.output / f"apple-history-{len(job.state['dataset_history'])}")
                    job.save()
                if "discovery" in job.state["datasets"]:
                    graph = self.output / job.state["datasets"]["discovery"]
                else:
                    discovery_budget = False
                    with self.client(job, "discovery") as provider:
                        try:
                            records, sources, state = discover(job, CheckpointClient(provider, job, "discovery"), matching,
                                                               profile, self.config["discovery_rules"], self.seed_graph, self.progress,
                                                               retry_failures=self.retry_failures)
                        except StageBudgetReached:
                            discovery_budget = True
                            records, sources, state = discovery_snapshot(job, profile)
                    graph = publish_dataset(job, "discovery", records, sources, profile,
                                            {"discovery_summary": state["summary"], "selections": list(state["routes"].values()),
                                             "exclusions": state["exclusions"], "failures": state["failures"],
                                             "collection_status": "complete_with_declared_limits" if not state["failures"] else "partial"})
                    job.state["stages"]["discovery"] = ("budget_exhausted" if discovery_budget else
                                                        "complete_with_declared_limits" if not state["failures"] else "incomplete")
                    job.save()
                if stage == "discovery":
                    return self.coverage(job)
                availability = self.apple(job, graph, profile)
                if stage != "apple":
                    self.export(job, graph, profile, availability)
            except StageBudgetReached:
                if job.state["stages"].get("matching") == "budget_exhausted":
                    self.consolidate(job)
                elif job.state["stages"].get("apple") == "budget_exhausted" and stage != "apple":
                    self.export(job, graph, profile, read_json(self.output / "apple/availability.json"))
            finally:
                atomic_json(self.output / "coverage.json", self.coverage(job))
            return self.coverage(job)

    def verify_offline(self, status):
        if (status["stages"].get("matching") != "complete"
                or status["stages"].get("discovery") != "complete_with_declared_limits"
                or status["stages"].get("apple") != "complete" or status["stages"].get("export") != "complete"):
            return status
        replay_directory = self.output / "offline_replay"
        replay = LibraryWorkflow(
            self.output / "inputs/favorites.json", replay_directory,
            limits_path=self.output / "inputs/full_library_limits.json",
            matching_rules_path=self.output / "inputs/matching_rules.json",
            collection_rules_path=self.output / "inputs/song_collection_limits.json",
            apple_rules_path=self.output / "inputs/apple_lookup_rules.json", weights_path=self.output / "inputs/song_weights.json",
            overrides_path=self.output / "inputs/policy_overrides.json" if self.overrides_path else None,
            pilot=self.pilot, seed_graph=self.seed_graph, offline=True, reuse_cache=True,
            musicbrainz_cache=self.output / "operations/musicbrainz", apple_cache=self.output / "operations/apple",
            resume=(replay_directory / "manifest.json").exists(), provider_options=self.provider_options)
        replay_status = replay.run()
        attempts = sum(counter["attempts"] for counter in replay_status["requests"].values())
        if attempts or replay_status["matching"]["processed_rows"] != len(self.tracks):
            raise ValueError("Offline replay is incomplete or sent requests")
        checks = {}
        for dataset in ("matching", "discovery"):
            first = self.output / status["datasets"][dataset]
            second = replay_directory / replay_status["datasets"][dataset]
            if read_json(first / "profile.json") != read_json(second / "profile.json"):
                raise ValueError("Offline profile replay differs")
            records, _ = load_dataset(first)
            replay_records, _ = load_dataset(second)
            if dataset_fingerprint(records) != dataset_fingerprint(replay_records):
                raise ValueError("Offline recording snapshot replay differs")
        first_matches = self.output / status["datasets"]["matching"] / "matches.json"
        replay_matches = replay_directory / replay_status["datasets"]["matching"] / "matches.json"
        if read_json(first_matches) != read_json(replay_matches):
            raise ValueError("Offline matching decisions differ")
        for filename in ("recommendations_weighted.json", "recommendations_equal.json",
                         "recommendations_weighted_without_saturation.json", "recommendations_weighted_contributor_diversity.json",
                         "playlist_preparation.json"):
            first = self.output / status["exports_directory"] / filename
            second = replay_directory / replay_status["exports_directory"] / filename
            if first.read_bytes() != second.read_bytes():
                raise ValueError(f"Offline replay differs: {filename}")
            checks[filename] = digest(first.read_bytes())
        verification = {"status": "verified", "http_attempts": attempts, "artifact_sha256": checks,
                        "matching_decisions_sha256": digest(first_matches.read_bytes())}
        atomic_json(self.output / "offline_verification.json", verification)
        with LibraryJob(self.output, self.binding, self.budgets, resume=True) as job:
            job.state["offline_replay"] = verification
            job.save()
            status = self.coverage(job)
            atomic_json(self.output / "coverage.json", status)
        return status


def read_status(output: Path):
    """Read atomic checkpoints while a collector holds the job lock."""
    state = read_json(output / "manifest.json")
    workflow = LibraryWorkflow.__new__(LibraryWorkflow)
    workflow.output, workflow._rows = output, None
    workflow.tracks, workflow.metadata = load_input(output / "inputs/favorites.json")
    if workflow.metadata["input_sha256"] != state["binding"]["input_sha256"]:
        raise ValueError("Frozen favorites input checksum mismatch")
    workflow.budgets = state["request_limits"]
    collector_active = False
    with (output / ".job.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            collector_active = True
    return workflow.coverage(SimpleNamespace(state=state, collector_active=collector_active))


def write_coverage_report(path: Path, status: dict):
    matching = status["matching"]
    lines = ["# Full-library collection coverage", "", f"Updated: {utc_now()}.", "",
             "These counts describe collection coverage. Independent identity precision and listening quality remain pending.", "",
             f"Supplied rows: {status['input_rows']}; processed: {matching['processed_rows']}; accepted rows: {matching['accepted_rows']}; "
             f"distinct accepted recordings: {matching['accepted_recordings']}; accepted primary artists: {matching['accepted_artists']}.",
             f"Unresolved: {matching['unresolved_rows']}; operational failures: {matching['failed_rows']}; "
             f"not attempted: {matching['not_attempted_rows']}; in progress: {matching['in_progress_rows']}; interrupted: {matching['interrupted_rows']}.", "",
             "Stage states: " + "; ".join(f"{stage}: {value}" for stage, value in status["stages"].items()) + ".", "",
             "| Provider stage | Attempts | Remaining allowance | Tranches started |", "|---|---:|---:|---:|"]
    for stage, counters in status["requests"].items():
        lines.append(f"| {stage} | {counters['attempts']} | {counters['remaining_attempts']} | {counters['tranche']} |")
    for key in ("credits", "discovery", "apple", "selection_summary", "selection_exclusions", "first_additional_100_rows", "offline_replay"):
        if key in status:
            lines += ["", f"{key.replace('_', ' ').capitalize()}:", "", "```json", json.dumps(status[key], indent=2), "```"]
    lines += ["", "Matching, credit, discovery, availability, recommendations, and ordered playlist preparation remain in the ignored private job directory.", ""]
    atomic_bytes(path, "\n".join(lines).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/private/favorites.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limits", type=Path, default=ROOT / "config/full_library_limits.json")
    parser.add_argument("--policy-overrides", type=Path)
    parser.add_argument("--import-pilot", type=Path)
    parser.add_argument("--seed-graph", type=Path)
    parser.add_argument("--apple-snapshot", type=Path)
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--fresh-apple", action="store_true")
    parser.add_argument("--musicbrainz-cache", type=Path)
    parser.add_argument("--apple-cache", type=Path)
    parser.add_argument("--contact-file", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--wait-for-job", action="store_true", help="Wait for an active collector, then resume its checkpoints")
    parser.add_argument("--report", type=Path, help="Publish an aggregate coverage report after this invocation")
    parser.add_argument("--verify-offline", action="store_true", help="Replay a completed job and verify identical decisions and exports")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--stage", choices=["all", "matching", "discovery", "apple", "export"], default="all")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    try:
        if args.status:
            status = read_status(args.output)
            if args.report:
                write_coverage_report(args.report, status)
            print(json.dumps(status, indent=2))
            return
        workflow = LibraryWorkflow(args.input, args.output, limits_path=args.limits, overrides_path=args.policy_overrides,
                                   pilot=args.import_pilot, seed_graph=args.seed_graph, apple_snapshot=args.apple_snapshot,
                                   reuse_cache=args.reuse_cache, fresh_apple=args.fresh_apple,
                                   musicbrainz_cache=args.musicbrainz_cache, apple_cache=args.apple_cache,
                                   resume=args.resume or args.status, offline=args.offline,
                                   wait_for_job=args.wait_for_job,
                                   retry_failures=args.retry_failures,
                                   contact=args.contact_file.read_text().strip() if args.contact_file else None,
                                   progress=lambda stage, counts: print(json.dumps({"stage": stage, **counts}), flush=True))
        status = workflow.run(stage=args.stage, status_only=args.status)
        if args.verify_offline:
            status = workflow.verify_offline(status)
        if args.report:
            write_coverage_report(args.report, status)
        print(json.dumps(status, indent=2))
        if not args.status and (status["matching"]["processed_rows"] != status["input_rows"] or
                               any(v in {"incomplete", "budget_exhausted"} for v in status["stages"].values())):
            raise SystemExit(2)
    except (OSError, ValueError, KeyError, TypeError, FetchError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
