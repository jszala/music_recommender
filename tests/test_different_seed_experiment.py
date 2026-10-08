"""No outcome screening, version substitution, reranking, or panel truncation."""

import csv
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from src.compare_methods import prepare_export_review, summarize_ratings
from src.different_seed_experiment import execute, prepare, seed_identity, select_cohorts
from src.fetch_musicbrainz import digest
from src.library_job import atomic_json, read_json


def sample(n, *, artist=None, title=None):
    return {"source_row": {"line_number": n, "artist_text": artist or f"Artist {n}",
                           "song_text": title or f"Song {n}"}}


def exported_rows(start, count):
    return [{"recording": {"id": f"recording-{n}", "title": f"Song {n}",
             "artist_credit": [{"artist": {"name": f"Artist {n}"}}],
             "source_url": f"https://musicbrainz.org/recording/recording-{n}"}}
            for n in range(start, start + count)]


class CohortTests(unittest.TestCase):
    def test_remasters_rows_and_feature_annotations_do_not_create_new_seed_identity(self):
        a = sample(1, artist="Singer feat. Guest", title="Song (2020 Remaster)")
        b = sample(900, artist="singer", title="song")
        self.assertEqual(seed_identity(a), seed_identity(b))
        self.assertEqual(seed_identity(sample(2, title="Song (Live)"))[1], "song")

    def test_first_eligible_rule_rejects_prior_duplicates_and_new_cohort_overlap(self):
        prior = sample(1)
        previews = {
            6: [sample(1)] + [sample(n) for n in range(10, 19)],
            7: [sample(n) for n in range(20, 30)],
            8: [sample(n) for n in range(20, 30)],
            9: [sample(n) for n in range(30, 40)],
            10: [sample(n) for n in range(40, 50)],
        }
        tracks = ["full input stays intact"]
        calls = []
        def sampler(actual, *, random_seed, seed_count):
            self.assertIs(actual, tracks)
            self.assertEqual(seed_count, 10)
            calls.append(random_seed)
            return previews[random_seed], {}
        cohorts, checked = select_cohorts(tracks, [prior], sampler=sampler)
        self.assertEqual([c["sampling_integer"] for c in cohorts], [7, 9, 10])
        self.assertEqual(calls, [6, 7, 8, 9, 10])
        self.assertEqual([p["song_overlap_count"] for p in checked], [1, 0, 10, 0, 0])

    def test_bounded_shortfall_and_duplicate_versions_are_not_refilled(self):
        def sampler(tracks, **kwargs):
            return [sample(1, title="Song"), sample(2, artist="Artist 1", title="Song (Remastered)")] + [sample(n) for n in range(3, 11)], {}
        cohorts, checked = select_cohorts([], [], sampler=sampler)
        self.assertEqual(cohorts, [])
        self.assertEqual(len(checked), 30)
        self.assertTrue(all(p["distinct_identity_count"] == 9 for p in checked))

    def test_changed_full_input_blocks_calls_before_contact_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            favorites = root / "input.json"
            atomic_json(favorites, {"format_version": 1, "tracks": [sample(1)["source_row"], sample(2)["source_row"]]})
            runs = [root / f"old{i}" for i in range(3)]
            for run in runs:
                run.mkdir()
                atomic_json(run / "recommendations.json", {"input_sha256": digest(favorites.read_bytes()), "sampled_seeds": []})
            followup = root / "followup"
            followup.mkdir()
            atomic_json(followup / "comparison.json", {})
            output = root / "experiment"
            protocol = prepare(favorites, runs, followup, output)
            self.assertEqual(protocol["cohort_shortfall"], 3)
            self.assertEqual((output / "favorites.json").read_bytes(), favorites.read_bytes())
            favorites.write_text("changed")
            runner = Mock()
            with self.assertRaisesRegex(ValueError, "Favorites input changed"):
                execute(output, root / "missing-contact", runner=runner)
            runner.assert_not_called()


class ExportReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_export(self, name, start, count):
        path = self.root / name
        path.mkdir()
        atomic_json(path / "recommendations.json", {"configuration": {"limit": 10},
            "selection_summary": {"requested": 10, "returned": count, "shortfall": 10 - count},
            "recommendations": exported_rows(start, count)})
        return path

    def test_all_ten_tracks_and_two_run_union_are_bound_with_blank_ratings(self):
        a, b = self.run_export("a", 1, 10), self.run_export("b", 8, 10)
        output = self.root / "review"
        result = prepare_export_review([a, b], output)
        panel = read_json(output / "panel_manifest.json")
        self.assertEqual({p["recording_id"] for p in panel["items"]}, {f"recording-{n}" for n in range(1, 18)})
        self.assertEqual(result["panel_size"], 17)
        self.assertEqual(panel["datasets"][0]["recommendations_sha256"], digest((a / "recommendations.json").read_bytes()))
        self.assertEqual(len(panel["datasets"][0]["ordered_recording_ids"]), 10)
        with (output / "ratings.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(all(r[k] == "" for r in rows for k in ("familiar", "enjoyment", "would_save")))
        self.assertNotIn("score", rows[0])
        ratings = summarize_ratings(output, output / "ratings.csv")
        self.assertEqual((ratings["rated"], ratings["pending"]), (0, 17))

    def test_short_and_empty_exports_retain_requested_denominators(self):
        a, b = self.run_export("a", 1, 3), self.run_export("b", 50, 0)
        output = self.root / "review"
        result = prepare_export_review([a, b], output)
        self.assertEqual(result["panel_size"], 3)
        self.assertEqual([(d["requested"], d["returned"]) for d in result["datasets"]], [(10, 3), (10, 0)])

    def test_wrong_limit_duplicate_ids_and_dishonest_counts_are_rejected(self):
        path = self.run_export("a", 1, 10)
        original = read_json(path / "recommendations.json")
        for mutation in ("limit", "duplicate", "count"):
            run = deepcopy(original)
            if mutation == "limit":
                run["configuration"]["limit"] = 5
            elif mutation == "duplicate":
                run["recommendations"][-1] = run["recommendations"][0]
            else:
                run["selection_summary"]["returned"] = 9
            atomic_json(path / "recommendations.json", run)
            with self.assertRaisesRegex(ValueError, "Export length"):
                prepare_export_review([path], self.root / mutation)
