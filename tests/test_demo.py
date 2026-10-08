"""Public demo and frozen comparison operate with network creation forbidden."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.build_graph import ROOT, load_dataset
from src.compare_methods import compare_dataset, prepare_comparison, prepare_followup, summarize_ratings
from src.demo import DEFAULT_DEMO, demo_report
from src.library_job import read_json
from src.recommend_songs import score_song_candidates
from src.source_songs import known_work_ids


class PublicDemoTests(unittest.TestCase):
    def test_deterministic_five_results_with_evidence_and_composition_uniqueness(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            first, second = demo_report(), demo_report()
            equal = demo_report(method="equal")
        self.assertEqual(first, second)
        self.assertFalse(first["fresh_api_data"])
        self.assertEqual(len(first["recommendations"]), 5)
        self.assertEqual(first["selection_summary"]["represented_source_groups"], 3)
        self.assertEqual(first["selection_summary"]["source_coverage_shortfall"], 0)
        records, _ = load_dataset(DEFAULT_DEMO)
        by_id = {r["id"]: r for r in records}
        observed = set()
        for row in first["recommendations"]:
            self.assertTrue(row["contributions"])
            self.assertTrue(row["recording"]["source_url"].startswith("https://musicbrainz.org/recording/"))
            works = known_work_ids(by_id[row["recording"]["id"]])
            self.assertFalse(observed & works)
            observed.update(works)
            self.assertIn(row["primary_seed_song"]["source_group_id"], row["source_assignment_evidence"])
            for contribution in row["contributions"]:
                self.assertTrue(all(c["favorite_credits"] and c["candidate_credits"] for c in contribution["contributors"]))
        self.assertEqual(first["source_policy"], equal["source_policy"])

    def test_cli_and_legacy_fixture_are_complete(self):
        load_dataset(ROOT / "data/fixture")
        result = subprocess.run([sys.executable, "-B", "-m", "src.demo", "--format", "json"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), demo_report())


class ListeningReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "review"
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            self.result = prepare_comparison([DEFAULT_DEMO, DEFAULT_DEMO], self.output)

    def test_panel_is_bounded_blinded_and_pending_with_no_invented_ratings(self):
        self.assertLessEqual(self.result["panel_size"], 20)
        with (self.output / "ratings.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), self.result["panel_size"])
        self.assertTrue(all(not r["familiar"] and not r["enjoyment"] and not r["would_save"] for r in rows))
        self.assertNotIn("method", rows[0])
        self.assertNotIn("score", rows[0])
        summary = summarize_ratings(self.output, self.output / "ratings.csv")
        self.assertEqual(summary["status"], "pending")
        self.assertEqual(summary["rated"], 0)
        self.assertIsNone(summary["methods"]["weighted"]["would_save_fraction_of_rated"])

    def test_ratings_are_once_per_recording_and_denominators_remain_visible(self):
        path = self.output / "ratings.csv"
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            row.update(familiar="no", enjoyment="like", would_save="yes")
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        summary = summarize_ratings(self.output, path)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["rated"], len(rows))
        self.assertEqual(summary["methods"]["weighted"]["rated"], 5)
        self.assertEqual(summary["methods"]["equal"]["would_save_fraction_of_rated"], 1)

    def test_tampered_panel_or_unknown_item_is_rejected(self):
        panel = read_json(self.output / "panel_manifest.json")
        panel["items"] = panel["items"][:-1]
        (self.output / "panel_manifest.json").write_text(json.dumps(panel))
        with self.assertRaisesRegex(ValueError, "different review panel"):
            summarize_ratings(self.output, self.output / "ratings.csv")

    def test_save_intention_is_optional_and_has_its_own_denominator(self):
        path = self.output / "ratings.csv"
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            row.update(familiar="yes", enjoyment="like")

        def write_rows(columns):
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

        # Both a blank optional column and an omitted optional column are uncollected.
        for columns in (fields, [f for f in fields if f != "would_save"]):
            with self.subTest(columns=columns):
                write_rows(columns)
                summary = summarize_ratings(self.output, path)
                self.assertEqual(summary["status"], "complete")
                self.assertEqual(summary["liked"], len(rows))
                self.assertEqual(summary["familiar"], len(rows))
                self.assertEqual(summary["previously_unfamiliar"], 0)
                self.assertEqual(summary["would_save_rated"], 0)
                self.assertIsNone(summary["would_save"])
                self.assertIsNone(summary["would_save_fraction_of_rated"])
                self.assertEqual(summary["methods"]["weighted"]["rated"], 5)
        rows[0]["would_save"] = "yes"
        write_rows(fields)
        summary = summarize_ratings(self.output, path)
        self.assertEqual(summary["would_save_rated"], 1)
        self.assertEqual(summary["would_save_fraction_of_rated"], 1)
        rows[0]["would_save"] = "maybe"
        write_rows(fields)
        with self.assertRaisesRegex(ValueError, "invalid rating"):
            summarize_ratings(self.output, path)
        rows[0].update(would_save="yes", enjoyment="")
        write_rows(fields)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            summarize_ratings(self.output, path)

    def test_followup_excludes_known_recordings_without_changing_scores_or_original_review(self):
        original = compare_dataset(DEFAULT_DEMO)
        known = original["methods"]["weighted"]["recommendations"][0]["recording"]["id"]
        path = self.output / "ratings.csv"
        panel = read_json(self.output / "panel_manifest.json")
        ids = {r["item_id"]: r["recording_id"] for r in panel["items"]}
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            row.update(familiar="yes" if ids[row["item_id"]] == known else "no", enjoyment="like")
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        summarize_ratings(self.output, path)
        unchanged = {p: p.read_bytes() for p in self.output.iterdir() if p.is_file()}
        followup = Path(self.temp.name) / "followup"

        def compare_after_protocol(dataset, *, excluded_ids):
            protocol = read_json(followup / "protocol.json")
            self.assertEqual(protocol["excluded_recording_ids"], [known])
            self.assertEqual(protocol["requested"], 5)
            return compare_dataset(dataset, excluded_ids=excluded_ids)

        with patch("socket.socket", side_effect=AssertionError("Network forbidden")), \
             patch("src.compare_methods.compare_dataset", side_effect=compare_after_protocol):
            result = prepare_followup(DEFAULT_DEMO, self.output, followup)
        protocol = read_json(followup / "protocol.json")
        report = read_json(followup / "comparison.json")["comparisons"][0]["methods"]["weighted"]
        records, _ = load_dataset(DEFAULT_DEMO)
        base = {r["recording"]["id"]: r["score"] for r in score_song_candidates(records, protocol["favorite_recording_ids"])}
        self.assertTrue(report["recommendations"])
        self.assertNotIn(known, {r["recording"]["id"] for r in report["recommendations"]})
        for row in report["recommendations"]:
            self.assertEqual(row["score"], base[row["recording"]["id"]])
            self.assertTrue(all(c["favorite_recording_id"] in protocol["favorite_recording_ids"] for c in row["contributions"]))
        self.assertEqual(report["source_policy"], original["methods"]["weighted"]["source_policy"])
        self.assertEqual(result["shortfall"], 5 - result["panel_size"])
        self.assertEqual(result["new_provider_requests"], 0)
        self.assertEqual(read_json(followup / "listening_results.json")["rated"], 0)
        self.assertEqual(set(read_json(followup / "listening_results.json")["methods"]), {"weighted"})
        self.assertTrue(all(p.read_bytes() == content for p, content in unchanged.items()))
        repeated = Path(self.temp.name) / "repeated"
        prepare_followup(DEFAULT_DEMO, self.output, repeated)
        for name in ("protocol.json", "comparison.json", "panel_manifest.json", "method_key.json", "ratings.csv"):
            self.assertEqual((followup / name).read_bytes(), (repeated / name).read_bytes())

    def test_followup_rejects_pending_or_tampered_prior_review_before_export(self):
        followup = Path(self.temp.name) / "followup"
        with self.assertRaisesRegex(ValueError, "Complete the previous"):
            prepare_followup(DEFAULT_DEMO, self.output, followup)
        self.assertFalse(followup.exists())
        panel = read_json(self.output / "panel_manifest.json")
        panel["items"] = panel["items"][:-1]
        (self.output / "panel_manifest.json").write_text(json.dumps(panel))
        with self.assertRaisesRegex(ValueError, "different review panel"):
            prepare_followup(DEFAULT_DEMO, self.output, followup)
        self.assertFalse(followup.exists())

    def test_followup_keeps_shortfall_when_all_feasible_recordings_are_known(self):
        # A prior panel may accumulate explicit known IDs from earlier follow-ups.
        # Mark all remaining recordings known and bind that metadata to its key.
        from src.fetch_musicbrainz import digest, json_bytes
        from src.library_job import atomic_json

        records, _ = load_dataset(DEFAULT_DEMO)
        panel = read_json(self.output / "panel_manifest.json")
        panel["excluded_recording_ids"] = sorted(r["id"] for r in records)
        atomic_json(self.output / "panel_manifest.json", panel)
        key = read_json(self.output / "method_key.json")
        key["panel_sha256"] = digest(json_bytes(panel))
        atomic_json(self.output / "method_key.json", key)
        path = self.output / "ratings.csv"
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            row.update(familiar="yes", enjoyment="like")
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        followup = Path(self.temp.name) / "followup"
        result = prepare_followup(DEFAULT_DEMO, self.output, followup)
        self.assertEqual(result["panel_size"], 0)
        self.assertEqual(result["shortfall"], 5)
        self.assertEqual(result["listening_status"], "no_items")
        self.assertEqual(read_json(followup / "protocol.json")["excluded_recording_ids"], panel["excluded_recording_ids"])


if __name__ == "__main__":
    unittest.main()
