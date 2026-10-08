"""Representative identity regressions are independent of historical exact matching."""

from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from src.seed_matching import (choose_candidate, compatible, core_response_valid, credit_diagnostics,
                               matching_allocation, seed_query, title_keys, version_notice)
from src.benchmark_matching import benchmark_matching
from src.fetch_musicbrainz import json_bytes
import test_quick_recommend as quick
from test_quick_recommend import QuickTransport, favorite, record
from test_song_policy import artist
from test_fetch_musicbrainz import Response, identifier


class IdentityTests(unittest.TestCase):
    def test_punctuation_unicode_and_annotation_keys(self):
        for title in ("It Didn’t Matter", "It Didn't Matter (1997 - Remaster)", "It Didn't Matter - 2011 Remastered", "It Didn't Matter (feat. Guest)"):
            with self.subTest(title=title):
                self.assertTrue(compatible(favorite(song_text=title), record() | {"title": "It Didn't Matter"}))
        self.assertEqual(title_keys("Ｃａｆé — Song")["base"], "café - song")
        self.assertEqual(title_keys("Song (I Live for You)")["base"], "song (i live for you)")

    def test_album_duration_and_missing_credit_fields_are_not_identity(self):
        row = record() | {"length": 999000, "releases": [{"title": "Compilation"}]}
        self.assertTrue(compatible(favorite(), row))
        for field in ("length", "relations", "releases"):
            row.pop(field, None)
        self.assertTrue(compatible(favorite(), row))
        self.assertFalse(credit_diagnostics(row)["relations_field_present"])
        self.assertEqual(credit_diagnostics(row)["note"], "matched; no additional contributor credits observed")
        self.assertTrue(compatible(favorite(), row | {"relations": []}))
        for field in ("artist-credit", "relations", "releases"):
            self.assertFalse(core_response_valid(row | {field: "malformed"}))

    def test_main_artist_and_guest_omission_without_guest_only_match(self):
        row = record() | {"artist-credit": [{"artist": artist(1), "joinphrase": " featuring "}, {"artist": artist(2)}]}
        for name in ("Act 1", "Act 1 feat. Act 2", "Act 1 & Act 2"):
            self.assertTrue(compatible(favorite(artist_text=name), row))
        self.assertFalse(compatible(favorite(artist_text="Act 2"), row))
        self.assertTrue(compatible(favorite(artist_text="Act 1 feat. Guest"), record()))

    def test_separator_names_are_not_blindly_split(self):
        for name in ("Earth, Wind & Fire", "AC/DC", "Belle & Sebastian"):
            row = record()
            row["artist-credit"][0]["artist"]["name"] = name
            self.assertTrue(compatible(favorite(artist_text=name), row))
            self.assertFalse(compatible(favorite(artist_text=name.split("&")[0].strip()), row)) if "&" in name else None

    def test_version_preference_and_deterministic_choice(self):
        studio = record()
        live = record(200) | {"title": "Song 100 (Live)", "disambiguation": "live"}
        for rows in ([live, studio], [studio, live]):
            self.assertEqual(choose_candidate(favorite(), rows)["id"], studio["id"])
            self.assertEqual(choose_candidate(favorite(song_text="Song 100 (Live)"), rows)["id"], live["id"])
        self.assertIsNotNone(version_notice(favorite(), live))
        self.assertTrue(compatible(favorite(), live))
        self.assertFalse(compatible(favorite(), studio | {"video": True}))
        self.assertFalse(compatible(favorite(), studio | {"id": "invalid"}))
        self.assertFalse(compatible(favorite(), studio | {"title": "Unrelated"}))

    def test_allocation_and_distinct_queries(self):
        self.assertEqual(matching_allocation(35), {"matching_attempt_limit": 20, "discovery_request_reserve": 15})
        for budget in (1, 2, 3, 7, 100):
            allocation = matching_allocation(budget)
            self.assertGreater(allocation["matching_attempt_limit"], 0)
            self.assertLessEqual(sum(allocation.values()), budget)
        track = favorite(song_text="Song 100 (1997 - Remaster)")
        self.assertNotIn("remaster", seed_query(track))
        self.assertNotEqual(seed_query(track), seed_query(track, fallback=True))


class MatchingFlowTests(unittest.TestCase):
    setUp = quick.CollectionTests.setUp
    collection = quick.CollectionTests.collection
    def test_fallback_follows_every_initial_opportunity(self):
        base = QuickTransport(search_mode="none")
        collector = self.collection(base, [favorite(), favorite(n=200, act=2, line=2)])
        collector.match()
        queries = [p["query"][0] for _, p, _ in base.calls]
        self.assertEqual(len(queries), 4)
        self.assertTrue(all(" AND artist:" in q for q in queries[:2]))
        self.assertTrue(all(" AND artist:" not in q for q in queries[2:]))

    def test_matching_stage_exhaustion_leaves_discovery_capacity(self):
        collector = self.collection(QuickTransport(), [favorite(n=100 + n, act=1 + n, line=1 + n) for n in range(25)])
        collector.sampled.sort(key=lambda s: s["source_row"]["line_number"])
        collector.match()
        self.assertEqual(collector.client.stats["attempts"], 20)
        self.assertTrue(any(r["status"] == "stage_budget" for r in collector.state["matching_outcomes"]))
        collector.discover()
        self.assertGreater(collector.client.stats["attempts"], 20)

    def test_invalid_json_shape_is_not_a_provider_transport_failure(self):
        collector = self.collection(lambda request, timeout: Response(["not an object"]))
        collector.match()
        self.assertEqual(collector.state["matching_outcomes"][0]["status"], "invalid_response")
        self.assertEqual(collector.client.stats["attempts"], 1)

    def test_global_small_budget_is_distinct_from_stage_exhaustion(self):
        collector = self.collection(QuickTransport(), budget=1)
        collector.run()
        self.assertEqual(collector.state["matching_outcomes"][0]["status"], "global_budget")
        self.assertEqual(collector.state["stop_reason"], "request_budget")
        self.assertEqual(collector.client.stats["attempts"], 1)

    def test_duplicate_accepted_mbids_preserve_rows_and_one_discovery_identity(self):
        collector = self.collection(QuickTransport())
        first = favorite() | {"source_lines": [1]}
        second = favorite(line=2, album_text="Other edition") | {"source_lines": [2]}
        collector.sampled = [{"source_row": first}, {"source_row": second}]
        collector.state["matching_outcomes"] = [{"status": "not_attempted", "recording_id": None, "source_lines": [n]} for n in (1, 2)]
        collector.match()
        self.assertEqual([row["status"] for row in collector.state["matching_outcomes"]], ["accepted", "accepted"])
        self.assertEqual(collector.favorites(), [identifier(100)])
        self.assertEqual(collector.client.stats["attempts"], 2)


class BenchmarkManifestTests(unittest.TestCase):
    def test_fixed_batches_and_full_denominator(self):
        from src.library_job import read_json
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root) / "favorites.json", Path(root) / "audit"
            source.write_bytes(json_bytes({"format_version": 1, "tracks": [favorite(n=100+n, act=n+1, line=n+1) for n in range(10)]}))
            observed = []
            def runner(input_path, **options):
                manifest = read_json(output / "sample_manifest.json")
                batch = options["_sampled_seeds"]
                observed.extend(s["source_row"]["line_number"] for s in batch)
                self.assertTrue(options["_matching_only"])
                self.assertEqual(manifest["sample_size"], 10)
                self.assertLessEqual(len(batch), 8)
                return {"output_directory": str(options["output_directory"]),
                        "matching_outcomes": [{"status": "provider_failure", "recording_id": None,
                                               "source_lines": s["source_row"]["source_lines"]} for s in batch],
                        "matching_summary": {"accepted_sampled_rows": 0},
                        "requests": {"attempts": len(batch)}, "stop_reason": "matching_complete"}
            result = benchmark_matching(source, contact="test@project.invalid", output=output, sample_size=10, _runner=runner)
            self.assertEqual(len(set(observed)), 10)
            self.assertEqual(result["sampled_rows"], 10)
            self.assertEqual(result["match_rate"], 0)
            self.assertEqual(result["outcomes"], {"provider_failure": 10})
            frozen = read_json(output / "sample_manifest.json")
            self.assertEqual(observed, [s["source_row"]["line_number"] for s in frozen["sampled_rows"]])


if __name__ == "__main__":
    unittest.main()
