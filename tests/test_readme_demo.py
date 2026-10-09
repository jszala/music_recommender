"""Saved outputs stay complete, source-bound, and independent of private input."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.build_graph import ROOT, load_dataset
from src.readme_demo import DEFAULT_RUNS, START, END, check_documents, load_runs, render_list, render_details
from src.recommend_songs import score_song_candidates


class ReadmeDemoTests(unittest.TestCase):
    def test_saved_runs_preserve_all_eleven_results_and_reproduce_every_base_path(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            reports = load_runs()
            self.assertEqual([r["random_seed"] for r in reports], [6, 9, 10])
            self.assertEqual([len(r["recommendations"]) for r in reports], [4, 3, 4])
            for number, report in enumerate(reports, 1):
                records, _ = load_dataset(DEFAULT_RUNS / f"run_{number:03}")
                scored = {r["recording"]["id"]: r for r in score_song_candidates(
                    records, report["context_favorite_recording_ids"], weights=report["role_weights"],
                    saturation_k=report["saturation_k"])}
                self.assertEqual(report["selection_summary"]["requested"], 10)
                for row in report["recommendations"]:
                    calculated = scored[row["recording"]["id"]]
                    self.assertEqual(row["score"], calculated["score"])
                    self.assertEqual(row["contributions"], calculated["contributions"])
                    self.assertAlmostEqual(row["selection_score"], sum(a["selection_value"] for a in row["selection_adjustments"]))
        self.assertIn("Happy Friday!", reports[0]["recommendations"][1]["recording"]["title"])
        self.assertIn("Essential Mix", reports[0]["recommendations"][2]["recording"]["title"])

    def test_documented_membership_order_and_ranks_match_saved_outputs_without_mutation(self):
        reports = load_runs()
        before = deepcopy(reports)
        markdown = render_list(reports)
        lines = [line for line in markdown.splitlines() if re.match(r"^\d+\. ", line)]
        ids = [re.search(r"musicbrainz.org/recording/([0-9a-f-]{36})", line).group(1) for line in lines]
        self.assertEqual(ids, [row["recording"]["id"] for report in reports for row in report["recommendations"]])
        self.assertEqual([int(line.split(".", 1)[0]) for line in lines], [1, 2, 3, 4, 1, 2, 3, 1, 2, 3, 4])
        document = (DEFAULT_RUNS / "README.md").read_text()
        self.assertEqual(document.split(START)[1].split(END)[0].strip(), markdown)
        self.assertEqual(reports, before)
        self.assertEqual(markdown.count("[Apple search]"), 11)

    def test_all_paths_and_arithmetic_remain_in_linked_evidence(self):
        reports = load_runs()
        details = render_details(reports)
        self.assertEqual((ROOT / "docs/recommendations.md").read_text().strip(), details)
        for report in reports:
            for row in report["recommendations"]:
                self.assertIn(row["recording"]["source_url"], details)
                for connection in row["contributions"]:
                    for credit in connection["contributors"]:
                        self.assertIn(credit["contributor"]["name"], details)
                        for evidence in credit["favorite_credits"] + credit["candidate_credits"]:
                            self.assertIn(evidence["source_url"], details)
        self.assertNotIn("data/private", json.dumps(reports))
        self.assertFalse(any(k in report for report in reports for k in ["sampled_seeds", "input_sha256", "output_directory", "requests"]))

    def test_hostile_text_does_not_add_html_or_markdown_rows(self):
        reports = load_runs()
        row = reports[0]["recommendations"][0]
        row["recording"]["title"] = '<script>[untitled] | Café</script>\n# injected heading'
        row["recording"]["source_url"] = "javascript:alert(1)"
        markdown = render_list(reports)
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("# injected heading\n", markdown)
        self.assertNotIn("javascript:", markdown)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("\\[untitled\\]", markdown)
        self.assertIn("Café", markdown)
        self.assertEqual(len(re.findall(r"^\d+\. ", markdown, re.M)), 11)

    def test_report_checksum_and_rank_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "recommendations"
            shutil.copytree(DEFAULT_RUNS, dataset)
            path = dataset / "run_001/report.json"
            data = json.loads(path.read_text())
            data["recommendations"][0]["selection_rank"] = 42
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_runs(dataset)
            index = json.loads((dataset / "index.json").read_text())
            index["runs"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (dataset / "index.json").write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "membership/ranks"):
                load_runs(dataset)

    def test_document_check_rejects_missing_reordered_or_duplicate_markers_and_changed_outputs(self):
        reports = load_runs()
        markdown, details = render_list(reports), render_details(reports)
        with tempfile.TemporaryDirectory() as tmp:
            list_path, evidence_path = Path(tmp) / "README.md", Path(tmp) / "evidence.md"
            valid = f"{START}\n{markdown}\n{END}\n"
            evidence_path.write_text(details)
            for document in (markdown, valid.replace(END, ""), valid + START,
                             f"{END}\n{markdown}\n{START}", valid.replace("Birthday Boy", "Changed title")):
                with self.subTest(document=document[:60]):
                    list_path.write_text(document)
                    with self.assertRaises(ValueError):
                        check_documents(reports, list_path=list_path, evidence_path=evidence_path)
            list_path.write_text(valid)
            check_documents(reports, list_path=list_path, evidence_path=evidence_path)
            evidence_path.write_text(details.replace("Birthday Boy", "Changed title"))
            with self.assertRaisesRegex(ValueError, "evidence differs"):
                check_documents(reports, list_path=list_path, evidence_path=evidence_path)

    def test_cli_json_and_document_check_work_offline(self):
        result = subprocess.run([sys.executable, "-B", "-m", "src.readme_demo", "--format", "json"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), load_runs())
        subprocess.run([sys.executable, "-B", "-m", "src.readme_demo", "--check-docs"],
                       cwd=ROOT, capture_output=True, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
