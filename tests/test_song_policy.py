"""Discovery and list constraints are tested against synthetic, adversarial credits."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from src.evaluate_songs import evaluate_split
from src.fetch_musicbrainz import digest
from src.recommend_songs import recommendation_report, recommend_songs
from src.song_policy import active_musicians, build_registry, candidate_eligibility, registry_for, submitted_artists
from test_fetch_musicbrainz import identifier
from test_match_recordings import ENGINEERING, INSTRUMENT


PRODUCER = "5c0ceac3-feb4-41f0-868d-dc06f6e27fc0"
WEIGHTS = {"musician": 1.0, "songwriter": 1.0, "producer": 1.0, "staff": 0.25}


def artist(n):
    return {"id": identifier(n), "name": f"Act {n}"}


def relation(who, role=ENGINEERING, attributes=None):
    return {"target-type": "artist", "artist": who, "type-id": role,
            "type": "instrument" if role == INSTRUMENT else "producer" if role == PRODUCER else "engineer",
            "attributes": attributes or []}


def song(n, primary, credits=None):
    return {"id": identifier(n), "title": f"Song {n}", "artist-credit": [{"artist": a} for a in primary],
            "relations": credits or []}


class SongPolicyTests(unittest.TestCase):
    def setUp(self):
        self.favorite, self.new, self.other, self.engineer = artist(1), artist(2), artist(3), artist(4)
        self.seed = song(100, [self.favorite], [relation(self.engineer)])
        self.registry = build_registry([self.seed], [self.seed["id"]])

    def report(self, candidates, **kwargs):
        return recommendation_report([self.seed] + candidates, [self.seed["id"]],
                                     weights=WEIGHTS, registry=kwargs.pop("registry", self.registry), **kwargs)

    def test_same_artist_is_excluded_even_with_highest_score(self):
        same = song(101, [self.favorite], [relation(self.engineer)])
        novel = song(102, [self.new], [relation(self.engineer)])
        result = self.report([same, novel])
        self.assertEqual([r["recording"]["id"] for r in result["recommendations"]], [novel["id"]])
        self.assertEqual(result["skipped_candidates"][0]["reason"], "submitted_act_without_unfamiliar_collaborator")
        self.assertEqual(recommend_songs([self.seed, same], [self.seed["id"]]), [])

    def test_all_input_names_exclude_unmatched_favorites_and_case_variants(self):
        names = submitted_artists([{"artist_text": self.favorite["name"], "line_number": 1},
                                   {"artist_text": "  ACT 2 ", "line_number": 99}])
        registry = build_registry([self.seed], [self.seed["id"]], names=names)
        candidate = song(101, [self.new], [relation(self.engineer)])
        self.assertFalse(candidate_eligibility(candidate, registry)["eligible"])
        self.assertEqual(registry["submitted_names"][0]["source_lines"], [1])

    def test_permitted_alias_retains_canonical_musician_identity(self):
        first = song(101, [self.favorite], [relation(self.engineer)])
        second = song(102, [self.favorite], [relation(self.engineer)])
        first["artist-credit"][0]["name"] = "Separate Alias"
        second["artist-credit"][0]["name"] = "Second Alias"
        self.registry["allowed_aliases"] = [{"artist_id": self.favorite["id"], "credited_name": name,
                                             "evidence": "Synthetic alias decision"} for name in ("Separate Alias", "Second Alias")]
        result = self.report([first, second])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["skipped_candidates"][0]["reason"], "musician_already_selected")

    def test_side_project_not_merged_with_band_membership(self):
        side = song(101, [self.new], [relation(self.engineer)])
        self.registry["group_members"] = [{"group_id": self.new["id"], "member_id": self.favorite["id"],
                                           "evidence": "Synthetic side-project membership"}]
        result = self.report([side])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertFalse(result["recommendations"][0]["eligibility"]["familiar_collaboration"])
        self.assertEqual(len(active_musicians(side)), 1)

    def test_one_global_collaboration_for_different_favorite_acts(self):
        seed2 = song(104, [self.other], [relation(self.engineer)])
        self.registry = build_registry([self.seed, seed2], [self.seed["id"], seed2["id"]])
        first = song(101, [self.favorite, self.new], [relation(self.favorite, INSTRUMENT)])
        second = song(102, [self.other, artist(5)], [relation(self.other, INSTRUMENT)])
        result = recommendation_report([self.seed, seed2, first, second], [self.seed["id"], seed2["id"]],
                                       weights=WEIGHTS, registry=self.registry)
        self.assertEqual(result["selection_summary"]["familiar_collaborations"], 1)
        self.assertEqual(result["skipped_candidates"][0]["reason"], "familiar_collaboration_limit")

    def test_related_performer_shares_allowance_and_members_only_are_not_collaboration(self):
        member = artist(7)
        self.registry["related_performers"] = [{"artist_id": member["id"], "evidence": "User identifies related performer"}]
        self.registry["group_members"] = [{"group_id": self.favorite["id"], "member_id": member["id"],
                                           "evidence": "Synthetic group membership"}]
        own = song(101, [self.favorite, member], [relation(member, INSTRUMENT)])
        self.assertFalse(candidate_eligibility(own, self.registry)["eligible"])
        related = song(102, [member, self.new], [relation(member, INSTRUMENT), relation(self.engineer)])
        group = song(103, [self.favorite, self.other], [relation(self.favorite, INSTRUMENT)])
        result = self.report([own, related, group])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertTrue(result["recommendations"][0]["eligibility"]["familiar_collaboration"])

    def test_joint_credit_without_performance_evidence_needs_review(self):
        joint = song(101, [self.favorite, self.new])
        self.assertEqual(candidate_eligibility(joint, self.registry)["reason"], "collaboration_needs_review")
        self.registry["verified_collaborations"] = [{"recording_id": joint["id"], "evidence": "Synthetic reviewed collaboration"}]
        self.assertTrue(candidate_eligibility(joint, self.registry)["eligible"])

    def test_sample_and_mashup_do_not_automatically_count_as_collaboration(self):
        sampled = song(101, [self.favorite, self.new], [relation(self.favorite, INSTRUMENT, ["sampled"])])
        self.assertFalse(candidate_eligibility(sampled, self.registry)["eligible"])
        mashup = song(102, [self.favorite, self.new], [relation(self.favorite, INSTRUMENT)])
        mashup["disambiguation"] = "mashup"
        self.assertFalse(candidate_eligibility(mashup, self.registry)["eligible"])

    def test_session_musician_uniqueness_including_musician_producer(self):
        session = artist(8)
        first = song(101, [self.new], [relation(session, INSTRUMENT), relation(session, PRODUCER), relation(self.engineer)])
        second = song(102, [self.other], [relation(session, INSTRUMENT), relation(self.engineer)])
        first["relations"].extend(deepcopy(first["relations"]))
        result = self.report([first, second])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["skipped_candidates"][0]["conflicting_musician_ids"], [session["id"]])
        self.assertEqual(len(active_musicians(first)), 2)

    def test_recurring_explanatory_engineer_or_producer_consumes_one_song(self):
        first = song(101, [self.new], [relation(self.engineer), relation(self.favorite, PRODUCER)])
        second = song(102, [self.other], [relation(self.engineer), relation(self.favorite, PRODUCER)])
        result = self.report([first, second])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["selection_summary"]["familiar_collaborations"], 0)
        self.assertEqual(result["skipped_candidates"][0]["reason"], "contributor_already_selected")
        self.assertEqual(result["skipped_candidates"][0]["conflicting_contributor_ids"],
                         sorted([self.engineer["id"], self.favorite["id"]]))

    def test_vocal_and_guest_performer_credits_reserve_a_single_appearance(self):
        for role in ("0fdbe3c6-7700-4a31-ae54-b53f06ae1cfa", "628a9658-f54c-4142-b0c0-95f031b544da"):
            with self.subTest(role=role):
                guest = artist(8)
                first = song(101, [self.new], [relation(guest, role, ["guest"]), relation(self.engineer)])
                second = song(102, [self.other], [relation(guest, role), relation(self.engineer)])
                result = self.report([first, second])
                self.assertEqual(len(result["recommendations"]), 1)
                self.assertEqual(result["skipped_candidates"][0]["conflicting_musician_ids"], [guest["id"]])

    def test_no_filling_with_forbidden_or_zero_score_songs(self):
        same = song(101, [self.favorite])
        disconnected = song(102, [self.new])
        result = self.report([same, disconnected], limit=10)
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["selection_summary"]["shortfall"], 10)

    def test_soft_diversity_is_redundant_and_replacements_keep_original_scores(self):
        engineer2 = artist(9)
        self.seed["relations"].append(relation(engineer2))
        first = song(101, [self.new], [relation(self.engineer)])
        repeated = song(102, [self.other], [relation(self.engineer)])
        different = song(103, [artist(10)], [relation(engineer2)])
        plain = self.report([first, repeated, different], limit=3)
        diverse = self.report([first, repeated, different], limit=3, diversity="contributors")
        self.assertEqual([r["recording"]["id"] for r in plain["recommendations"]], [identifier(101), identifier(103)])
        self.assertEqual([r["recording"]["id"] for r in diverse["recommendations"]], [identifier(101), identifier(103)])
        self.assertEqual(plain["selection_summary"]["shortfall"], 1)
        for row in diverse["recommendations"]:
            self.assertAlmostEqual(row["score"], sum(e["value"] for e in row["contributor_evidence"]))
            self.assertAlmostEqual(row["selection_score"], sum(e["selection_value"] for e in row["selection_adjustments"]))
        self.assertGreater(diverse["recommendations"][-1]["selection_score"], 0)

    def test_all_connectors_reserved_and_allowances_reset_between_batches(self):
        engineer2 = artist(9)
        self.seed["relations"].append(relation(engineer2))
        first = song(101, [self.new], [relation(self.engineer), relation(engineer2)])
        repeated = song(102, [self.other], [relation(engineer2)])
        report = self.report([first, repeated])
        self.assertEqual(len(report["recommendations"]), 1)
        self.assertEqual(report["selection_summary"]["unique_explanatory_contributors"], 2)
        self.assertEqual(report["skipped_candidates"][0]["conflicting_contributor_ids"], [engineer2["id"]])
        self.assertEqual(report, self.report([repeated, first]))

    def test_contributor_cap_is_global_across_favorites_and_different_roles(self):
        seed2 = song(104, [artist(11)], [relation(self.engineer, PRODUCER)])
        first = song(101, [self.new], [relation(self.engineer, PRODUCER)])
        second = song(102, [self.other], [relation(self.engineer)])
        result = recommendation_report([self.seed, seed2, first, second], [self.seed["id"], seed2["id"]])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["selection_summary"]["repeated_explanatory_contributors"], 0)
        self.assertEqual(result["skipped_candidates"][0]["conflicting_contributor_ids"], [self.engineer["id"]])

    def test_nonconnecting_staff_can_recur(self):
        engineer2, staff = artist(9), artist(10)
        self.seed["relations"].append(relation(engineer2))
        first = song(101, [self.new], [relation(self.engineer), relation(staff)])
        second = song(102, [self.other], [relation(engineer2), relation(staff)])
        self.assertEqual(len(self.report([first, second])["recommendations"]), 2)

    def test_full_registry_source_binding_and_reviewed_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "favorites.json"
            source.write_text(json.dumps({"format_version": 1, "tracks": [{"artist_text": "Unmatched act", "line_number": 6}]}))
            expected = digest(source.read_bytes())
            profile = {"input_sha256": expected}
            registry = registry_for([self.seed], [self.seed["id"]], profile=profile, input_path=source)
            self.assertEqual(registry["scope"], "full_input")
            with self.assertRaisesRegex(ValueError, "different favorites"):
                registry_for([self.seed], [self.seed["id"]], profile={"input_sha256": "wrong"}, input_path=source)
            embedded = profile | {"artist_registry": registry}
            self.assertEqual(registry_for([self.seed], [self.seed["id"]], profile=embedded), registry)
            overrides = Path(directory) / "overrides.json"
            overrides.write_text(json.dumps({"format_version": 1, "input_sha256": expected,
                                            "allowed_aliases": [{"artist_id": self.favorite["id"], "credited_name": "Alias", "evidence": ""}]}))
            with self.assertRaisesRegex(ValueError, "needs evidence"):
                registry_for([self.seed], [self.seed["id"]], profile=embedded, overrides_path=overrides)

    def test_deterministic_selection_with_duplicate_favorites_and_permutations(self):
        candidates = [song(101, [self.new], [relation(self.engineer)]), song(102, [self.other], [relation(self.engineer)])]
        expected = self.report(candidates, diversity="contributors")
        actual = recommendation_report(list(reversed([self.seed] + candidates)) + [self.seed],
                                       [self.seed["id"], self.seed["id"]], registry=self.registry,
                                       weights=WEIGHTS, diversity="contributors")
        self.assertEqual(expected, actual)

    def test_artist_holdout_rejects_same_primary_and_excludes_only_training_names(self):
        with self.assertRaisesRegex(ValueError, "complete-artist"):
            evaluate_split([self.seed, song(101, [self.favorite])], [self.seed["id"]], [identifier(101)],
                           weights=WEIGHTS, saturation_k=5)
        novel = song(102, [self.new], [relation(self.engineer)])
        result = evaluate_split([self.seed, novel], [self.seed["id"]], [novel["id"]], weights=WEIGHTS, saturation_k=5)
        self.assertEqual([a["id"] for a in result["training_artist_registry"]["submitted_artists"]], [self.favorite["id"]])
        self.assertEqual(len(result["comparisons"]), 4)
        for method in result["comparisons"]:
            self.assertEqual(method["metrics"]["10"]["hits"], 1)
            self.assertEqual(method["selection_summary"]["repeated_observed_musicians"], 0)

    def test_research_rejects_full_input_registry_that_contains_holdout_names(self):
        novel = song(102, [self.new], [relation(self.engineer)])
        registry = build_registry([self.seed], [self.seed["id"]], names=submitted_artists([{"artist_text": self.new["name"]}]))
        with self.assertRaisesRegex(ValueError, "only from training"):
            evaluate_split([self.seed, novel], [self.seed["id"]], [novel["id"]], weights=WEIGHTS,
                           saturation_k=5, research=True, collection_training_ids=[self.seed["id"]], collection_registry=registry)
        result = evaluate_split([self.seed, novel], [self.seed["id"]], [novel["id"]], weights=WEIGHTS,
                                saturation_k=5, research=True, collection_training_ids=[self.seed["id"]], collection_registry=self.registry)
        self.assertEqual(result["status"], "exploratory_research")


if __name__ == "__main__":
    unittest.main()
