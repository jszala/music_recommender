"""Bounded song discovery through engineering and songwriting, without real HTTP."""

from dataclasses import replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from src.build_graph import load_dataset
from src.collect_song_graph import CollectionRules, balanced_frontier, collect_song_graph
from src.song_policy import build_registry, registry_for, submitted_artists
from src.fetch_musicbrainz import Limits, MusicBrainzClient, digest, json_bytes
from test_fetch_musicbrainz import FakeClock, Response, identifier
from test_match_recordings import ARTIST, ENGINEER, ENGINEERING, R1, R2, WORK, WRITER, recording


class SongTransport:
    def __init__(self, mode):
        self.mode, self.offsets = mode, []

    def __call__(self, request, timeout):
        parsed = urlparse(request.full_url)
        endpoint = parsed.path.removeprefix("/ws/2/")
        params = parse_qs(parsed.query)
        if endpoint.startswith("artist/"):
            aid = endpoint.split("/")[1]
            relation = ({"target-type": "recording", "type-id": ENGINEERING,
                         "recording": {"id": R2}} if self.mode == "engineer" else
                        {"target-type": "work", "type-id": WRITER, "work": {"id": WORK}})
            return Response({"id": aid, "relations": [relation]})
        if endpoint == "recording":
            offset = int(params["offset"][0])
            self.offsets.append(offset)
            return Response({"recording-count": 2, "recording-offset": offset,
                             "recordings": [{"id": R1 if offset == 0 else R2}]})
        if endpoint.startswith("work/"):
            return Response({"id": WORK, "relations": [{"target-type": "recording", "recording": {"id": R2}}]})
        candidate = recording(R2)
        candidate["artist-credit"] = [{"artist": {"id": identifier(150), "name": "Unfamiliar act"}}]
        return Response(candidate)


class SongCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = FakeClock()

    def prepare(self, mode):
        matched = self.root / "matched"
        matched.mkdir()
        seed = recording()
        if mode == "engineer":
            seed["artist-credit"] = [{"artist": ARTIST}]
            seed["relations"] = [{"target-type": "artist", "artist": ENGINEER,
                                  "type-id": ENGINEERING, "type": "engineer"}]
            # MBID order makes this engineer the selected contributor.
            seed["relations"][0]["artist"] = ENGINEER | {"id": identifier(1)}
        else:
            seed["relations"] = [{"target-type": "work", "type": "performance", "work": {
                "id": WORK, "relations": [{"target-type": "artist", "type-id": WRITER,
                                             "type": "writer", "artist": ENGINEER | {"id": identifier(1)}}]}}]
        raw = json_bytes(seed)
        (matched / "seed.json").write_bytes(raw)
        source = {"recording_id": R1, "snapshot_file": "seed.json", "sha256": digest(raw)}
        (matched / "manifest.json").write_bytes(json_bytes({"format_version": 1, "sources": [source], "input_sha256": "input"}))
        registry = build_registry([seed], [R1], names=submitted_artists([{"artist_text": ARTIST["name"]}]), input_sha256="input")
        (matched / "profile.json").write_bytes(json_bytes({"format_version": 1, "input_sha256": "input", "artist_registry": registry,
                                                           "favorites": [{"recording_id": R1, "source_sha256": digest(raw)}]}))
        return matched

    def run_graph(self, matched, transport, name, *, offline=False, limits=None):
        with MusicBrainzClient(self.root / "cache", limits or Limits(), contact="test@project.invalid",
                              offline=offline, opener=transport, clock=self.clock.time,
                              sleep=self.clock.sleep) as client:
            return collect_song_graph(client, matched, matched / "profile.json", self.root / name,
                                      CollectionRules(contributors=1, browse_page_size=1))

    def test_engineering_only_discovery_paginates_and_freezes_training_provenance(self):
        matched = self.prepare("engineer")
        transport = SongTransport("engineer")
        manifest = self.run_graph(matched, transport, "graph")
        self.assertEqual(transport.offsets, [0, 1])
        self.assertEqual(manifest["candidate_collection_training_recording_ids"], [R1])
        self.assertEqual(manifest["stats"], {"favorite_recordings": 1, "candidate_recordings": 1})
        source = next(s for s in manifest["sources"] if s["recording_id"] == R2)
        self.assertIn("artist recording relationship", source["origins"][0]["routes"])
        records, _ = load_dataset(self.root / "graph")
        self.assertEqual({r["id"] for r in records}, {R1, R2})

    def test_songwriter_discovery_uses_work_recording_relationships(self):
        matched = self.prepare("writer")
        manifest = self.run_graph(matched, SongTransport("writer"), "graph")
        source = next(s for s in manifest["sources"] if s["recording_id"] == R2)
        self.assertIn(f"songwriting work {WORK}", source["origins"][0]["routes"])
        self.assertEqual(manifest["selections"][0]["selected_work_ids"], [WORK])

    def test_offline_replay_reproduces_snapshot_sources_and_fingerprint(self):
        matched = self.prepare("engineer")
        first = self.run_graph(matched, SongTransport("engineer"), "graph")
        with patch.object(socket, "socket", side_effect=AssertionError("Network forbidden")):
            replay = self.run_graph(matched, lambda *a, **kw: self.fail("Network forbidden"), "replay", offline=True)
        self.assertEqual(first["sample_id"], replay["sample_id"])
        self.assertEqual(first["sources"], replay["sources"])
        self.assertEqual(replay["network_attempts"], 0)

    def test_budget_failure_preserves_training_and_partial_manifest(self):
        matched = self.prepare("engineer")
        manifest = self.run_graph(matched, SongTransport("engineer"), "graph", limits=replace(Limits(), max_requests=1))
        self.assertEqual(manifest["collection_status"], "partial")
        self.assertTrue(manifest["failures"])
        self.assertEqual(manifest["network_attempts"], 1)
        self.assertTrue((self.root / "graph/profile.json").exists())

    def test_unknown_training_id_is_rejected_before_creating_output(self):
        matched = self.prepare("engineer")
        with MusicBrainzClient(self.root / "cache", Limits(), offline=True) as client:
            with self.assertRaisesRegex(ValueError, "subset"):
                collect_song_graph(client, matched, matched / "profile.json", self.root / "graph",
                                   CollectionRules(), [identifier(999)])
        self.assertFalse((self.root / "graph").exists())

    def test_frontier_balances_acts_even_when_one_has_many_favorites(self):
        primary1, primary2 = identifier(1001), identifier(1002)
        first_ids = {identifier(2000 + n) for n in range(20)}
        last_id = identifier(3000)
        records = {rid: {"artist-credit": [{"artist": {"id": primary1}}]} for rid in first_ids}
        records[last_id] = {"artist-credit": [{"artist": {"id": primary2}}]}
        frontier = {identifier(10): {"recording_ids": first_ids}, identifier(11): {"recording_ids": {last_id}},
                    primary1: {"recording_ids": first_ids}, primary2: {"recording_ids": {last_id}}}
        self.assertEqual(balanced_frontier(frontier, records, first_ids | {last_id})[:2], [identifier(10), identifier(11)])

    def test_old_profile_without_full_input_registry_cannot_collect_silently(self):
        matched = self.prepare("engineer")
        profile = json.loads((matched / "profile.json").read_bytes())
        profile.pop("artist_registry")
        (matched / "profile.json").write_bytes(json_bytes(profile))
        with self.assertRaisesRegex(ValueError, "supply --input"):
            self.run_graph(matched, SongTransport("engineer"), "graph")
        self.assertFalse((self.root / "graph").exists())

    def test_rejected_recording_is_replaced_and_sources_remain_replayable(self):
        matched = self.prepare("engineer")
        forbidden, admitted = identifier(113), identifier(114)
        calls = []
        def transport(request, timeout):
            endpoint = urlparse(request.full_url).path.removeprefix("/ws/2/")
            calls.append(endpoint)
            if endpoint.startswith("artist/"):
                return Response({"id": endpoint.split("/")[1], "relations": [
                    {"target-type": "recording", "type-id": ENGINEERING, "recording": {"id": rid}}
                    for rid in (forbidden, admitted)]})
            if endpoint == "recording":
                return Response({"recording-count": 0, "recording-offset": 0, "recordings": []})
            rid = endpoint.split("/")[1]
            rec = recording(rid)
            if rid == admitted:
                rec["artist-credit"] = [{"artist": {"id": identifier(150), "name": "New act"}}]
            return Response(rec)
        with MusicBrainzClient(self.root / "cache", Limits(), contact="test@project.invalid", opener=transport,
                              clock=self.clock.time, sleep=self.clock.sleep) as client:
            manifest = collect_song_graph(client, matched, matched / "profile.json", self.root / "graph",
                                          CollectionRules(contributors=1, recordings_per_contributor=1))
        self.assertEqual(manifest["selections"][0]["selected_recording_ids"], [admitted])
        excluded = manifest["selections"][0]["excluded_recordings"][0]
        self.assertEqual(excluded["recording_id"], forbidden)
        self.assertTrue(excluded["source"]["response_sha256"])
        self.assertEqual(calls[-2:], [f"recording/{forbidden}", f"recording/{admitted}"])

    def test_familiar_solo_browse_credit_does_not_spend_detail_lookup(self):
        matched = self.prepare("engineer")
        calls = []
        def transport(request, timeout):
            endpoint = urlparse(request.full_url).path.removeprefix("/ws/2/")
            calls.append(endpoint)
            if endpoint.startswith("artist/"):
                return Response({"id": endpoint.split("/")[1], "relations": []})
            return Response({"recording-count": 1, "recording-offset": 0, "recordings": [recording(R2)]})
        manifest = self.run_graph(matched, transport, "graph")
        self.assertNotIn(f"recording/{R2}", calls)
        self.assertEqual(manifest["selections"][0]["excluded_recordings"][0]["stage"], "browse")

    def test_explicit_training_subset_does_not_inherit_full_input_exclusions(self):
        matched = self.prepare("engineer")
        profile_path = matched / "profile.json"
        profile = json.loads(profile_path.read_bytes())
        profile["artist_registry"]["submitted_names"].append({"name": "Held out act", "normalized_name": "held out act", "source_lines": [9]})
        profile_path.write_bytes(json_bytes(profile))
        with MusicBrainzClient(self.root / "cache", Limits(), contact="test@project.invalid", opener=SongTransport("engineer"),
                              clock=self.clock.time, sleep=self.clock.sleep) as client:
            collect_song_graph(client, matched, profile_path, self.root / "graph", CollectionRules(contributors=1), [R1])
        result = json.loads((self.root / "graph/profile.json").read_bytes())["artist_registry"]
        self.assertEqual(result["scope"], "training_recordings")
        self.assertNotIn("held out act", {r["normalized_name"] for r in result["submitted_names"]})
        collected_profile = json.loads((self.root / "graph/profile.json").read_bytes())
        records, _ = load_dataset(self.root / "graph")
        self.assertEqual(registry_for(records, [R1], profile=collected_profile), result)


if __name__ == "__main__":
    unittest.main()
