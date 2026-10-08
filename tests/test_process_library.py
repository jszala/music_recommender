"""Full-library durability and breadth checks use synthetic providers only."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from src.apple_music import dataset_fingerprint, validate_availability
from src.build_graph import load_dataset
from src.fetch_musicbrainz import Limits, MusicBrainzClient, digest, json_bytes
from src.library_job import CheckpointClient, LibraryJob, atomic_json, balanced_rows, read_json
from src.match_recordings import MatchRules, match_batch, search_query
from src.process_library import LibraryWorkflow, load_configuration, read_status
from src.recommend_songs import profile_favorites
from test_fetch_musicbrainz import FakeClock, Response, identifier
from test_match_recordings import ARTIST, ENGINEER, ENGINEERING, R1, TRACK, recording


class LibraryTransport:
    def __init__(self):
        self.second_artist = {"id": identifier(201), "name": "Second favorite act"}
        self.second_engineer = {"id": identifier(202), "name": "Second engineer"}
        self.r2, self.c1, self.c2 = identifier(211), identifier(301), identifier(302)
        self.tracks = [deepcopy(TRACK), TRACK | {"line_number": 2, "artist_text": self.second_artist["name"], "song_text": "Second favorite"},
                       TRACK | {"line_number": 3}, TRACK | {"line_number": 4, "artist_text": "Unresolved input act", "song_text": "Unknown"}]
        def make(rid, title, artist, engineer):
            return recording(rid, title=title, **{"artist-credit": [{"artist": artist}], "relations": [
                {"target-type": "artist", "artist": engineer, "type-id": ENGINEERING, "type": "engineer"}]})
        self.records = {R1: make(R1, TRACK["song_text"], ARTIST, ENGINEER),
                        self.r2: make(self.r2, "Second favorite", self.second_artist, self.second_engineer),
                        self.c1: make(self.c1, "Discovery one", {"id": identifier(401), "name": "New act one"}, ENGINEER),
                        self.c2: make(self.c2, "Discovery two", {"id": identifier(402), "name": "New act two"}, self.second_engineer)}
        self.calls, self.crash_at, self.fail_at, self.on_send = [], None, None, None

    def __call__(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        if self.on_send:
            self.on_send(url)
        if len(self.calls) == self.crash_at:
            raise KeyboardInterrupt("synthetic interruption during transport")
        if len(self.calls) == self.fail_at:
            raise URLError("synthetic transient error")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if parsed.netloc == "itunes.apple.com":
            record = next(r for r in self.records.values() if r["title"].casefold() in params["term"][0])
            track = {"wrapperType": "track", "kind": "song", "trackId": int(record["id"][-12:]) + 100,
                     "artistName": record["artist-credit"][0]["artist"]["name"], "trackName": record["title"],
                     "collectionName": "Synthetic album", "trackTimeMillis": 180000, "isStreamable": True,
                     "trackViewUrl": "https://music.apple.com/de/album/synthetic/123?i=456"}
            return Response({"resultCount": 1, "results": [track]})
        endpoint = parsed.path.removeprefix("/ws/2/")
        if endpoint.startswith("recording/"):
            return Response(self.records[endpoint.split("/")[1]])
        if endpoint.startswith("artist/"):
            aid = endpoint.split("/")[1]
            return Response({"id": aid, "relations": []})
        if "query" in params:
            track = next(t for t in self.tracks if search_query(t) == params["query"][0])
            found = [r for r in self.records.values() if r["title"] == track["song_text"]]
            return Response({"count": len(found), "offset": 0, "recordings": found})
        aid, offset, size = params["artist"][0], int(params["offset"][0]), int(params["limit"][0])
        # Familiar-act metadata on page one must be filtered before a detail lookup.
        pool = ({ENGINEER["id"]: [self.records[R1], self.records[self.c1]],
                 self.second_engineer["id"]: [self.records[self.r2], self.records[self.c2]]}).get(aid, [])
        return Response({"recording-count": len(pool), "recording-offset": offset, "recordings": pool[offset:offset + size]})


class FullLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.transport, self.clock = LibraryTransport(), FakeClock()
        self.input = self.root / "favorites.json"
        atomic_json(self.input, {"format_version": 1, "tracks": self.transport.tracks, "needs_review": []})
        self.limits = self.root / "limits.json"
        self.config = load_configuration(Path(__file__).resolve().parents[1] / "config/full_library_limits.json")
        for stage in ("matching", "discovery", "apple"):
            self.config[stage] = {"tranche_attempts": 1, "total_attempts": 100}
        self.config["discovery_rules"].update(candidate_target=2, minimum_routes=4, browse_page_size=1)
        atomic_json(self.limits, self.config)

    def workflow(self, name="job", **kwargs):
        return LibraryWorkflow(self.input, self.root / name, limits_path=self.limits,
                               contact="test@project.invalid", provider_options={"opener": self.transport,
                               "clock": self.clock.time, "sleep": self.clock.sleep}, **kwargs)

    def test_end_to_end_multiple_tranches_full_profile_and_offline_replay(self):
        status = self.workflow().run()
        self.assertEqual(status["matching"]["processed_rows"], 4)
        self.assertEqual(status["matching"]["accepted_rows"], 3)
        self.assertEqual(status["matching"]["accepted_recordings"], 2)
        self.assertEqual(status["matching"]["statuses"]["no_result"], 1)
        self.assertEqual(status["selection_summary"]["returned"], 2)
        self.assertEqual(status["selection_summary"]["shortfall"], 8)
        for stage in ("matching", "discovery", "apple"):
            self.assertGreater(status["requests"][stage]["tranche"], 1)
        profile = read_json(self.root / "job" / status["datasets"]["matching"] / "profile.json")
        self.assertEqual(next(f["source_lines"] for f in profile["favorites"] if f["recording_id"] == R1), [1, 3])
        self.assertEqual(len(profile["artist_registry"]["submitted_names"]), 3)
        original = read_json(self.root / "job/exports/recommendations_weighted.json")
        self.assertEqual(original["selection_summary"]["repeated_explanatory_contributors"], 0)
        self.assertEqual(original["selection_summary"]["repeated_observed_musicians"], 0)
        for row in original["recommendations"]:
            self.assertAlmostEqual(row["score"], sum(c["value"] for c in row["contributions"]))
        sends = len(self.transport.calls)
        with patch("socket.socket", side_effect=AssertionError("offline must not open a socket")):
            replay = self.workflow("replay", offline=True, reuse_cache=True,
                                   musicbrainz_cache=self.root / "job/raw/musicbrainz", apple_cache=self.root / "job/raw/apple").run()
        self.assertEqual(len(self.transport.calls), sends)
        self.assertEqual(sum(c["attempts"] for c in replay["requests"].values()), 0)
        for name in ("weighted", "equal", "weighted_without_saturation", "weighted_contributor_diversity"):
            self.assertEqual(read_json(self.root / f"job/exports/recommendations_{name}.json"),
                             read_json(self.root / f"replay/exports/recommendations_{name}.json"))
        self.assertEqual((self.root / "job/exports/playlist_preparation.json").read_bytes(),
                         (self.root / "replay/exports/playlist_preparation.json").read_bytes())

    def test_send_debit_survives_crash_and_completed_operations_are_not_resent(self):
        workflow = self.workflow()
        def assert_debit(url):
            state = read_json(workflow.output / "manifest.json")
            self.assertEqual(state["active_operation"]["query"], url)
            self.assertGreater(state["counters"]["matching"]["attempts"], 0)
        self.transport.on_send = assert_debit
        self.transport.crash_at = 2
        with self.assertRaises(KeyboardInterrupt):
            workflow.run(stage="matching")
        status = self.workflow(resume=True).run(status_only=True)
        self.assertEqual(status["requests"]["matching"]["attempts"], 2)
        self.assertEqual(status["matching"]["interrupted_rows"], 1)
        self.transport.on_send, self.transport.crash_at = None, None
        status = self.workflow(resume=True).run(stage="matching")
        self.assertEqual(status["matching"]["processed_rows"], 4)
        self.assertEqual(self.transport.calls.count(self.transport.calls[0]), 1)
        self.assertEqual(status["requests"]["matching"]["attempts"], len(self.transport.calls))

    def test_crash_between_row_commit_and_cursor_clear_repairs_without_requests(self):
        import src.process_library as module
        original = module.atomic_json
        def crash(path, value):
            original(path, value)
            if path.parent.name == "rows":
                raise KeyboardInterrupt("after durable row commit")
        with patch.object(module, "atomic_json", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.workflow().run(stage="matching")
        completed_url = self.transport.calls[0]
        self.workflow(resume=True).run(stage="matching")
        self.assertEqual(self.transport.calls.count(completed_url), 1)

    def test_cumulative_total_cannot_reset_on_resume(self):
        self.config["matching"] = {"tranche_attempts": 1, "total_attempts": 1}
        atomic_json(self.limits, self.config)
        first = self.workflow().run()
        self.assertEqual(first["stages"]["matching"], "budget_exhausted")
        second = self.workflow(resume=True).run()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(second["requests"]["matching"]["remaining_attempts"], 0)
        self.assertEqual(second["matching"]["processed_rows"], 0)
        self.assertNotIn("export", second["stages"])

    def test_retry_is_charged_and_automatically_crosses_tranches(self):
        self.transport.fail_at = 1
        status = self.workflow().run(stage="matching")
        self.assertEqual(status["matching"]["processed_rows"], 4)
        self.assertEqual(status["requests"]["matching"]["attempts"], len(self.transport.calls))
        self.assertEqual(self.transport.calls[0], self.transport.calls[1])

    def test_changed_input_or_rules_cannot_resume(self):
        self.workflow().run(stage="matching")
        self.config["requested_songs"] = 5
        atomic_json(self.limits, self.config)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.workflow(resume=True).run()
        self.config["requested_songs"] = 10
        atomic_json(self.limits, self.config)
        data = read_json(self.input)
        data["tracks"][0]["song_text"] = "Changed"
        atomic_json(self.input, data)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.workflow(resume=True).run()

    def test_job_lock_and_temporary_files(self):
        workflow = self.workflow()
        with LibraryJob(workflow.output, workflow.binding, workflow.budgets) as job:
            atomic_json(workflow.output / "rows/1.json.tmp", {"incomplete": True})
            with self.assertRaises(BlockingIOError):
                with LibraryJob(workflow.output, workflow.binding, workflow.budgets, resume=True):
                    pass
            self.assertEqual(workflow.coverage(job)["matching"]["attempted_rows"], 0)

    def test_discovery_paging_refills_and_breadth_before_depth(self):
        status = self.workflow().run(stage="discovery")
        state = read_json(self.root / "job/discovery_state.json")
        self.assertEqual(state["summary"]["explored_routes"], 4)
        engineer_route = state["routes"][ENGINEER["id"]]
        self.assertEqual([p["offset"] for p in engineer_route["pages"]], [0, 1])
        self.assertEqual(engineer_route["candidate_lookups"], 1)
        self.assertEqual(state["summary"]["eligible_candidates"], 2)
        detail_urls = [u for u in self.transport.calls if "/recording/" in u]
        self.assertEqual(sum(f"/recording/{R1}?" in u for u in detail_urls), 1)
        self.assertEqual(state["round"], 1)
        self.assertEqual(status["stages"]["discovery"], "complete_with_declared_limits")

    def test_discovery_interruption_reuses_first_page_and_pending_lookup(self):
        self.workflow().run(stage="matching")
        self.transport.crash_at = len(self.transport.calls) + 4
        with self.assertRaises(KeyboardInterrupt):
            self.workflow(resume=True).run(stage="discovery")
        completed = self.transport.calls[-2]
        self.transport.crash_at = None
        status = self.workflow(resume=True).run(stage="discovery")
        self.assertEqual(status["discovery"]["eligible_candidates"], 2)
        self.assertEqual(self.transport.calls.count(completed), 1)

    def test_apple_interruption_rebinds_and_resumes_without_rechecking_completed_candidate(self):
        self.workflow().run(stage="discovery")
        self.transport.crash_at = len(self.transport.calls) + 2
        with self.assertRaises(KeyboardInterrupt):
            self.workflow(resume=True).run()
        completed = self.transport.calls[-2]
        self.transport.crash_at = None
        status = self.workflow(resume=True).run()
        self.assertEqual(status["apple"]["checked"], 2)
        self.assertEqual(self.transport.calls.count(completed), 1)
        records, _ = load_dataset(self.root / "job" / status["datasets"]["discovery"])
        report = read_json(self.root / "job/apple/availability.json")
        self.assertEqual(report["dataset_sha256"], dataset_fingerprint(records))
        with self.assertRaisesRegex(ValueError, "snapshots"):
            validate_availability(report, records[:-1])

    def test_pilot_import_preserves_decisions_and_duplicate_row_evidence(self):
        workflow = self.workflow()
        pilot = self.root / "pilot"
        with MusicBrainzClient(self.root / "pilot-cache", Limits(), contact="test@project.invalid",
                              opener=self.transport, clock=self.clock.time, sleep=self.clock.sleep) as client:
            match_batch(client, workflow.tracks, workflow.metadata, pilot, MatchRules())
        sends = len(self.transport.calls)
        status = self.workflow(pilot=pilot).run(stage="matching")
        self.assertEqual(len(self.transport.calls), sends)
        self.assertEqual(status["matching"]["processed_rows"], 4)
        self.assertEqual(status["matching"]["accepted_recordings"], 2)
        rows = read_json(self.root / "job" / status["datasets"]["matching"] / "matches.json")
        for original, consolidated in zip(read_json(pilot / "matches.json"), rows):
            self.assertEqual(original, {k: v for k, v in consolidated.items() if k != "operational_outcome"})

    def test_conflicting_duplicate_snapshots_are_rejected(self):
        status = self.workflow().run(stage="matching")
        path = self.root / "job/rows/3.json"
        checkpoint = read_json(path)
        checkpoint["records"][0]["title"] = "Different frozen title"
        checkpoint["sources"][0]["sha256"] = digest(json_bytes(checkpoint["records"][0]))
        atomic_json(path, checkpoint)
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            self.workflow(resume=True).run(stage="matching")

    def test_atomic_snapshot_publication_can_resume_after_interruption(self):
        original = Path.rename
        def crash(path, target):
            if path.name == "dataset":
                raise KeyboardInterrupt("before dataset directory publication")
            return original(path, target)
        with patch.object(Path, "rename", autospec=True, side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.workflow().run(stage="matching")
        sends = len(self.transport.calls)
        status = self.workflow(resume=True).run(stage="matching")
        self.assertEqual(len(self.transport.calls), sends)
        records, manifest = load_dataset(self.root / "job" / status["datasets"]["matching"])
        self.assertEqual(len(profile_favorites(self.root / "job" / status["datasets"]["matching"] / "profile.json", manifest)), 2)

    def test_row_schedule_spreads_artist_groups(self):
        tracks = [TRACK | {"line_number": n, "artist_text": artist} for n, artist in [(1, "A"), (2, "A"), (3, "B"), (4, "C"), (5, "B")]]
        self.assertEqual([t["line_number"] for t in balanced_rows(tracks)], [1, 3, 4, 2, 5])

    def test_status_is_readable_while_the_job_is_locked(self):
        workflow = self.workflow()
        with LibraryJob(workflow.output, workflow.binding, workflow.budgets):
            atomic_json(workflow.output / "inputs/favorites.json", read_json(self.input))
            status = read_status(workflow.output)
            self.assertEqual(status["matching"]["not_attempted_rows"], 4)
            self.assertEqual(status["requests"]["matching"]["remaining_attempts"], 100)

    def test_discovery_budget_preserves_partial_graph_and_exports_shortfall(self):
        self.config["discovery"] = {"tranche_attempts": 1, "total_attempts": 1}
        atomic_json(self.limits, self.config)
        status = self.workflow().run()
        self.assertEqual(status["stages"]["discovery"], "budget_exhausted")
        records, _ = load_dataset(self.root / "job" / status["datasets"]["discovery"])
        self.assertEqual({r["id"] for r in records}, {R1, self.transport.r2})
        self.assertEqual(status["selection_summary"]["shortfall"], 10)
        self.assertEqual(status["requests"]["discovery"]["attempts"], 1)

    def test_apple_budget_exports_only_completed_available_candidates(self):
        self.config["apple"] = {"tranche_attempts": 1, "total_attempts": 1}
        atomic_json(self.limits, self.config)
        status = self.workflow().run()
        self.assertEqual(status["stages"]["apple"], "budget_exhausted")
        self.assertEqual(status["apple"]["checked"], 1)
        self.assertEqual(status["apple"]["deferred"], 1)
        self.assertEqual(status["selection_summary"]["returned"], 1)
        self.assertEqual(status["selection_summary"]["shortfall"], 9)

    def test_apple_can_cross_the_original_60_attempt_limit(self):
        workflow = self.workflow()
        workflow.config["apple"] = workflow.budgets["apple"] = {"tranche_attempts": 60, "total_attempts": 100}
        with LibraryJob(workflow.output, workflow.binding, workflow.budgets) as job:
            with workflow.client(job, "apple") as provider:
                provider.opener = lambda request, timeout: Response({"resultCount": 0, "results": []})
                client = CheckpointClient(provider, job, "apple")
                for index in range(65):
                    client.search(str(index), "DE", workflow.apple_rules)
                self.assertEqual(job.state["counters"]["apple"]["attempts"], 65)
                self.assertEqual(job.state["counters"]["apple"]["tranche"], 2)
                self.assertEqual(provider.limits.max_requests, 60)

    def test_failed_discovery_route_can_resume_using_frozen_successes(self):
        original = LibraryTransport.__call__
        def failed(transport, request, timeout):
            if f"/recording/{transport.c1}?" in request.full_url:
                transport.calls.append(request.full_url)
                raise URLError("temporary discovery failure")
            return original(transport, request, timeout)
        with patch.object(LibraryTransport, "__call__", failed):
            first = self.workflow().run()
        self.assertEqual(first["stages"]["discovery"], "incomplete")
        self.assertEqual(first["selection_summary"]["returned"], 1)
        original_search = self.transport.calls[0]
        second = self.workflow(resume=True, retry_failures=True).run()
        self.assertEqual(second["stages"]["discovery"], "complete_with_declared_limits")
        self.assertEqual(second["selection_summary"]["returned"], 2)
        self.assertEqual(self.transport.calls.count(original_search), 1)
        self.assertNotEqual(second["exports_directory"], "exports")
        self.assertEqual(read_json(self.root / "job/exports/recommendations_weighted.json")["selection_summary"]["returned"], 1)

    def test_compatible_apple_responses_are_recomputed_for_an_expanded_dataset(self):
        old_status = self.workflow().run()
        old_report = read_json(self.root / "job/apple/availability.json")
        new_id = identifier(501)
        new_track = TRACK | {"line_number": 5, "song_text": "Third favorite", "artist_text": "Third favorite act"}
        self.transport.tracks.append(new_track)
        self.transport.records[new_id] = recording(new_id, title=new_track["song_text"], **{
            "artist-credit": [{"artist": {"id": identifier(502), "name": new_track["artist_text"]}}],
            "relations": [{"target-type": "artist", "artist": ENGINEER, "type-id": ENGINEERING, "type": "engineer"}]})
        atomic_json(self.input, {"format_version": 1, "tracks": self.transport.tracks})
        apple_calls = sum("itunes.apple.com" in url for url in self.transport.calls)
        status = self.workflow("expanded", apple_snapshot=self.root / "job/apple").run()
        records, _ = load_dataset(self.root / "expanded" / status["datasets"]["discovery"])
        with self.assertRaisesRegex(ValueError, "snapshots"):
            validate_availability(old_report, records)
        self.assertEqual(status["matching"]["accepted_recordings"], 3)
        self.assertEqual(status["requests"]["apple"]["attempts"], 0)
        self.assertEqual(sum("itunes.apple.com" in url for url in self.transport.calls), apple_calls)

    def test_frontier_exhaustion_exposes_unmet_targets(self):
        self.config["discovery_rules"].update(candidate_target=500, minimum_routes=100)
        atomic_json(self.limits, self.config)
        status = self.workflow().run(stage="discovery")
        self.assertEqual(status["discovery"]["eligible_candidates"], 2)
        self.assertEqual(status["discovery"]["frontier_routes"], 4)
        self.assertEqual(status["discovery"]["unexplored_routes"], 0)
        self.assertEqual(status["discovery"]["stop_reason"], "frontier_exhausted_or_route_limits")

    def test_pilot_decision_tampering_is_rejected_before_import(self):
        workflow = self.workflow()
        pilot = self.root / "pilot"
        with MusicBrainzClient(self.root / "pilot-cache", Limits(), contact="test@project.invalid",
                              opener=self.transport, clock=self.clock.time, sleep=self.clock.sleep) as client:
            match_batch(client, workflow.tracks, workflow.metadata, pilot, MatchRules())
        rows = read_json(pilot / "matches.json")
        rows[0]["accepted_recording_id"] = self.transport.c1
        atomic_json(pilot / "matches.json", rows)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.workflow(pilot=pilot).run(stage="matching")

    def test_completed_job_verifies_a_fresh_offline_replay(self):
        workflow = self.workflow()
        status = workflow.run()
        sends = len(self.transport.calls)
        with patch("socket.socket", side_effect=AssertionError("offline verification opened a socket")):
            status = workflow.verify_offline(status)
        self.assertEqual(status["offline_replay"]["status"], "verified")
        self.assertEqual(status["offline_replay"]["http_attempts"], 0)
        self.assertEqual(len(self.transport.calls), sends)
        self.assertEqual(len(status["offline_replay"]["artifact_sha256"]), 5)


if __name__ == "__main__":
    unittest.main()
