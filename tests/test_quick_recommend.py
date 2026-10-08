"""Controlled transports test the fast pipeline without contacting either provider."""

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from src.benchmark_recommendations import list_overlap, run_experiments
from src.build_graph import load_dataset
from src.check_apple_music import check_recommendation_run
from src.credits import extract_credits
from src.fetch_musicbrainz import FetchError, json_bytes
from src.library_job import atomic_json, read_json
from src.match_recordings import MatchRules, load_input
from src.quick_recommend import (CollectionStopped, FreshClient, QuickCollection,
                                 choose_seed_candidate, recommend_from_likes, sample_likes)
from src.recommend_songs import load_weights, recommendation_report, profile_favorites
from test_apple_music import apple_track
from test_fetch_musicbrainz import FakeClock, Response, identifier
from test_song_policy import ENGINEERING, INSTRUMENT, PRODUCER, artist, relation, song


CONTACT = "test@project.invalid"


def record(n=100, act=1, connector=4):
    return song(n, [artist(act)], [relation(artist(connector))]) | {
        "length": 180000, "releases": [{"id": identifier(999), "title": "Album"}], "video": False}


def favorite(n=100, act=1, line=1, **updates):
    return {"line_number": line, "artist_text": f"Act {act}", "song_text": f"Song {n}",
            "album_text": "Album", "duration_text": "3:00"} | updates


class QuickTransport:
    def __init__(self, *, search_mode="single", thin=False, work=False):
        self.calls = []
        self.search_mode, self.thin, self.work = search_mode, thin, work

    def __call__(self, request, timeout):
        parsed = urlparse(request.full_url)
        endpoint, params = parsed.path.removeprefix("/ws/2/"), parse_qs(parsed.query)
        self.calls.append((endpoint, params, timeout))
        if endpoint == "recording" and "query" in params:
            records = [] if self.search_mode == "none" else [record()]
            if self.search_mode == "ambiguous":
                records.append(record(100) | {"id": identifier(200)})
            return Response({"recordings": records, "count": 26 if self.search_mode == "capped" else len(records), "offset": 0})
        if endpoint.startswith("artist/"):
            aid = endpoint.split("/")[1]
            rows = []
            if aid == artist(4)["id"]:
                rows = [{"target-type": "recording", "type-id": ENGINEERING, "recording": {"id": identifier(n)}} for n in (101, 102)]
                if self.work:
                    rows += [{"target-type": "work", "type-id": "d59d99ea-23d4-4a80-b066-edca32ee158f",
                              "work": {"id": identifier(w)}} for w in (701, 702)]
            return Response({"id": aid, "name": "Contributor", "relations": rows})
        if endpoint == "recording":
            rows = [record(101, 2), record(102, 3)] if params.get("artist") == [artist(4)["id"]] else []
            if "work" in params:
                rows = [record(103, 5)]
            if self.thin:
                rows = [{k: v for k, v in row.items() if k != "relations"} for row in rows]
            return Response({"recordings": rows, "recording-count": len(rows), "recording-offset": 0})
        if endpoint.startswith("recording/"):
            rid = endpoint.split("/")[1]
            n = int(rid.split("-")[-1])
            return Response(record(n, {100: 1, 101: 2, 102: 3}.get(n, 5)))
        raise AssertionError(f"Unexpected request: {request.full_url}")


class StalledTransport:
    def __init__(self, marker):
        self.marker = str(marker)

    def __call__(self, request, timeout):
        Path(self.marker).write_text("transport entered")
        time.sleep(10)
        raise AssertionError("Stalled transport was not terminated")


class AfterSeedStalledTransport(QuickTransport):
    def __call__(self, request, timeout):
        if "/artist/" in request.full_url:
            time.sleep(10)
            raise AssertionError("Discovery transport was not terminated")
        return super().__call__(request, timeout)


class SamplingTests(unittest.TestCase):
    def test_weight_boundaries_deduplication_and_source_lines(self):
        tracks = []
        for act, count in enumerate((1, 2, 10, 11), 1):
            for n in range(count):
                tracks.append(favorite(n=n, act=act, line=len(tracks) + 1))
        tracks.append(tracks[0] | {"line_number": 99, "artist_text": "  ACT 1  "})
        sampled, summary = sample_likes(tracks, random_seed=42, seed_count=4)
        self.assertEqual({s["artist_key"]: s["sampling_weight"] for s in sampled},
                         {"act 1": 1, "act 2": 2, "act 3": 2, "act 4": 3})
        self.assertEqual(summary["duplicate_rows"], 1)
        self.assertEqual(next(s for s in sampled if s["artist_key"] == "act 1")["source_row"]["source_lines"], [1, 99])

    def test_same_seed_and_input_order_reproduce_sampling(self):
        tracks = [favorite(n=100 + n, act=1 + n // 2, line=n + 1) for n in range(40)]
        first = sample_likes(tracks, random_seed=17)
        self.assertEqual(first, sample_likes(list(reversed(tracks)), random_seed=17))
        self.assertNotEqual(first[0], sample_likes(tracks, random_seed=18)[0])
        self.assertEqual(len({row["artist_key"] for row in first[0]}), 8)

    def test_different_versions_remain_distinct(self):
        tracks = [favorite(), favorite(line=2, album_text="Live Album"), favorite(line=3, duration_text="3:01")]
        _, summary = sample_likes(tracks, random_seed=0)
        self.assertEqual(summary["distinct_liked_songs"], 3)

    def test_known_ids_are_retained_and_conflicts_rejected(self):
        tracks = [favorite(), favorite(line=2, recording_mbid=identifier(100))]
        sampled, _ = sample_likes(tracks, random_seed=0)
        self.assertEqual(sampled[0]["source_row"]["recording_mbid"], identifier(100))
        with self.assertRaises(ValueError):
            sample_likes([tracks[1], favorite(line=3, recording_mbid=identifier(101))], random_seed=0)


class FreshClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = FakeClock()

    def client(self, opener, name="run", budget=35, deadline=1000):
        return FreshClient(self.root / name, contact=CONTACT, max_requests=budget, deadline=deadline,
                           pacing_directory=self.root / "gate", opener=opener, clock=self.clock.time,
                           monotonic=self.clock.time, sleep=self.clock.sleep)

    def test_reuse_only_within_run_and_spacing_across_runs(self):
        calls = []
        def transport(request, timeout):
            calls.append(self.clock.time())
            return Response({"ok": True})
        first = self.client(transport)
        first.get("recording", operation="search", query="same")
        first.get("recording", operation="lookup", query="same")
        second = self.client(transport, name="second")
        second.get("recording", operation="search", query="same")
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(calls[1] - calls[0], 1.1 - 1e-8)
        self.assertEqual(first.stats["within_run_reuses"], 1)
        self.assertEqual(second.stats["attempts"], 1)

    def test_attempt_is_saved_before_transport_and_budget_blocks_next_call(self):
        def transport(request, timeout):
            state = read_json(self.root / "run/requests.json")
            self.assertEqual(state["attempts"], 1)
            self.assertEqual(state["events"][0]["outcome"], "in_progress")
            return Response({"ok": True})
        client = self.client(transport, budget=1)
        client.get("recording", operation="search")
        with self.assertRaises(CollectionStopped) as error:
            client.get("artist", operation="lookup")
        self.assertEqual(error.exception.reason, "request_budget")
        self.assertEqual(client.stats["attempts"], 1)

    def test_failures_are_not_retried_and_provider_backoff_is_shared(self):
        attempts = []
        def failing(request, timeout):
            attempts.append(self.clock.time())
            raise HTTPError(request.full_url, 503, "unavailable", {"Retry-After": "3"}, BytesIO())
        first = self.client(failing)
        with self.assertRaises(FetchError):
            first.get("recording", operation="search")
        with self.assertRaises(FetchError):
            first.get("recording", operation="search")
        second = self.client(lambda request, timeout: Response({}), name="second")
        second.get("artist", operation="lookup")
        self.assertEqual(len(attempts), 1)
        self.assertGreaterEqual(self.clock.time() - attempts[0], 3)

    def test_pacing_cannot_spend_past_deadline(self):
        first = self.client(lambda request, timeout: Response({}))
        first.get("recording", operation="search")
        second = self.client(lambda request, timeout: self.fail("late transport"), name="second", deadline=100.5)
        with self.assertRaises(CollectionStopped):
            second.get("artist", operation="lookup")
        self.assertEqual(second.stats["attempts"], 0)

    def test_timeout_uses_remaining_time_and_rejects_malformed_json(self):
        timeouts = []
        def transport(request, timeout):
            timeouts.append(timeout)
            return Response(b"[]")
        client = self.client(transport, deadline=102)
        with self.assertRaises(FetchError):
            client.get("recording", operation="search")
        self.assertLessEqual(timeouts[0], 2)
        self.assertEqual(client.stats["attempts"], 1)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def collection(self, transport, tracks=None, *, budget=35, limit=2):
        tracks = [favorite()] if tracks is None else tracks
        source = self.root / "favorites.json"
        source.write_bytes(json_bytes({"format_version": 1, "tracks": tracks}))
        tracks, metadata = load_input(source)
        sampled, _ = sample_likes(tracks, random_seed=0, seed_count=len(tracks))
        state = {"records": {}, "sources": {}, "failures": [], "stage_timings": {},
                 "matching_outcomes": [{"source_lines": s["source_row"]["source_lines"], "status": "not_attempted",
                                        "recording_id": None} for s in sampled],
                 "discovery": {"contributor_queue": [], "routes": [], "exclusions": [], "examined_recordings": 0,
                               "admitted_candidates": 0}, "stop_reason": "running"}
        clock = FakeClock()
        client = FreshClient(self.root / "run", contact=CONTACT, max_requests=budget, deadline=1000,
                             pacing_directory=self.root / "gate", opener=transport, clock=clock.time,
                             monotonic=clock.time, sleep=clock.sleep)
        weights = load_weights()
        config = {"limit": limit, "role_weights": weights["role_weights"], "saturation_k": weights["saturation_k"]}
        return QuickCollection(self.root / "run", tracks, metadata, sampled, config, client, state)

    def test_batched_credits_avoid_individual_lookups_and_allow_contributor_reuse(self):
        collector = self.collection(QuickTransport())
        collector.run()
        self.assertEqual(len(collector.report()["recommendations"]), 2)
        self.assertNotIn("candidate_lookup", collector.client.stats["by_operation"])
        self.assertEqual(collector.state["stop_reason"], "target_reached")
        self.assertEqual(collector.report()["selection_summary"]["repeated_observed_musicians"], 0)
        self.assertEqual(collector.report()["selection_summary"]["repeated_explanatory_contributors"], 1)
        for source in collector.state["sources"].values():
            self.assertTrue((self.root / "run" / source["response_file"]).exists())

    def test_large_frontier_does_not_spend_entire_budget_initializing_routes(self):
        base = QuickTransport()
        def transport(request, timeout):
            if urlparse(request.full_url).path.endswith("/recording/" + identifier(100)):
                return Response(record() | {"relations": [relation(artist(n)) for n in range(4, 30)]})
            return base(request, timeout)
        collector = self.collection(transport, budget=4)
        collector.run()
        self.assertEqual(len(collector.report()["recommendations"]), 2)
        self.assertEqual(collector.client.stats["attempts"], 4)
        self.assertEqual(collector.client.stats["by_operation"]["artist_browse"], 1)

    def test_nested_work_credits_in_browse_are_ingested_without_lookup(self):
        base = QuickTransport()
        work_relation = {"target-type": "work", "type": "performance", "work": {
            "id": identifier(701), "title": "Composition", "relations": [
                relation(artist(4), role="d59d99ea-23d4-4a80-b066-edca32ee158f") | {"type": "composer"}]}}
        def transport(request, timeout):
            parsed = urlparse(request.full_url)
            if parsed.path.endswith("/recording") and "artist" in parse_qs(parsed.query):
                return Response({"recordings": [record(101, 2) | {"relations": [work_relation]}],
                                 "recording-count": 1, "recording-offset": 0})
            return base(request, timeout)
        collector = self.collection(transport, limit=1)
        collector.run()
        credits = extract_credits(collector.state["records"][identifier(101)])
        self.assertTrue(any(c["scope"] == "work" and c["category"] == "songwriter" for c in credits))
        self.assertNotIn("candidate_lookup", collector.client.stats["by_operation"])

    def test_candidate_admission_stops_at_100_when_performers_conflict(self):
        base = QuickTransport()
        def transport(request, timeout):
            parsed, params = urlparse(request.full_url), parse_qs(urlparse(request.full_url).query)
            if parsed.path.endswith("/recording/" + identifier(100)):
                return Response(record() | {"relations": [relation(artist(n)) for n in range(4, 10)]})
            if "/artist/" in parsed.path:
                return Response({"id": parsed.path.split("/")[-1], "relations": []})
            if parsed.path.endswith("/recording") and "artist" in params:
                number = int(params["artist"][0].split("-")[-1])
                rows = [record(1000 + number * 25 + n, 50) for n in range(25)]
                return Response({"recordings": rows, "recording-count": 40, "recording-offset": 0})
            return base(request, timeout)
        collector = self.collection(transport, limit=15)
        collector.run()
        self.assertEqual(collector.state["discovery"]["admitted_candidates"], 100)
        self.assertEqual(collector.state["stop_reason"], "candidate_limit")
        self.assertEqual(len(collector.report()["recommendations"]), 1)

    def test_missing_credit_fields_use_bounded_deduplicated_fallback(self):
        collector = self.collection(QuickTransport(thin=True))
        collector.run()
        self.assertEqual(len(collector.report()["recommendations"]), 2)
        self.assertEqual(collector.client.stats["by_operation"]["candidate_lookup"], 2)
        self.assertLessEqual(collector.client.stats["attempts"], 35)

    def test_missing_nested_work_credits_require_bounded_fallback(self):
        base = QuickTransport()
        def transport(request, timeout):
            parsed, params = urlparse(request.full_url), parse_qs(urlparse(request.full_url).query)
            if parsed.path.endswith("/recording") and params.get("artist") == [artist(4)["id"]]:
                thin = record(101, 2) | {"relations": [{"target-type": "work", "type": "performance",
                                                      "work": {"id": identifier(701), "title": "Composition"}}]}
                return Response({"recordings": [thin], "recording-count": 1, "recording-offset": 0})
            return base(request, timeout)
        collector = self.collection(transport, limit=1)
        collector.run()
        self.assertEqual(collector.client.stats["by_operation"]["candidate_lookup"], 1)
        self.assertEqual(len(collector.report()["recommendations"]), 1)

    def test_multiple_versions_choose_exactly_one_detail_lookup(self):
        collector = self.collection(QuickTransport(search_mode="ambiguous"), budget=2)
        collector.run()
        outcome = collector.state["matching_outcomes"][0]
        self.assertEqual(outcome["plausible_candidates"], 2)
        self.assertEqual(outcome["chosen_recording_id"], identifier(100))
        self.assertEqual(outcome["status"], "accepted")
        self.assertEqual(outcome["alternative_recording_ids"], [identifier(100), identifier(200)])
        self.assertEqual(collector.client.stats["by_operation"], {"seed_search": 1, "seed_lookup": 1})

    def test_candidate_choice_prefers_album_known_duration_and_stable_order(self):
        wrong_album = record() | {"releases": [{"id": identifier(990), "title": "Other"}]}
        closest = record(200) | {"title": "Song 100", "length": 181000}
        missing_duration = record(300) | {"title": "Song 100", "length": None}
        candidates = [wrong_album, missing_duration, closest]
        for ordering in (candidates, list(reversed(candidates))):
            self.assertEqual(choose_seed_candidate(favorite(), ordering, MatchRules())["id"], identifier(200))

    def test_representative_choice_still_rejects_explicit_metadata_conflicts(self):
        base = QuickTransport()
        def transport(request, timeout):
            if "query=" in request.full_url:
                rows = [record(100, 2), record() | {"disambiguation": "live"}, record() | {"length": 190000}]
                return Response({"recordings": rows, "count": 3, "offset": 0})
            return base(request, timeout)
        collector = self.collection(transport)
        collector.run()
        self.assertEqual(collector.state["matching_outcomes"][0]["status"], "no_plausible_match")
        self.assertEqual(collector.client.stats["attempts"], 1)

    def test_capped_and_empty_searches_do_not_fetch_details(self):
        for mode, status in (("capped", "search_capped"), ("none", "no_plausible_match")):
            with self.subTest(mode=mode):
                collector = self.collection(QuickTransport(search_mode=mode))
                collector.run()
                self.assertEqual(collector.state["matching_outcomes"][0]["status"], status)
                self.assertEqual(collector.client.stats["attempts"], 1)
                self.assertEqual(collector.state["stop_reason"], "no_accepted_seeds")

    def test_known_recording_id_skips_search_and_checks_album(self):
        collector = self.collection(QuickTransport(), [favorite(recording_mbid=identifier(100), album_text="Wrong album")])
        collector.run()
        self.assertNotIn("seed_search", collector.client.stats["by_operation"])
        self.assertEqual(collector.state["matching_outcomes"][0]["status"], "no_confident_match")

    def test_full_input_excludes_artists_even_when_their_seed_does_not_match(self):
        collector = self.collection(QuickTransport(), [favorite(), favorite(n=700, act=2, line=2)])
        collector.run()
        self.assertEqual([r["recording"]["id"] for r in collector.report()["recommendations"]], [identifier(102)])

    def test_exhausted_budget_preserves_accepted_seed(self):
        collector = self.collection(QuickTransport(), budget=2)
        collector.run()
        self.assertEqual(collector.favorites(), [identifier(100)])
        self.assertEqual(collector.client.stats["attempts"], 2)
        self.assertEqual(collector.state["stop_reason"], "request_budget")

    def test_only_one_work_route_per_contributor(self):
        transport = QuickTransport(work=True)
        collector = self.collection(transport, limit=15)
        collector.run()
        work_calls = [params for _, params, _ in transport.calls if "work" in params]
        self.assertEqual(len(work_calls), 1)
        self.assertEqual(work_calls[0]["work"], [identifier(701)])


class PenalizedSelectionTests(unittest.TestCase):
    def test_legacy_strict_selection_and_penalized_raw_scores(self):
        seed, one, two = record(), record(101, 2), record(102, 3)
        strict = recommendation_report([seed, one, two], [seed["id"]])
        soft = recommendation_report([seed, one, two], [seed["id"]], contributor_policy="penalized")
        self.assertEqual(len(strict["recommendations"]), 1)
        self.assertEqual(len(soft["recommendations"]), 2)
        first, second = soft["recommendations"]
        self.assertEqual(first["score"], second["score"])
        self.assertAlmostEqual(second["selection_score"], first["selection_score"] / 2)
        self.assertEqual(soft["policy"], "D-025")

    def test_repeated_performers_still_conflict(self):
        seed, one, two = record(), record(101, 2), record(102, 2)
        result = recommendation_report([seed, one, two], [seed["id"]], contributor_policy="penalized")
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["skipped_candidates"][0]["reason"], "musician_already_selected")


class EngineAndAppleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "favorites.json"
        cls.source.write_bytes(json_bytes({"format_version": 1, "tracks": [favorite(recording_mbid=identifier(100))]}))
        cls.result = recommend_from_likes(cls.source, random_seed=0, limit=2, contact=CONTACT,
            runtime_limit_seconds=10, output_directory=cls.root / "run", _pacing_directory=cls.root / "gate",
            _opener=QuickTransport())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_export_is_compatible_and_contains_no_apple_filter(self):
        self.assertEqual(self.result["selection_summary"]["returned"], 2)
        self.assertFalse(self.result["availability_summary"]["applied"])
        self.assertTrue(self.result["runtime_target_met"])
        records, manifest = load_dataset(self.root / "run")
        self.assertEqual(len(records), 3)
        self.assertEqual(profile_favorites(self.root / "run/profile.json", manifest), [identifier(100)])
        self.assertEqual(self.result, read_json(self.root / "run/recommendations.json"))
        self.assertTrue((self.root / "run/SONG_REVIEW.md").exists())
        self.assertIn("Live run diagnostics", (self.root / "run/SONG_REVIEW.md").read_text())
        self.assertIn("collection_total", self.result["stage_timings"])

    def test_separate_apple_check_keeps_order_and_unmatched_song(self):
        source = self.root / "run/recommendations.json"
        before = source.read_bytes()
        calls = []
        def transport(request, timeout):
            term = parse_qs(urlparse(request.full_url).query)["term"][0]
            calls.append(term)
            tracks = [apple_track(record(101, 2))] if "101" in term else []
            return Response({"resultCount": len(tracks), "results": tracks})
        clock = FakeClock()
        result = check_recommendation_run(source, output=self.root / "apple", cache=self.root / "apple_cache",
            _client_options={"opener": transport, "clock": clock.time, "sleep": clock.sleep})
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual([r["recording"]["id"] for r in result["recommendations"]], [identifier(101), identifier(102)])
        self.assertEqual(result["recommendations"][0]["apple_availability"]["reason"], "available")
        self.assertNotEqual(result["recommendations"][1]["apple_availability"]["reason"], "available")
        self.assertEqual(len(calls), 2)

    def test_stalled_transport_is_killed_with_valid_partial_result(self):
        marker = self.root / "stalled.started"
        result = recommend_from_likes(self.source, random_seed=0, contact=CONTACT, runtime_limit_seconds=1.6,
            output_directory=self.root / "stalled", _pacing_directory=self.root / "stalled_gate",
            _opener=StalledTransport(marker))
        self.assertTrue(marker.exists())
        self.assertEqual(result["stop_reason"], "deadline")
        self.assertEqual(result["requests"]["attempts"], 1)
        self.assertEqual(result["matching_outcomes"][0]["status"], "interrupted")
        self.assertEqual(result["requests"]["events"][0]["outcome"], "interrupted")
        self.assertEqual(result["recommendations"], [])
        self.assertLess(result["elapsed_seconds"], 2.5)
        self.assertEqual(result, read_json(self.root / "stalled/recommendations.json"))

    def test_discovery_stall_preserves_completed_seed_snapshot(self):
        result = recommend_from_likes(self.source, random_seed=0, contact=CONTACT, runtime_limit_seconds=2.8,
            output_directory=self.root / "partial", _pacing_directory=self.root / "partial_gate",
            _opener=AfterSeedStalledTransport())
        self.assertEqual(result["stop_reason"], "deadline")
        self.assertEqual(result["matching_summary"]["accepted_recordings"], 1)
        self.assertEqual(result["requests"]["attempts"], 2)
        records, manifest = load_dataset(self.root / "partial")
        self.assertEqual([r["id"] for r in records], [identifier(100)])
        self.assertEqual(profile_favorites(self.root / "partial/profile.json", manifest), [identifier(100)])

    def test_fresh_engine_runs_do_not_read_previous_responses(self):
        for index in range(2):
            result = recommend_from_likes(self.source, random_seed=0, contact=CONTACT, max_requests=1,
                output_directory=self.root / f"fresh_{index}", _pacing_directory=self.root / "fresh_gate",
                _opener=QuickTransport())
            self.assertEqual(result["requests"]["attempts"], 1)
            self.assertEqual(result["requests"]["within_run_reuses"], 0)
            self.assertEqual(result["stop_reason"], "request_budget")


class ExperimentTests(unittest.TestCase):
    def test_runner_grid_exports_timing_counts_and_overlap(self):
        calls = []
        def runner(input_path, **kwargs):
            calls.append(kwargs)
            seed = kwargs["random_seed"]
            return {"recommendations": [{"recording": {"id": identifier(seed + 100)}}], "elapsed_seconds": 2,
                    "requests": {"attempts": 3}, "matching_summary": {"accepted_recordings": 1},
                    "candidate_coverage": {"admitted_candidates": 2}, "stop_reason": "routes_exhausted",
                    "runtime_target_met": True, "output_directory": str(kwargs["output_directory"])}
        with tempfile.TemporaryDirectory() as root:
            result = run_experiments("favorites.json", random_seeds=[1, 2], seed_counts=[8, 10], repeats=2,
                contact=CONTACT, output_directory=Path(root) / "experiments", _runner=runner)
            self.assertEqual(len(calls), 8)
            self.assertEqual(result["total_http_attempts"], 24)
            self.assertEqual(result["runs"][1]["overlap_with_previous"], 1)
            self.assertEqual(result["runs"][2]["overlap_with_previous"], 0)
            self.assertTrue((Path(root) / "experiments/summary.csv").exists())
            self.assertEqual(len({str(call["output_directory"]) for call in calls}), 8)

    def test_empty_lists_do_not_imply_successful_identical_recommendations(self):
        self.assertIsNone(list_overlap([], []))
        self.assertEqual(list_overlap(["one"], ["two"]), 0)


if __name__ == "__main__":
    unittest.main()
