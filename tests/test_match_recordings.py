"""Identity safety and provenance checks use synthetic MusicBrainz data only."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from src.build_graph import load_dataset
from src.credits import SONGWRITING_IDS, credit_coverage, extract_credits
from src.fetch_musicbrainz import Limits, MusicBrainzClient, digest, json_bytes
from src.match_recordings import MatchRules, candidate_checks, load_input, load_reviews, match_batch, search_query
from test_fetch_musicbrainz import FakeClock, Response, identifier


ARTIST = {"id": identifier(101), "name": "Synthetic musician", "type": "Person"}
ENGINEER = {"id": identifier(102), "name": "Synthetic engineer", "type": "Person"}
TRACK = {"line_number": 1, "original_line": "preserved source row", "artist_text": ARTIST["name"],
         "song_text": "Synthetic song", "album_text": "Synthetic album", "duration_text": "3:00"}
R1, R2, WORK, RELEASE = [identifier(n) for n in (111, 112, 121, 131)]
WRITER = "a255bca1-b157-4518-9108-7b147dc3fc68"
INSTRUMENT = "59054b12-01ac-43ee-a618-285fd397e461"
ENGINEERING = "5dcc52af-7064-4051-8d62-7d80f4c3c907"


def recording(rid=R1, **overrides):
    return {"id": rid, "title": TRACK["song_text"], "length": 180000,
            "artist-credit": [{"artist": ARTIST, "name": ARTIST["name"]}],
            "disambiguation": "", "video": False,
            "releases": [{"id": RELEASE, "title": TRACK["album_text"]}],
            "relations": [
                {"target-type": "artist", "artist": ARTIST, "type": "instrument", "type-id": INSTRUMENT,
                 "attributes": ["drums"]},
                {"target-type": "artist", "artist": ENGINEER, "type": "engineer", "type-id": ENGINEERING},
                {"target-type": "work", "type": "performance", "type-id": identifier(140),
                 "work": {"id": WORK, "title": "Synthetic work", "relations": [
                     {"target-type": "artist", "artist": ARTIST, "type": "writer", "type-id": WRITER}]}}],
            **overrides}


class Transport:
    def __init__(self, records, search_rows=None, reported_total=None):
        self.records = {r["id"]: r for r in records}
        self.search_rows = list(records) if search_rows is None else search_rows
        self.reported_total = len(self.search_rows) if reported_total is None else reported_total
        self.calls = []

    def __call__(self, request, timeout):
        parsed = urlparse(request.full_url)
        self.calls.append(request.full_url)
        endpoint = parsed.path.removeprefix("/ws/2/")
        params = parse_qs(parsed.query)
        if endpoint == "recording":
            offset, limit = int(params["offset"][0]), int(params["limit"][0])
            return Response({"count": self.reported_total, "offset": offset,
                             "recordings": self.search_rows[offset:offset + limit]})
        return Response(self.records[endpoint.removeprefix("recording/")])


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = FakeClock()
        self.metadata = {"input_sha256": "synthetic-input", "input_rows": 1}

    def run_batch(self, transport, *, name="result", tracks=None, rules=None, limits=None,
                  reviews=None, offline=False):
        with MusicBrainzClient(self.root / "cache", limits or Limits(), contact="test@project.invalid",
                              opener=transport, offline=offline, clock=self.clock.time,
                              sleep=self.clock.sleep) as client:
            return match_batch(client, tracks or [deepcopy(TRACK)], dict(self.metadata), self.root / name,
                               rules or MatchRules(), reviews=reviews)

    def rows(self, name="result"):
        return json.loads((self.root / name / "matches.json").read_text())

    def test_unique_multi_signal_match_preserves_scope_and_profile(self):
        manifest = self.run_batch(Transport([recording()]))
        row = self.rows()[0]
        self.assertEqual(row["status"], "accepted")
        self.assertEqual(row["acceptance_basis"], "rule_based")
        self.assertEqual(row["source_row"], TRACK)
        writer = next(c for c in row["candidates"][0]["credits"] if c["category"] == "songwriter")
        self.assertEqual((writer["scope"], writer["work_id"]), ("work", WORK))
        self.assertEqual(writer["source_url"], f"https://musicbrainz.org/work/{WORK}")
        self.assertEqual(writer["work_link"]["type"], "performance")
        self.assertEqual(manifest["stats"]["accepted_distinct_recordings"], 1)
        records, _ = load_dataset(self.root / "result")
        self.assertEqual(records, [recording()])
        profile = json.loads((self.root / "result/profile.json").read_text())
        self.assertEqual(profile["favorites"][0]["recording_id"], R1)
        self.assertEqual(profile["independent_human_audit"], "pending")

    def test_small_matching_batch_retains_all_submitted_artist_exclusions(self):
        source = self.root / "favorites.json"
        source.write_bytes(json_bytes({"format_version": 1, "tracks": [TRACK,
                                       TRACK | {"line_number": 2, "artist_text": "Unmatched artist"}], "needs_review": []}))
        tracks, self.metadata = load_input(source, count=1)
        self.run_batch(Transport([recording()]), tracks=tracks)
        profile = json.loads((self.root / "result/profile.json").read_bytes())
        registry = profile["artist_registry"]
        self.assertEqual(registry["scope"], "full_input")
        self.assertEqual({n["normalized_name"] for n in registry["submitted_names"]}, {ARTIST["name"].casefold(), "unmatched artist"})
        self.assertEqual(len(profile["favorites"]), 1)
        self.assertEqual(registry["input_sha256"], digest(source.read_bytes()))

    def test_multiple_qualifying_ids_are_not_auto_accepted(self):
        self.run_batch(Transport([recording(), recording(R2)]))
        self.assertEqual(self.rows()[0]["status"], "needs_review")
        self.assertIsNone(self.rows()[0]["accepted_recording_id"])

    def test_score_100_does_not_override_missing_or_conflicting_evidence(self):
        for index, changes in enumerate([
            {"releases": []}, {"length": 184000}, {"length": None},
            {"disambiguation": "live"}, {"video": True},
            {"artist-credit": [{"artist": ARTIST | {"name": "Wrong artist"}}]},
        ]):
            with self.subTest(changes=changes):
                self.run_batch(Transport([recording(score="100", **changes)]), name=f"case{index}")
                # Unique cache per variant is necessary: a cache deliberately freezes a response.
                row = self.rows(f"case{index}")[0]
                if index == 0:
                    self.assertFalse(row["candidates"][0]["checks"]["album_absence_is_conclusive"])
                self.assertEqual(row["status"], "needs_review")
                self.root = self.root / f"next{index}"
                self.root.mkdir()

    def test_explicit_live_version_is_preserved_as_distinct_identity(self):
        track = TRACK | {"song_text": "Synthetic song (live)"}
        rec = recording(title=track["song_text"], disambiguation="live")
        self.run_batch(Transport([rec]), tracks=[track])
        self.assertEqual(self.rows()[0]["status"], "accepted")
        self.assertEqual(self.rows()[0]["candidates"][0]["disambiguation"], "live")

    def test_search_paging_uses_returned_count_and_preserves_alternatives(self):
        transport = Transport([recording(), recording(R2)])
        self.run_batch(transport, rules=replace(MatchRules(), search_page_size=1))
        row = self.rows()[0]
        self.assertEqual([p["offset"] for p in row["search"]["pages"]], [0, 1])
        self.assertTrue(row["search"]["complete"])
        self.assertEqual(row["status"], "needs_review")

    def test_page_limit_prevents_false_unique_acceptance(self):
        self.run_batch(Transport([recording(), recording(R2)]),
                       rules=replace(MatchRules(), search_page_size=1, max_search_pages=1))
        self.assertFalse(self.rows()[0]["search"]["complete"])
        self.assertEqual(self.rows()[0]["status"], "needs_review")

    def test_uninspected_exact_candidates_prevent_acceptance(self):
        self.run_batch(Transport([recording(), recording(R2)]),
                       rules=replace(MatchRules(), max_recordings_per_song=1))
        self.assertEqual(self.rows()[0]["search"]["omitted_exact_ids"], [R2])
        self.assertEqual(self.rows()[0]["status"], "needs_review")

    def test_empty_search_and_failed_search_have_distinct_statuses(self):
        self.run_batch(Transport([]))
        self.assertEqual(self.rows()[0]["status"], "no_result")
        self.run_batch(lambda *a, **kw: self.fail("Network forbidden"), name="offline",
                       tracks=[TRACK | {"song_text": "Uncached song"}], offline=True)
        self.assertEqual(self.rows("offline")[0]["status"], "not_searched")

    def test_request_budget_saves_partial_and_does_not_accept(self):
        manifest = self.run_batch(Transport([recording()]), limits=replace(Limits(), max_requests=1))
        self.assertEqual(manifest["network_attempts"], 1)
        self.assertEqual(manifest["collection_status"], "partial")
        self.assertEqual(self.rows()[0]["status"], "needs_review")
        self.assertTrue((self.root / "result/profile.json").exists())

    def test_offline_replay_has_identical_decisions_and_sources(self):
        first = self.run_batch(Transport([recording()]))
        with patch.object(socket, "socket", side_effect=AssertionError("Network forbidden")):
            replay = self.run_batch(lambda *a, **kw: self.fail("Network forbidden"), name="replay", offline=True)
        self.assertEqual(replay["network_attempts"], 0)
        self.assertEqual(first["sample_id"], replay["sample_id"])
        for filename in ("matches.json", "profile.json", "credit_audit.json", "reviews_template.json"):
            self.assertEqual((self.root / "result" / filename).read_bytes(), (self.root / "replay" / filename).read_bytes())

    def test_duplicate_favorite_rows_preserve_input_but_do_not_increase_profile(self):
        manifest = self.run_batch(Transport([recording()]), tracks=[TRACK, TRACK | {"line_number": 2}])
        self.assertEqual(manifest["stats"]["accepted_distinct_recordings"], 1)
        profile = json.loads((self.root / "result/profile.json").read_text())
        self.assertEqual(profile["favorites"][0]["source_lines"], [1, 2])
        self.assertEqual(manifest["network_attempts"], 2)

    def test_explicit_review_can_select_one_version_or_leave_unresolved(self):
        review = {1: {"status": "accepted", "recording_id": R2,
                      "reviewer": "Synthetic reviewer", "evidence": "Synthetic release/version check"}}
        self.run_batch(Transport([recording(), recording(R2)]), reviews=review)
        self.assertEqual(self.rows()[0]["accepted_recording_id"], R2)
        self.assertEqual(self.rows()[0]["acceptance_basis"], "human_review")
        self.run_batch(Transport([recording()]), name="unresolved", reviews={1: {
            "status": "unresolved", "reviewer": "Synthetic reviewer", "evidence": "Version cannot be established"}})
        self.assertEqual(self.rows("unresolved")[0]["status"], "needs_review")

    def test_manual_review_cannot_accept_unfetched_id(self):
        with self.assertRaisesRegex(ValueError, "fetched candidate"):
            self.run_batch(Transport([recording()]), reviews={1: {
                "status": "accepted", "recording_id": R2, "reviewer": "Reviewer", "evidence": "Evidence"}})

    def test_output_is_immutable(self):
        self.run_batch(Transport([recording()]))
        original = (self.root / "result/matches.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_batch(Transport([]))
        self.assertEqual((self.root / "result/matches.json").read_bytes(), original)

    def test_selection_and_reviews_are_bound_to_original_source(self):
        path = self.root / "favorites.json"
        path.write_bytes(json_bytes({"format_version": 1, "tracks": [TRACK]}))
        selection = self.root / "selection.json"
        selection.write_bytes(json_bytes({"favorite_source_sha256": digest(path.read_bytes()),
                                         "selected_source_line_numbers": [1]}))
        tracks, metadata = load_input(path, selection)
        self.assertEqual(tracks, [TRACK])
        selection.write_text(json.dumps({"favorite_source_sha256": "wrong", "selected_source_line_numbers": [1]}))
        with self.assertRaisesRegex(ValueError, "different favorites"):
            load_input(path, selection)
        review_path = self.root / "reviews.json"
        review_path.write_bytes(json_bytes({"format_version": 1, "input_sha256": metadata["input_sha256"],
                                           "decisions": [{"line_number": 1, "status": "accepted", "recording_id": R1,
                                                          "reviewer": "", "evidence": ""}]}))
        with self.assertRaisesRegex(ValueError, "reviewer and evidence"):
            load_reviews(review_path, metadata, tracks)

    def test_lucene_special_characters_are_literal(self):
        query = search_query(TRACK | {"song_text": 'A "quoted" song: (live)', "artist_text": "AC/DC"})
        self.assertIn('recording:"A \\"quoted\\" song\\: \\(live\\)"', query)
        self.assertIn('artist:"AC\\/DC"', query)


class CreditTests(unittest.TestCase):
    def test_same_artist_can_have_musician_and_songwriter_categories(self):
        credits = extract_credits(recording())
        categories = {c["category"] for c in credits if c["artist"]["id"] == ARTIST["id"]}
        self.assertEqual(categories, {"musician", "songwriter"})
        stats = credit_coverage([recording(), recording()])
        self.assertEqual(stats["recordings_inspected"], 1)
        self.assertEqual(stats["recordings_with_category"]["staff"], 1)
        self.assertEqual(stats["recordings"][0]["musician_and_songwriter_entities"], [ARTIST["id"]])

    def test_unknown_executive_and_release_roles_are_retained_without_promotion(self):
        rec = recording()
        extras = [{"target-type": "artist", "artist": ENGINEER, "type": "engineer", "type-id": ENGINEERING, "level": "release"},
                  {"target-type": "artist", "artist": ENGINEER, "type": "producer",
                   "type-id": "5c0ceac3-feb4-41f0-868d-dc06f6e27fc0", "attributes": ["executive"]},
                  {"target-type": "artist", "artist": ENGINEER, "type": "unknown", "type-id": identifier(199)}]
        rec["relations"].extend(extras)
        credits = extract_credits(rec)
        unmapped = [c for c in credits if c["category"] is None]
        self.assertEqual(len(unmapped), 3)
        self.assertIn("release", {c["scope"] for c in unmapped})
        rec["relations"].extend(deepcopy(rec["relations"]))
        self.assertEqual(extract_credits(rec), credits)


if __name__ == "__main__":
    unittest.main()
