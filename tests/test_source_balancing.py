"""Adversarial source assignments and observed composition uniqueness."""

from copy import deepcopy
import unittest

from src.recommend_songs import recommendation_report
from src.source_songs import known_work_ids, source_song_groups
from test_song_policy import PRODUCER, INSTRUMENT, artist, relation, song
from test_fetch_musicbrainz import identifier


def with_works(record, *numbers):
    return record | {"relations": record["relations"] + [
        {"target-type": "work", "type": "performance", "work": {"id": identifier(n)}} for n in numbers]}


def report(records, favorites, **options):
    return recommendation_report(records, favorites, contributor_policy="penalized",
        seed_balancing=True, deduplicate_works=True, **options)


class SourceBalancingTests(unittest.TestCase):
    def test_first_appearances_precede_second_and_caps_keep_shortfall(self):
        seeds = [song(n, [artist(a)], [relation(artist(c), role)])
                 for n, a, c, role in ((100, 1, 10, PRODUCER), (200, 2, 20, None), (300, 3, 30, None))]
        # Use actual mapped engineering credits for the lower-scoring sources.
        seeds[1]["relations"] = [relation(artist(20))]
        seeds[2]["relations"] = [relation(artist(30))]
        candidates = [song(101+n, [artist(101+n)], [relation(artist(10), PRODUCER)]) for n in range(10)]
        candidates += [song(201, [artist(201)], [relation(artist(20))]), song(301, [artist(301)], [relation(artist(30))])]
        result = report(seeds + candidates, [s["id"] for s in seeds], limit=15)
        assignments = [r["primary_seed_song"]["source_group_id"] for r in result["recommendations"]]
        self.assertEqual(len(set(assignments[:3])), 3)
        self.assertEqual(len(result["recommendations"]), 4)
        self.assertEqual(sorted(result["selection_summary"]["recommendations_per_source"].values()), [1, 1, 2])
        self.assertEqual(result["selection_summary"]["source_coverage_shortfall"], 0)
        self.assertGreater(result["selection_summary"]["shortfall"], 0)

    def test_multisource_candidate_has_one_supported_assignment_and_all_evidence(self):
        seeds = [song(100+n, [artist(1+n)], [relation(artist(10))]) for n in range(3)]
        candidates = [song(200+n, [artist(20+n)], [relation(artist(10))]) for n in range(3)]
        result = report(seeds + candidates, [s["id"] for s in seeds], limit=3)
        groups = []
        for row in result["recommendations"]:
            groups.append(row["primary_seed_song"]["source_group_id"])
            self.assertEqual(len(row["contributions"]), 3)
            self.assertIn(row["primary_seed_song"]["source_group_id"], row["source_assignment_evidence"])
        self.assertEqual(len(set(groups)), 3)

    def test_covers_and_partial_multiwork_overlap_are_excluded(self):
        seed = song(100, [artist(1)], [relation(artist(10))])
        candidates = [with_works(song(200+n, [artist(20+n)], [relation(artist(10))]), 700) for n in range(5)]
        candidates.append(with_works(song(300, [artist(30)], [relation(artist(10))]), 700, 701))
        result = report([seed] + candidates, [seed["id"]], limit=5)
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["selection_summary"]["known_work_exclusions"], 5)
        self.assertEqual(result["selection_summary"]["source_coverage_shortfall"], 2)
        self.assertEqual(known_work_ids(candidates[-1]), {identifier(700), identifier(701)})

    def test_titles_do_not_define_compositions_and_unknowns_remain_visible(self):
        seed = song(100, [artist(1)], [relation(artist(10))])
        candidates = [with_works(song(200+n, [artist(20+n)], [relation(artist(10))]) | {"title": "Same title"}, 700+n) for n in range(2)]
        self.assertEqual(len(report([seed] + candidates, [seed["id"]], limit=2)["recommendations"]), 2)
        unknown = [song(300+n, [artist(30+n)], [relation(artist(10))]) for n in range(2)]
        self.assertEqual(report([seed] + unknown, [seed["id"]], limit=2)["selection_summary"]["selected_unknown_work_identity"], 2)

    def test_equivalent_seed_work_sets_and_duplicate_ids_are_one_group(self):
        seeds = [with_works(song(100+n, [artist(1+n)], [relation(artist(10))]), 700) for n in range(2)]
        mapping, groups = source_song_groups(seeds, [s["id"] for s in seeds] * 2)
        self.assertEqual(len(groups), 1)
        candidates = [song(200+n, [artist(20+n)], [relation(artist(10))]) for n in range(4)]
        result = report(seeds + candidates, [s["id"] for s in seeds], limit=5)
        self.assertEqual(len(result["recommendations"]), 2)
        self.assertEqual(result["selection_summary"]["represented_source_groups"], 1)

    def test_legacy_policy_and_base_scores_remain_unchanged(self):
        seed = song(100, [artist(1)], [relation(artist(10))])
        candidates = [song(200+n, [artist(20+n)], [relation(artist(10))]) for n in range(4)]
        legacy = recommendation_report([seed] + candidates, [seed["id"]], contributor_policy="penalized", limit=5)
        balanced = report([seed] + candidates, [seed["id"]], limit=5)
        self.assertEqual(len(legacy["recommendations"]), 4)
        self.assertEqual(len(balanced["recommendations"]), 2)
        self.assertEqual(legacy["recommendations"][0]["score"], balanced["recommendations"][0]["score"])
        self.assertFalse(legacy["source_policy"]["enabled"])
        self.assertEqual(len(recommendation_report([seed] + candidates, [seed["id"]])["recommendations"]), 1)

    def test_performer_conflict_reports_greedy_coverage_limit(self):
        a = song(100, [artist(1)], [relation(artist(10), PRODUCER)])
        b = song(200, [artist(2)], [relation(artist(20))])
        one = song(101, [artist(101)], [relation(artist(10), PRODUCER), relation(artist(999), INSTRUMENT)])
        two = song(201, [artist(201)], [relation(artist(20)), relation(artist(999), INSTRUMENT)])
        alternative = song(102, [artist(102)], [relation(artist(10))])
        result = report([a, b, one, two, alternative], [a["id"], b["id"]], limit=3)
        self.assertEqual(result["selection_summary"]["represented_source_groups"], 1)
        self.assertTrue(any(r["reason"] == "musician_already_selected" for r in result["skipped_candidates"]))
        self.assertIn("no assignment repair", result["selection_limitations"][0])


if __name__ == "__main__":
    unittest.main()
