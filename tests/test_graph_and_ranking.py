"""Independent fixture arithmetic and graph/ranking invariants, all offline."""

from copy import deepcopy
import hashlib
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from src.build_graph import ROOT, build_graph, load_fixture, load_rules
from src.parse_library import parse_favorites
from src.recommend import explain_contribution, recommend


BEATLES = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
GET_BACK = "beaf49d4-c864-4141-9ce0-162e16778d87"
DONT_LET = "76a0136f-d130-4a63-81e9-f7a438a86442"
GUITAR = "863288d1-0fb0-410f-ac45-98e0bd62eac1"
TEARS = "21ddde6c-90f4-469e-bdd0-1f438d011917"
CORE = {"The Beatles", "George Martin", "George Harrison", "John Lennon", "Paul McCartney", "Ringo Starr"}
TEARS_ONLY = {"Alex Haas", "Ed Cherney", "Gayle Levant", "Jay Dee Maness", "Jeff DeMorris",
              "Jimmy Bralower", "Lenny Castro", "Nathan East", "Randy Kerber", "Russ Titelman"}


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.manifest = load_fixture()
        cls.graph = build_graph(cls.records)
        cls.ids = {a["name"]: a["id"] for a in cls.graph.artists.values()}

    def by_name(self, method="two-hop", seeds=None):
        return {r["artist"]["name"]: r for r in recommend(self.graph, [BEATLES] if seeds is None else seeds, method)}

    def test_independent_recording_artist_sets(self):
        expected = {GET_BACK: CORE | {"Billy Preston", "Glyn Johns"},
                    DONT_LET: CORE | {"Billy Preston"},
                    GUITAR: CORE | {"Ken Scott", "Eric Clapton"},
                    TEARS: TEARS_ONLY | {"Eric Clapton"}}
        for rid, names in expected.items():
            self.assertEqual({self.graph.artists[a]["name"] for a in self.graph.credits[rid]}, names)

    def test_independent_graph_counts_and_density(self):
        stats = self.graph.stats()
        self.assertEqual((stats["artists"], stats["recordings"], stats["edges"], stats["edge_contributions"]), (20, 4, 96, 132))
        self.assertEqual({r["recording_id"]: (r["eligible_artists"], r["edges"]) for r in stats["recording_density"]},
                         {GET_BACK: (8, 28), DONT_LET: (7, 21), GUITAR: (8, 28), TEARS: (11, 55)})
        self.assertEqual(stats["artist_degrees"][self.ids["Eric Clapton"]], 17)

    def test_all_expected_scores(self):
        expected = {name: (3, 3, 6) for name in CORE - {"The Beatles"}}
        expected["Billy Preston"] = (2, 3, 5)
        expected.update({name: (1, 2, 3) for name in ["Eric Clapton", "Glyn Johns", "Ken Scott"]})
        expected.update({name: (0, 1, 1) for name in TEARS_ONLY})
        rows = self.by_name()
        self.assertEqual(set(rows), set(expected))
        for name, scores in expected.items():
            row = rows[name]
            self.assertEqual((row["direct_score"], row["two_hop_score"], row["score"]), scores, name)
        direct = self.by_name("direct")
        self.assertEqual(set(rows), set(direct))
        for name, row in direct.items():
            self.assertEqual(row["score"], expected[name][0])
            self.assertEqual(row["two_hop_score"], 0)

    def test_every_edge_has_source_and_eligible_roles(self):
        rules = load_rules()
        for aid, neighbors in self.graph.adjacency.items():
            self.assertNotIn(aid, neighbors)
            for bid, evidence in neighbors.items():
                self.assertEqual(evidence, self.graph.evidence(bid, aid))
                self.assertEqual(len(evidence), len({e["recording"]["id"] for e in evidence}))
                for edge in evidence:
                    rid = edge["recording"]["id"]
                    self.assertEqual(edge["recording"]["source_url"], f"https://musicbrainz.org/recording/{rid}")
                    self.assertEqual(set(edge["credits"]), {aid, bid})
                    for artist, credits in edge["credits"].items():
                        self.assertTrue(credits)
                        self.assertEqual(credits, self.graph.credits[rid][artist])
                        for credit in credits:
                            self.assertTrue(credit["role"] == "primary artist" or credit["relationship_type_id"] in rules["eligible_relationships"])

    def test_all_contributions_sum_and_paths_are_valid(self):
        seeds = {BEATLES, self.ids["Billy Preston"]}
        for row in recommend(self.graph, list(seeds)):
            candidate = row["artist"]["id"]
            self.assertNotIn(candidate, seeds)
            self.assertEqual(row["score"], sum(c["value"] for c in row["contributions"]))
            unique = set()
            for c in row["contributions"]:
                self.assertEqual(c["candidate_id"], candidate)
                if c["kind"] == "direct":
                    self.assertIn(c["evidence"], self.graph.evidence(c["seed_id"], candidate))
                    key = (c["kind"], c["seed_id"], c["evidence"]["recording"]["id"])
                else:
                    self.assertEqual(len(set(c["recording_pair"])), 2)
                    key = (c["kind"], c["seed_id"], *c["recording_pair"])
                    for p in c["paths"]:
                        h = p["intermediary_id"]
                        self.assertNotIn(h, seeds | {candidate})
                        self.assertIn(p["first_edge"], self.graph.evidence(c["seed_id"], h))
                        self.assertIn(p["second_edge"], self.graph.evidence(h, candidate))
                        self.assertEqual(sorted([p["first_edge"]["recording"]["id"], p["second_edge"]["recording"]["id"]]), c["recording_pair"])
                self.assertNotIn(key, unique)
                unique.add(key)

    def test_nathan_east_one_point_via_clapton(self):
        row = self.by_name()["Nathan East"]
        self.assertEqual(len(row["contributions"]), 1)
        c = row["contributions"][0]
        self.assertEqual(set(c["recording_pair"]), {GUITAR, TEARS})
        self.assertEqual([p["intermediary_id"] for p in c["paths"]], [self.ids["Eric Clapton"]])
        explanation = " ".join(explain_contribution(self.graph, c))
        self.assertEqual(explanation.count("both credited on"), 2)
        self.assertIn("degree 17", explanation)

    def test_several_intermediaries_and_orientations_count_once(self):
        row = self.by_name()["George Martin"]
        c = next(c for c in row["contributions"] if c["kind"] == "two-hop" and set(c["recording_pair"]) == {GET_BACK, DONT_LET})
        self.assertEqual(c["value"], 1)
        self.assertEqual(len(c["paths"]), 10)  # Five intermediaries, both recording orientations.
        self.assertEqual(len({p["intermediary_id"] for p in c["paths"]}), 5)

    def test_one_recording_does_not_create_two_hop_evidence(self):
        graph = build_graph([next(r for r in self.records if r["id"] == GET_BACK)])
        for row in recommend(graph, [BEATLES]):
            self.assertEqual((row["direct_score"], row["two_hop_score"]), (1, 0))

    def test_duplicates_and_multiple_roles_do_not_inflate_scores(self):
        repeated = deepcopy(self.records)
        repeated[0]["relations"] *= 2
        repeated[0]["artist-credit"] *= 2
        repeated += deepcopy(self.records)
        graph = build_graph(repeated)
        self.assertEqual(graph.stats(), self.graph.stats())
        self.assertEqual(recommend(graph, [BEATLES, BEATLES]), recommend(self.graph, [BEATLES]))
        ed = self.graph.credits[TEARS][self.ids["Ed Cherney"]]
        self.assertEqual({c["role"] for c in ed}, {"mix", "recording"})

    def test_group_and_member_are_separate_entities(self):
        self.assertEqual(self.graph.artists[BEATLES]["type"], "Group")
        self.assertNotEqual(BEATLES, self.ids["Paul McCartney"])
        record = deepcopy(next(r for r in self.records if r["id"] == GUITAR))
        record["relations"] = []
        graph = build_graph([record])
        self.assertEqual(set(graph.artists), {BEATLES})
        self.assertEqual(graph.stats()["edges"], 0)

    def test_work_only_writer_excluded_with_reason(self):
        self.assertNotIn("Will Jennings", self.ids)
        exclusions = [e for e in self.graph.exclusions if e["artist"]["name"] == "Will Jennings"]
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0]["reason"], "work-level credit")
        self.assertTrue(exclusions[0]["work_id"])
        self.assertEqual(len(self.graph.exclusions), 8)

    def test_executive_release_unknown_and_spoofed_roles_excluded(self):
        record = deepcopy(next(r for r in self.records if r["id"] == GET_BACK))
        artist = {"id": "00000000-0000-4000-8000-000000000001", "name": "Synthetic excluded artist", "type": "Person"}
        producer = {"target-type": "artist", "type": "producer", "type-id": "5c0ceac3-feb4-41f0-868d-dc06f6e27fc0", "artist": artist, "attributes": ["executive"]}
        release = {**producer, "attributes": [], "level": "release"}
        unknown = {**producer, "attributes": [], "type-id": "unknown", "type": "primary artist"}
        record["relations"] += [producer, release, unknown]
        graph = build_graph([record])
        self.assertNotIn(artist["id"], graph.artists)
        self.assertEqual({e["reason"] for e in graph.exclusions if e["artist"]["id"] == artist["id"]},
                         {"excluded executive attribute", "release-level credit", "relationship type outside allowlist"})

    def test_each_allowlisted_relationship_id_is_eligible(self):
        template = deepcopy(next(r for r in self.records if r["id"] == GUITAR))
        for type_id, role in load_rules()["eligible_relationships"].items():
            record = deepcopy(template)
            record["relations"] = [{"target-type": "artist", "type-id": type_id, "type": role,
                                    "artist": self.graph.artists[self.ids["Nathan East"]], "attributes": []}]
            graph = build_graph([record])
            self.assertEqual(len(graph.evidence(BEATLES, self.ids["Nathan East"])), 1, role)

    def test_empty_unknown_and_seed_exclusion(self):
        self.assertEqual(recommend(self.graph, []), [])
        with self.assertRaisesRegex(ValueError, "Unknown seed"):
            recommend(self.graph, ["not-an-artist-id"])
        with self.assertRaisesRegex(ValueError, "Unknown method"):
            recommend(self.graph, [BEATLES], "pagerank")
        self.assertNotIn("The Beatles", self.by_name())

    def test_deterministic_results_under_input_permutation(self):
        records = deepcopy(self.records[::-1])
        for r in records:
            r["relations"].reverse()
        self.assertEqual(recommend(build_graph(records), [BEATLES]), recommend(self.graph, [BEATLES]))
        rows = recommend(self.graph, [BEATLES])
        self.assertEqual(rows, sorted(rows, key=lambda r: (-r["score"], r["artist"]["name"].casefold(), r["artist"]["id"])))

    def test_ties_use_artist_id_after_name(self):
        records = deepcopy(self.records)
        for r in records:
            for relation in r["relations"]:
                if relation["target-type"] == "artist" and relation["artist"]["name"] in {"Ken Scott", "Glyn Johns"}:
                    relation["artist"]["name"] = "Same Name"
        tied = [r for r in recommend(build_graph(records), [BEATLES]) if r["artist"]["name"] == "Same Name"]
        self.assertEqual([r["artist"]["id"] for r in tied], sorted(r["artist"]["id"] for r in tied))

    def test_conflicting_recording_metadata_rejected(self):
        duplicate = deepcopy(self.records[0])
        duplicate["title"] = "Conflicting title"
        with self.assertRaisesRegex(ValueError, "Conflicting metadata"):
            build_graph(self.records + [duplicate])

    def test_demo_json_cli(self):
        result = subprocess.run([sys.executable, "-m", "src.recommend", "--format", "json"], cwd=ROOT, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stats"]["edges"], 96)
        self.assertEqual(len(payload["recommendations"]), 19)
        self.assertTrue(all(r["explanations"] for r in payload["recommendations"]))

    def test_frozen_snapshot_provenance_and_checksums(self):
        for source in self.manifest["sources"]:
            data = (ROOT / "data" / "fixture" / source["snapshot_file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), source["sha256"])
            self.assertEqual(json.loads(data)["id"], source["recording_id"])
            self.assertIn(source["recording_id"], source["query"])
            self.assertTrue(source["retrieved_at"])

    def test_fixture_and_ranking_do_not_use_network(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            records, _ = load_fixture()
            self.assertEqual(len(recommend(build_graph(records), [BEATLES])), 19)


class FavoritesTests(unittest.TestCase):
    def test_observed_tabular_format_preserves_all_columns(self):
        columns = ["Song — Subtitle", "", "3:14", "Artist A & Artist B", "Album", "Pop", "2", "5"]
        line = "\t".join(columns)
        result = parse_favorites(line)
        row = result["tracks"][0]
        self.assertEqual(row["source_columns"], columns)
        self.assertEqual(row["original_line"], line)
        self.assertEqual(row["song_text"], columns[0])
        self.assertEqual(row["artist_text"], columns[3])
        self.assertEqual(row["album_text"], "Album")
        self.assertEqual(result["needs_review"], [])

    def test_malformed_tabular_rows_require_review(self):
        invalid = ["Song\tArtist", "Song\t\t3:99\tArtist\tAlbum\tPop\t0\t1",
                   "Song\t\t3:14\t\tAlbum\tPop\t0\t1"]
        result = parse_favorites("\n".join(invalid))
        self.assertEqual(result["tracks"], [])
        self.assertEqual([r["original_line"] for r in result["needs_review"]], invalid)

    def test_original_text_and_duplicates_preserved(self):
        line = "  Artist — Song (live)  "
        result = parse_favorites(line + "\n\n" + line)
        self.assertEqual([r["line_number"] for r in result["tracks"]], [1, 3])
        self.assertTrue(all(r["original_line"] == line for r in result["tracks"]))
        self.assertEqual(result["tracks"][0]["song_text"], "Song (live)")

    def test_ambiguous_or_missing_fields_require_review(self):
        lines = ["Artist - Song", "Artist — Song — Version", " — Song", "Artist — ", "Song only"]
        result = parse_favorites("\n".join(lines))
        self.assertEqual(result["tracks"], [])
        self.assertEqual([r["original_line"] for r in result["needs_review"]], lines)


if __name__ == "__main__":
    unittest.main()
