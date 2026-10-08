"""Adversarial free Apple responses exercise automatic matching and complete-list filtering."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from src.apple_music import (AppleClient, AppleRules, collect_availability, dataset_fingerprint,
                             match_recording, search_terms, title_identity, validate_availability)
from src.build_graph import ROOT
from src.evaluate_songs import evaluate_split
from src.fetch_musicbrainz import FetchError, digest, json_bytes
from src.recommend_songs import recommendation_report, write_playlist_preparation, write_song_review
from test_fetch_musicbrainz import FakeClock, Response
from test_song_policy import WEIGHTS, artist, relation, song


def example_record(n=101, act=2, connector=4):
    return song(n, [artist(act)], [relation(artist(connector))]) | {
        "length": 180000, "releases": [{"title": "Source Album"}]}


def apple_track(record, **updates):
    return {"wrapperType": "track", "kind": "song", "trackId": 123, "collectionId": 12,
            "artistName": record["artist-credit"][0]["artist"]["name"], "trackName": record["title"],
            "collectionName": "Source Album", "trackTimeMillis": record["length"],
            "trackExplicitness": "notExplicit", "isStreamable": True,
            "trackViewUrl": "https://music.apple.com/de/album/example/12?i=123"} | updates


def availability_report(records, entries):
    rules = asdict(AppleRules())
    return {"format_version": 1, "provider": "apple_itunes_search", "country": "DE",
            "dataset_sha256": dataset_fingerprint(records), "rules": rules,
            "rules_sha256": digest(json_bytes(rules)), "recordings": entries}


class AppleMatchingTests(unittest.TestCase):
    def setUp(self):
        self.record = example_record()
        self.track = apple_track(self.record)
        self.rules = AppleRules()

    def match(self, *tracks):
        return match_recording(self.record, list(tracks), self.rules)

    def test_exact_metadata_match_and_different_album_appearance(self):
        result = self.match(self.track | {"collectionName": "Compilation"})
        self.assertEqual(result["reason"], "available")
        self.assertFalse(result["checks"]["album_context_match"])

    def test_false_missing_and_nonboolean_streaming_flags_are_separate(self):
        self.assertEqual(self.match(self.track | {"isStreamable": False})["reason"], "not_streamable")
        for flag in (None, 1, "true"):
            with self.subTest(flag=flag):
                self.assertEqual(self.match(self.track | {"isStreamable": flag})["reason"], "missing_streaming_flag")
        del self.track["isStreamable"]
        self.assertEqual(self.match(self.track)["reason"], "missing_streaming_flag")

    def test_wrong_artist_title_resource_and_malformed_tracks_fail_closed(self):
        for changes in ({"artistName": "Different Act"}, {"trackName": "Different Song"},
                        {"kind": "music-video"}, {"trackId": True}, {"artistName": None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.match(self.track | changes)["reason"], "no_confident_match")
        self.assertEqual(self.match(None, "bad", {})["reason"], "no_confident_match")

    def test_duration_boundary_missing_and_invalid_values(self):
        self.assertEqual(self.match(self.track | {"trackTimeMillis": 182000})["reason"], "available")
        for duration in (182001, None, True, -1):
            with self.subTest(duration=duration):
                self.assertEqual(self.match(self.track | {"trackTimeMillis": duration})["reason"], "no_confident_match")
        self.record.pop("length")
        self.assertEqual(self.match(self.track)["reason"], "no_confident_match")

    def test_decorated_studio_remasters_are_allowed(self):
        for suffix in (" (2011 Remastered)", " [Remastered 2011]", " - 2011 Remaster", " – Remastered"):
            with self.subTest(suffix=suffix):
                result = self.match(self.track | {"trackName": self.record["title"] + suffix})
                self.assertEqual(result["reason"], "available")
                self.assertTrue(result["checks"]["studio_remaster"])
        self.assertEqual(title_identity("The Remaster Song"), ("the remaster song", False))

    def test_remastered_source_can_match_original_studio_release(self):
        self.record["title"] += " (Remastered)"
        self.assertEqual(self.match(self.track)["reason"], "available")

    def test_remaster_permission_does_not_extend_to_live_or_remix_versions(self):
        for version in ("Live", "Remix"):
            with self.subTest(version=version):
                self.record["title"] = f"Song 101 ({version})"
                track = self.track | {"trackName": self.record["title"], "collectionName": "Source Album (2011 Remaster)"}
                self.assertEqual(self.match(track)["reason"], "no_confident_match")
                self.record["title"] += " (Remastered)"
                self.assertEqual(self.match(track | {"collectionName": "Source Album"})["reason"], "no_confident_match")

    def test_other_version_distinctions_survive_remaster_normalization(self):
        for marker in ("Live", "Remix", "Radio Edit", "Acoustic", "Instrumental", "Demo", "Mono", "Cover"):
            with self.subTest(marker=marker):
                self.assertEqual(self.match(self.track | {"trackName": self.track["trackName"] + f" ({marker})"})["reason"], "no_confident_match")
                self.assertEqual(self.match(self.track | {"collectionName": f"Source Album ({marker})"})["reason"], "no_confident_match")
        self.record["disambiguation"] = "live"
        self.assertEqual(self.match(self.track)["reason"], "no_confident_match")
        self.assertEqual(self.match(self.track | {"collectionName": "Source Album (Live)"})["reason"], "available")

    def test_conflicting_clean_and_explicit_identities_are_ambiguous(self):
        result = self.match(self.track | {"trackExplicitness": "explicit"},
                            self.track | {"trackId": 124, "trackExplicitness": "cleaned"})
        self.assertEqual(result["reason"], "ambiguous_match")

    def test_duplicate_releases_and_original_album_duration_id_precedence(self):
        original = self.track | {"trackId": 10, "collectionName": "Compilation"}
        album = self.track | {"trackId": 20, "trackTimeMillis": 180100}
        remaster = self.track | {"trackId": 1, "trackName": self.track["trackName"] + " (Remastered)"}
        result = self.match(original, remaster, album, album)
        self.assertEqual(result["match"]["trackId"], 20)
        self.assertEqual(self.match(album, remaster, original)["match"], result["match"])
        self.assertEqual(self.match(self.track | {"trackId": 2}, self.track | {"trackId": 1})["match"]["trackId"], 1)

    def test_unstreamable_original_does_not_hide_streamable_remaster(self):
        result = self.match(self.track | {"isStreamable": False}, self.track | {
            "trackId": 124, "trackName": self.record["title"] + " (Remastered)"})
        self.assertEqual(result["reason"], "available")
        self.assertEqual(result["match"]["trackId"], 124)

    def test_queries_are_distinct_and_bounded_with_literal_special_characters(self):
        self.record["title"] = "Song & Artist? (Remastered)"
        self.assertEqual(len(search_terms(self.record, self.rules)), 1)
        self.record["artist-credit"][0]["joinphrase"] = " & "
        self.record["artist-credit"].append({"artist": artist(3)})
        terms = search_terms(self.record, self.rules)
        self.assertEqual(len(terms), 2)
        self.assertIn("song & artist?", terms[0])

    def test_invalid_rules_and_country_are_rejected(self):
        for changes in ({"search_limit": 0}, {"max_queries_per_candidate": 3},
                        {"min_interval_seconds": 3}, {"duration_tolerance_ms": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                AppleRules(**changes)


class AppleCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = FakeClock()
        self.rules = AppleRules()
        self.records = [example_record(), example_record(102, act=3)]

    def client(self, opener, **kwargs):
        return AppleClient(self.root / "cache", self.rules, opener=opener,
                           clock=self.clock.time, sleep=self.clock.sleep, **kwargs)

    def transport(self, request, timeout):
        params = parse_qs(urlparse(request.full_url).query)
        for key, value in {"country": "DE", "entity": "song", "media": "music", "explicit": "Yes", "limit": "50"}.items():
            self.assertEqual(params[key], [value])
        self.assertNotIn("fmt", params)
        self.assertEqual(urlparse(request.full_url).netloc, "itunes.apple.com")
        record = next(record for record in self.records if record["title"].casefold() in params["term"][0])
        return Response({"resultCount": 1, "results": [apple_track(record)]})

    def collect(self, client, directory):
        return collect_availability(client, self.records, [r["id"] for r in self.records],
                                    rules=self.rules, output=self.root / directory)

    def test_pacing_exact_queries_frozen_responses_and_offline_replay(self):
        with self.client(self.transport) as client:
            live = self.collect(client, "live")
        self.assertEqual(live["summary"]["network_attempts"], 2)
        self.assertTrue(all(delay >= 3.1 - 1e-9 for delay in self.clock.delays))
        self.assertEqual(len(list((self.root / "live/responses").glob("*.json"))), 2)
        with patch.object(socket, "create_connection", side_effect=AssertionError("network disabled")):
            with self.client(lambda *a, **k: self.fail("offline transport called"), offline=True) as client:
                replay = self.collect(client, "replay")
        self.assertEqual(replay["summary"]["network_attempts"], 0)
        self.assertEqual(live["dataset_sha256"], replay["dataset_sha256"])
        for original, cached in zip(live["recordings"], replay["recordings"]):
            self.assertEqual({k: v for k, v in original.items() if k != "queries"},
                             {k: v for k, v in cached.items() if k != "queries"})

    def test_partial_budget_failure_saves_all_candidates(self):
        self.rules = replace(self.rules, max_requests=1)
        with self.client(self.transport) as client:
            report = self.collect(client, "partial")
        self.assertEqual(report["summary"]["reason_counts"], {"available": 1, "budget_exhausted": 1})
        self.assertTrue((self.root / "partial/availability.json").exists())

    def test_slow_request_preparation_cannot_shorten_next_send_interval(self):
        starts = []

        def opener(request, timeout):
            starts.append(self.clock.time())
            return self.transport(request, timeout)

        with self.client(opener) as client:
            original_pace = client._pace

            def delayed_preparation(not_before=0):
                original_pace(not_before)
                if not starts:
                    self.clock.sleep(0.2)

            client._pace = delayed_preparation
            self.collect(client, "slow_preparation")
        self.assertGreaterEqual(starts[1] - starts[0], 3.1 - 1e-9)

    def test_request_failure_and_offline_cache_miss_stay_unknown(self):
        def failing(*args, **kwargs):
            raise OSError("simulated outage")
        with self.client(failing) as client:
            report = self.collect(client, "failed")
        self.assertEqual(report["summary"]["reason_counts"], {"request_failure": 2})
        with self.client(lambda *a, **k: self.fail("offline network"), offline=True) as client:
            replay = self.collect(client, "failed_replay")
        self.assertEqual(replay["summary"]["reason_counts"], report["summary"]["reason_counts"])

    def test_corrupt_cache_and_immutable_outputs_are_rejected(self):
        with self.client(self.transport) as client:
            self.collect(client, "live")
        with self.client(self.transport) as client, self.assertRaises(FileExistsError):
            self.collect(client, "live")
        cache = next((self.root / "cache").glob("*.json"))
        cache.write_text("{}")
        with self.client(lambda *a, **k: self.fail("corrupt cache network"), offline=True) as client:
            report = self.collect(client, "corrupt")
        self.assertIn("request_failure", report["summary"]["reason_counts"])

    def test_search_limit_and_malformed_response_cannot_auto_accept(self):
        self.rules = replace(self.rules, search_limit=1)
        with self.client(self.transport) as client:
            # This response has a qualifying match, but the result set hits the declared limit.
            client.opener = lambda *a, **k: Response({"resultCount": 1, "results": [apple_track(self.records[0])]})
            report = self.collect(client, "truncated")
        self.assertEqual(report["summary"]["reason_counts"], {"search_limit_reached": 2})
        with AppleClient(self.root / "new_cache", self.rules,
                         opener=lambda *a, **k: Response({"resultCount": 4, "results": []}),
                         clock=self.clock.time, sleep=self.clock.sleep) as client:
            report = self.collect(client, "malformed")
        self.assertEqual(report["summary"]["reason_counts"], {"request_failure": 2})

    def test_country_dataset_rules_duplicate_ids_and_false_flags_cannot_be_rebound(self):
        with self.client(self.transport) as client:
            report = self.collect(client, "live")
        for changes in ({"country": "US"}, {"dataset_sha256": "wrong"}, {"rules_sha256": "wrong"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_availability(report | changes, self.records)
        changed = deepcopy(self.records)
        changed[0]["title"] = "Other Song"
        with self.assertRaises(ValueError):
            validate_availability(report, changed)
        altered = deepcopy(report)
        altered["recordings"][0]["match"]["isStreamable"] = False
        with self.assertRaises(ValueError):
            validate_availability(altered, self.records)
        with self.assertRaises(ValueError):
            validate_availability(report | {"recordings": report["recordings"] * 2}, self.records)
        self.assertEqual(dataset_fingerprint(self.records), dataset_fingerprint(list(reversed(self.records)) + [self.records[0]]))

    def test_wrong_country_links_are_skipped_automatically(self):
        with self.client(lambda *a, **k: Response({"resultCount": 1, "results": [apple_track(self.records[0],
                          trackViewUrl="https://music.apple.com/us/album/example/12?i=123")]})) as client:
            report = self.collect(client, "country")
        self.assertEqual(report["recordings"][0]["reason"], "invalid_country_link")


class AppleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.seed = example_record(100, act=1)
        self.first, self.second = example_record(), example_record(102, act=3)
        self.records = [self.seed, self.first, self.second]

    def entry(self, record, streamable=True):
        return {"recording_id": record["id"], "checked_at": "2026-10-07T12:00:00+00:00",
                **match_recording(record, [apple_track(record, isStreamable=streamable)], AppleRules())}

    def test_unavailable_best_song_does_not_consume_connector_and_missing_entries_fail_closed(self):
        availability = availability_report(self.records, [self.entry(self.first, False), self.entry(self.second)])
        result = recommendation_report(self.records, [self.seed["id"]], availability=availability)
        self.assertEqual([row["recording"]["id"] for row in result["recommendations"]], [self.second["id"]])
        self.assertEqual(result["availability_summary"]["excluded"], 1)
        self.assertEqual(result["skipped_candidates"][0]["availability_reason"], "not_streamable")
        availability["recordings"] = []
        result = recommendation_report(self.records, [self.seed["id"]], availability=availability)
        self.assertEqual(result["recommendations"], [])
        self.assertTrue(all(row["availability_reason"] == "not_checked" for row in result["skipped_candidates"]))

    def test_playlist_order_ids_and_source_linked_review(self):
        self.seed["relations"].append(relation(artist(9)))
        self.second["relations"] = [relation(artist(9))]
        availability = availability_report(self.records, [self.entry(self.first), self.entry(self.second)])
        result = recommendation_report(self.records, [self.seed["id"]], availability=availability)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "playlist.json"
            write_playlist_preparation(path, result)
            playlist = json.loads(path.read_text())
            self.assertEqual([track["recording_id"] for track in playlist["tracks"]],
                             [row["recording"]["id"] for row in result["recommendations"]])
            self.assertEqual([track["position"] for track in playlist["tracks"]], [1, 2])
            self.assertTrue(all(track["apple_music_catalog_id"] is None for track in playlist["tracks"]))
            with self.assertRaises(FileExistsError):
                write_playlist_preparation(path, result)
            review = Path(directory) / "REVIEW.md"
            write_song_review(review, result)
            self.assertIn("Listen on Apple Music", review.read_text())
            self.assertIn("Shared contributors: at most one song each", review.read_text())

    def test_evaluation_methods_share_filters_and_report_both_reachability_denominators(self):
        availability = availability_report(self.records, [self.entry(self.first, False), self.entry(self.second)])
        result = evaluate_split(self.records, [self.seed["id"]], [self.second["id"]], weights=WEIGHTS,
                                saturation_k=5, availability=availability)
        self.assertEqual(result["policy"], "D-020")
        for comparison in result["comparisons"]:
            self.assertEqual(comparison["availability_summary"]["eligible_before_filter"], 2)
            self.assertEqual(comparison["availability_summary"]["eligible_after_filter"], 1)
            self.assertEqual(comparison["ranking"][0]["recording_id"], self.second["id"])
            self.assertEqual(comparison["metrics"]["10"]["available_reachable_denominator"], 1)

    def test_evaluation_prefers_available_appearance_of_established_identity(self):
        equivalent = example_record(103)
        records = [self.seed, self.first, equivalent]
        availability = availability_report(records, [self.entry(self.first, False), self.entry(equivalent)])
        result = evaluate_split(records, [self.seed["id"]], [equivalent["id"]], weights=WEIGHTS,
                                saturation_k=5, availability=availability,
                                equivalent_groups=[[self.first["id"], equivalent["id"]]])
        for comparison in result["comparisons"]:
            self.assertEqual(comparison["ranking"][0]["recording_id"], equivalent["id"])
            self.assertEqual(comparison["metrics"]["10"]["hits"], 1)
            self.assertEqual(comparison["metrics"]["10"]["available_reachable_denominator"], 1)

    def test_complete_offline_cli_workflow_and_wrong_country_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            dataset.mkdir()
            sources = []
            for record in self.records:
                raw = json_bytes(record)
                filename = record["id"] + ".json"
                (dataset / filename).write_bytes(raw)
                sources.append({"recording_id": record["id"], "snapshot_file": filename, "sha256": digest(raw)})
            (dataset / "manifest.json").write_bytes(json_bytes({"format_version": 1, "sources": sources}))
            profile = dataset / "profile.json"
            profile.write_bytes(json_bytes({"format_version": 1, "favorites": [{
                "recording_id": self.seed["id"], "source_sha256": sources[0]["sha256"]}]}))
            clock = FakeClock()

            def transport(request, timeout):
                term = parse_qs(urlparse(request.full_url).query)["term"][0]
                record = next(record for record in self.records if record["title"].casefold() in term)
                return Response({"resultCount": 1, "results": [apple_track(record)]})

            with AppleClient(root / "cache", AppleRules(), opener=transport,
                             clock=clock.time, sleep=clock.sleep) as client:
                collect_availability(client, self.records, [self.first["id"], self.second["id"]],
                                     rules=AppleRules(), output=root / "seed_cache")
            common = ["--dataset", str(dataset), "--profile", str(profile)]
            checked = subprocess.run([sys.executable, "-B", "-m", "src.check_apple_music", *common,
                                      "--offline", "--cache", str(root / "cache"), "--output", str(root / "check")],
                                     cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertIn('"network_attempts": 0', checked.stdout)
            run = subprocess.run([sys.executable, "-B", "-m", "src.recommend_songs", *common,
                                  "--availability", str(root / "check/availability.json"), "--format", "json",
                                  "--playlist-output", str(root / "playlist.json"),
                                  "--review-output", str(root / "REVIEW.md")],
                                 cwd=ROOT, capture_output=True, text=True, check=True)
            report = json.loads(run.stdout)
            self.assertEqual(report["selection_summary"]["returned"], 1)
            self.assertEqual(report["selection_summary"]["repeated_explanatory_contributors"], 0)
            self.assertEqual(json.loads((root / "playlist.json").read_text())["tracks"][0]["position"], 1)
            rejected = subprocess.run([sys.executable, "-B", "-m", "src.recommend_songs", *common,
                                       "--availability", str(root / "check/availability.json"), "--country", "US"],
                                      cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("different country", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
