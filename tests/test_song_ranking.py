"""Song scores, role addition, saturation, and split leakage are independently checked."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from src.build_graph import ROOT
from src.evaluate_songs import equivalence_map, evaluate_split
from src.recommend_songs import contributor_features, load_weights, profile_favorites, score_song_candidates as recommend_songs
from test_fetch_musicbrainz import identifier
from test_match_recordings import ARTIST, ENGINEER, ENGINEERING, INSTRUMENT, R1, R2, recording


WEIGHTS = {"musician": 1.0, "songwriter": 1.0, "producer": 1.0, "staff": 0.25}


def musical_record(rid, contributor, primary=None, attributes=None):
    primary = contributor if primary is None else primary
    return {"id": rid, "title": "Synthetic " + rid[-3:], "artist-credit": [{"artist": primary}],
            "relations": [{"target-type": "artist", "type": "instrument", "type-id": INSTRUMENT,
                           "artist": contributor, "attributes": attributes or []}]}


class SongRankingTests(unittest.TestCase):
    def test_independent_additive_role_arithmetic_and_contribution_sum(self):
        first, second = recording(), recording(R2)
        row = recommend_songs([first, second], [R1], weights=WEIGHTS)[0]
        # Shared musician+writer: 2*2=4. Shared engineer: .25*.25=.0625.
        raw = 4 + 0.25 ** 2
        expected = raw / (1 + raw) * (1 / 6)
        self.assertAlmostEqual(row["score"], expected)
        self.assertEqual(row["score"], sum(c["value"] for c in row["contributions"]))
        musician = contributor_features(first, WEIGHTS)[ARTIST["id"]]
        self.assertEqual(musician["weight"], 2)
        self.assertEqual(set(musician["categories"]), {"musician", "songwriter"})

    def test_musicians_have_equal_weight_despite_instrument_and_guest_labels(self):
        lead = musical_record(R1, ARTIST, attributes=["lead vocals"])
        guest = musical_record(R2, ARTIST, attributes=["guest", "triangle"])
        self.assertEqual(contributor_features(lead, WEIGHTS)[ARTIST["id"]]["weight"], 1)
        self.assertEqual(contributor_features(guest, WEIGHTS)[ARTIST["id"]]["weight"], 1)
        self.assertAlmostEqual(recommend_songs([lead, guest], [R1], weights=WEIGHTS)[0]["score"], 0.5 / 6)

    def test_duplicate_roles_and_multiple_instruments_do_not_increase_weight(self):
        first, second = recording(), recording(R2)
        before = recommend_songs([first, second], [R1], weights=WEIGHTS)
        first["relations"].extend(deepcopy(first["relations"]))
        first["relations"].append(first["relations"][0] | {"attributes": ["piano"]})
        second["relations"].append(second["relations"][0] | {"attributes": ["organ"]})
        after = recommend_songs([first, second], [R1, R1], weights=WEIGHTS)
        self.assertEqual(before[0]["score"], after[0]["score"])
        self.assertEqual(contributor_features(first, WEIGHTS)[ARTIST["id"]]["weight"], 2)

    def test_engineering_only_connection_has_positive_lower_weight(self):
        other = {"id": identifier(150), "name": "Other primary", "type": "Person"}
        first = musical_record(R1, ARTIST)
        second = musical_record(R2, other)
        relation = {"target-type": "artist", "type": "engineer", "type-id": ENGINEERING, "artist": ENGINEER}
        first["relations"] = [relation]
        second["relations"] = [relation]
        row = recommend_songs([first, second], [R1], weights=WEIGHTS)[0]
        self.assertAlmostEqual(row["score"], (0.0625 / 1.0625) / 6)
        self.assertGreater(row["score"], 0)
        self.assertEqual(row["contributions"][0]["contributors"][0]["favorite_roles"], ["staff"])

    def test_saturated_artist_influence_is_bounded_and_diminishes(self):
        candidate = musical_record(R2, ARTIST)
        scores = []
        for count in (1, 5, 20, 100):
            favorites = [musical_record(identifier(200 + i), ARTIST) for i in range(count)]
            row = recommend_songs(favorites + [candidate], [r["id"] for r in favorites], weights=WEIGHTS)[0]
            self.assertAlmostEqual(row["score"], 0.5 * count / (count + 5))
            self.assertLess(row["artist_contributions"][0]["score"], 1)
            scores.append(row["score"])
        self.assertLess(scores[0], scores[1])
        self.assertLess(scores[1], scores[2])
        self.assertLess(scores[2], scores[3])
        favorites = [musical_record(identifier(200 + i), ARTIST) for i in range(20)]
        linear = recommend_songs(favorites + [candidate], [r["id"] for r in favorites], weights=WEIGHTS, saturation_k=None)[0]
        self.assertAlmostEqual(linear["score"], 10)

    def test_seed_exclusion_empty_unknown_and_explicit_equivalents(self):
        records = [recording(), recording(R2)]
        self.assertEqual(recommend_songs(records, [], weights=WEIGHTS), [])
        with self.assertRaisesRegex(ValueError, "Unknown favorite"):
            recommend_songs(records, [identifier(999)], weights=WEIGHTS)
        self.assertEqual(recommend_songs(records, [R1], weights=WEIGHTS, excluded_ids={R2}), [])
        self.assertEqual([r["recording"]["id"] for r in recommend_songs(records, [R1], weights=WEIGHTS)], [R2])

    def test_deterministic_duplicate_recordings_and_permutations(self):
        records = [recording(), recording(R2), recording(identifier(113))]
        expected = recommend_songs(records, [R1], weights=WEIGHTS)
        self.assertEqual(expected, recommend_songs(list(reversed(records)) + [records[0]], [R1, R1], weights=WEIGHTS))
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            recommend_songs(records + [recording(title="Conflicting title")], [R1], weights=WEIGHTS)

    def test_profile_requires_matching_snapshot_hashes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps({"format_version": 1, "favorites": [{"recording_id": R1, "source_sha256": "correct"}]}))
            self.assertEqual(profile_favorites(path, {"sources": [{"recording_id": R1, "sha256": "correct"}]}), [R1])
            with self.assertRaisesRegex(ValueError, "snapshots"):
                profile_favorites(path, {"sources": [{"recording_id": R1, "sha256": "wrong"}]})

    def test_profile_registry_is_bound_to_dataset_manifest(self):
        import tempfile
        from src.song_policy import build_registry, registry_digest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            registry = build_registry([recording()], [R1])
            data = {"format_version": 1, "favorites": [{"recording_id": R1, "source_sha256": "correct"}], "artist_registry": registry}
            manifest = {"sources": [{"recording_id": R1, "sha256": "correct"}], "artist_registry_sha256": registry_digest(registry)}
            path.write_text(json.dumps(data))
            self.assertEqual(profile_favorites(path, manifest), [R1])
            data["artist_registry"]["related_performers"] = [{"artist_id": ENGINEER["id"], "evidence": "Tampered"}]
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "registry"):
                profile_favorites(path, manifest)

    def test_song_demo_cli_produces_recordings_and_full_contributions(self):
        result = subprocess.run([sys.executable, "-B", "-m", "src.recommend_songs", "--format", "json"],
                                cwd=ROOT, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["candidate_count"], 3)
        for row in data["recommendations"]:
            self.assertIn("recording", row)
            self.assertAlmostEqual(row["score"], sum(c["value"] for c in row["contributions"]))


class SongEvaluationTests(unittest.TestCase):
    def test_overall_and_reachable_counts_include_missing_targets(self):
        novel = recording(R2)
        novel["artist-credit"] = [{"artist": {"id": identifier(150), "name": "Novel act"}}]
        result = evaluate_split([recording(), novel], [R1], [R2, identifier(999)],
                                weights=WEIGHTS, saturation_k=5)
        self.assertEqual(result["status"], "demonstration_diagnostics")
        for method in result["comparisons"]:
            self.assertEqual(method["heldout_in_graph"], 1)
            self.assertEqual(method["heldout_reachable"], 1)
            self.assertEqual(method["metrics"]["10"]["overall_recall"], 0.5)
            self.assertEqual(method["metrics"]["10"]["reachable_recall"], 1)

    def test_equivalent_appearances_cannot_cross_training_and_holdout(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            evaluate_split([recording(), recording(R2)], [R1], [R2], weights=WEIGHTS,
                           saturation_k=5, equivalent_groups=[[R1, R2]])
        third = identifier(113)
        aliases = equivalence_map([[R1, R2], [R2, third]])
        self.assertEqual(len(set(aliases.values())), 1)

    def test_zero_score_candidates_are_not_counted_as_reachable_hits(self):
        other = {"id": identifier(150), "name": "Unconnected primary"}
        result = evaluate_split([musical_record(R1, ARTIST), musical_record(R2, other)],
                                [R1], [R2], weights=WEIGHTS, saturation_k=5)
        for method in result["comparisons"]:
            self.assertEqual(method["heldout_reachable"], 0)
            self.assertEqual(method["metrics"]["20"]["hits"], 0)
            self.assertIsNone(method["metrics"]["20"]["reachable_recall"])

    def test_research_mode_requires_training_bound_collection_provenance(self):
        with self.assertRaisesRegex(ValueError, "collection provenance"):
            evaluate_split([recording(), recording(R2)], [R1], [R2], weights=WEIGHTS, saturation_k=5, research=True)
        with self.assertRaisesRegex(ValueError, "collection provenance"):
            evaluate_split([recording(), recording(R2)], [R1], [R2], weights=WEIGHTS, saturation_k=5,
                           research=True, collection_training_ids=[R1, R2])


if __name__ == "__main__":
    unittest.main()
