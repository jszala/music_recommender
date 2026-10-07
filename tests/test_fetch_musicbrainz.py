"""Synthetic HTTP fixtures test collection policy; none are actual recording credits."""

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from src.build_graph import build_graph, load_dataset, load_rules
from src.fetch_musicbrainz import FetchError, Limits, MusicBrainzClient, collect_sample, load_seeds
from src.recommend import recommend


def identifier(number):
    return f"00000000-0000-4000-8000-{number:012d}"


SEED, PRODUCER, CANDIDATE, OTHER = [identifier(i) for i in range(1, 5)]
FIRST, SECOND, NEW, NEW_OTHER, EXECUTIVE = [identifier(i) for i in range(11, 16)]
PRODUCER_ROLE = "5c0ceac3-feb4-41f0-868d-dc06f6e27fc0"
ARTISTS = {a: {"id": a, "name": name, "type": "Person"} for a, name in
           [(SEED, "Synthetic seed"), (PRODUCER, "Synthetic producer"),
            (CANDIDATE, "Synthetic candidate"), (OTHER, "Synthetic other candidate")]}


class Response:
    status = 200

    def __init__(self, payload):
        self.data = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload

    def read(self, size):
        return self.data[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeClock:
    def __init__(self):
        self.now, self.delays = 100, []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


def recording(rid, primary):
    return {"id": rid, "title": f"Synthetic recording {rid[-2:]}", "disambiguation": "test version",
            "length": 100000, "artist-credit": [{"artist": ARTISTS[primary]}],
            "relations": [{"target-type": "artist", "type": "producer", "type-id": PRODUCER_ROLE,
                           "artist": ARTISTS[PRODUCER], "attributes": []}]}


class SampleTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append(request)
        parsed = urlparse(request.full_url)
        params = parse_qs(parsed.query)
        endpoint = parsed.path.removeprefix("/ws/2/")
        if endpoint == f"artist/{SEED}":
            return Response(ARTISTS[SEED] | {"relations": []})
        if endpoint == f"artist/{PRODUCER}":
            rels = [{"target-type": "recording", "type": "producer", "type-id": PRODUCER_ROLE,
                     "attributes": [], "recording": {"id": rid}} for rid in (FIRST, SECOND, NEW, NEW_OTHER)]
            rels.append({"target-type": "recording", "type": "producer", "type-id": PRODUCER_ROLE,
                         "attributes": ["executive"], "recording": {"id": EXECUTIVE}})
            return Response(ARTISTS[PRODUCER] | {"relations": rels})
        if endpoint == "recording":
            seed_page = params["artist"] == [SEED]
            ids = [FIRST, SECOND] if seed_page else []
            return Response({"recording-count": 9 if seed_page else 0,
                             "recordings": [{"id": i} for i in ids]})
        rid = endpoint.removeprefix("recording/")
        primary = {FIRST: SEED, SECOND: SEED, NEW: CANDIDATE, NEW_OTHER: OTHER}[rid]
        return Response(recording(rid, primary))


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "cache"
        self.clock = FakeClock()

    def client(self, opener, **kwargs):
        return MusicBrainzClient(self.cache, Limits(), contact="test@project.invalid", opener=opener,
                                 clock=self.clock.time, sleep=self.clock.sleep, **kwargs)

    def test_successful_cache_reused_and_offline_never_calls_network(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return Response({"id": FIRST})

        with self.client(opener) as client:
            self.assertEqual(client.get(f"recording/{FIRST}", inc="artist-rels"), {"id": FIRST})
            self.assertEqual(client.get(f"recording/{FIRST}", inc="artist-rels"), {"id": FIRST})
            self.assertEqual(client.network_attempts, 1)
            self.assertEqual(client.events[-1]["mode"], "cache")
        self.assertEqual(len(calls), 1)
        self.assertIn("music-credit-recommender/0.2.0", calls[0].get_header("User-agent"))
        self.assertIn("test@project.invalid", calls[0].get_header("User-agent"))
        with self.client(lambda *a, **k: self.fail("Network forbidden"), offline=True) as client:
            client.get(f"recording/{FIRST}", inc="artist-rels")
            self.assertEqual(client.network_attempts, 0)

    def test_offline_miss_does_not_call_transport(self):
        with self.client(lambda *a, **k: self.fail("Network forbidden"), offline=True) as client:
            with self.assertRaisesRegex(FetchError, "Offline cache miss"):
                client.get(f"recording/{FIRST}")
            self.assertEqual(client.events[-1]["mode"], "offline-miss")

    def test_failed_response_is_cached_until_explicit_retry(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 404, "Not found", {}, BytesIO(b"missing"))

        with self.client(opener) as client:
            with self.assertRaisesRegex(FetchError, "HTTP 404"):
                client.get(f"recording/{FIRST}")
            self.assertEqual(client.network_attempts, 1)
        with self.client(lambda *a, **k: self.fail("Should reuse cached failure")) as client:
            with self.assertRaisesRegex(FetchError, "Cached failure"):
                client.get(f"recording/{FIRST}")
        with self.client(lambda *a, **k: Response({"id": FIRST}), retry_failures=True) as client:
            self.assertEqual(client.get(f"recording/{FIRST}"), {"id": FIRST})

    def test_transient_retry_respects_retry_after_and_records_attempts(self):
        calls = []

        def opener(request, timeout):
            calls.append(self.clock.now)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 503, "Busy", {"Retry-After": "4"}, BytesIO(b"busy"))
            return Response({"id": FIRST})

        with self.client(opener) as client:
            client.get(f"recording/{FIRST}")
            self.assertEqual(client.network_attempts, 2)
            self.assertEqual([a["status"] for a in client.events[-1]["attempts"]], [503, 200])
        self.assertEqual(calls, [100, 104])

    def test_timing_is_persisted_across_clients_and_budget_counts_retries(self):
        with self.client(lambda *a, **k: Response({})) as client:
            client.get(f"recording/{FIRST}")
        calls = []

        def opener(*args, **kwargs):
            calls.append(self.clock.now)
            raise URLError("Synthetic network failure")

        with self.client(opener) as client:
            client.limits = replace(Limits(), max_requests=1)
            with self.assertRaisesRegex(FetchError, "Request budget exhausted"):
                client.get(f"recording/{SECOND}")
            self.assertEqual(client.network_attempts, 1)
            self.assertEqual([e["attempts"][0]["error"] for e in client.events if e["mode"] == "network"], ["URLError"])
        self.assertGreaterEqual(calls[0] - 100, 1)
        envelope = json.loads(next(p for p in self.cache.glob("*.json") if SECOND in p.read_text()).read_text())
        self.assertEqual(envelope["error"], "URLError")

    def test_http_date_retry_after_is_respected_and_long_waits_are_not_retried(self):
        for rid, retry_after, expected_attempts in [(FIRST, "Thu, 01 Jan 1970 00:01:44 GMT", 2),
                                                  (SECOND, "120", 1)]:
            calls = []

            def opener(request, timeout):
                calls.append(self.clock.now)
                if len(calls) == 1:
                    raise HTTPError(request.full_url, 503, "Busy", {"Retry-After": retry_after}, BytesIO(b"busy"))
                return Response({"id": rid})

            with self.client(opener) as client:
                if expected_attempts == 1:
                    with self.assertRaisesRegex(FetchError, "HTTP 503"):
                        client.get(f"recording/{rid}")
                else:
                    client.get(f"recording/{rid}")
                    self.assertEqual(calls[1] - calls[0], 4)
                self.assertEqual(client.network_attempts, expected_attempts)

    def test_invalid_json_and_response_size_are_recorded_failures(self):
        for rid, payload, byte_limit in [(FIRST, b"not JSON", 100), (SECOND, b"x" * 20, 10)]:
            with self.client(lambda *a, payload=payload, **k: Response(payload)) as client:
                client.limits = replace(Limits(), max_response_bytes=byte_limit)
                with self.assertRaises(FetchError):
                    client.get(f"recording/{rid}")
                self.assertTrue(client.events[-1]["error"])

    def test_cache_tampering_is_rejected_without_network(self):
        with self.client(lambda *a, **k: Response({"id": FIRST})) as client:
            client.get(f"recording/{FIRST}")
        path = next(self.cache.glob("*.json"))
        value = json.loads(path.read_text())
        value["response_text"] = "{}"
        path.write_text(json.dumps(value))
        with self.client(lambda *a, **k: self.fail("Network forbidden"), offline=True) as client:
            with self.assertRaisesRegex(FetchError, "Corrupt cache"):
                client.get(f"recording/{FIRST}")

    def test_parallel_collectors_on_same_cache_rejected(self):
        with self.client(lambda *a, **k: Response({})):
            with self.assertRaisesRegex(FetchError, "Another collector"):
                with self.client(lambda *a, **k: Response({})):
                    pass

    def test_contact_and_rate_limits_validated(self):
        for contact in (None, "", "anonymous", "test@example.invalid\nHeader: value"):
            with self.assertRaisesRegex(ValueError, "contact"):
                MusicBrainzClient(self.cache, Limits(), contact=contact)
        for values in ({"min_interval_seconds": 0.9}, {"seed_recordings": 101},
                       {"expansion_depth": 2}, {"retries": 2}, {"max_requests": 0},
                       {"min_interval_seconds": float("nan")}, {"timeout_seconds": float("inf")}):
            with self.assertRaises(ValueError):
                Limits(**values)
        MusicBrainzClient(self.cache, Limits(), offline=True)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = FakeClock()
        self.transport = SampleTransport()
        self.limits = Limits(seed_recordings=2, expansion_recordings=2, intermediaries_per_seed=1)
        self.seeds = [ARTISTS[SEED] | {"verification": {"source_url": f"https://musicbrainz.org/artist/{SEED}"}}]
        self.metadata = {"format_version": 1, "seeds": self.seeds}

    def run_sample(self, directory, offline=False, limits=None, transport=None):
        with MusicBrainzClient(self.root / "cache", limits or self.limits, contact="test@project.invalid",
                              offline=offline, opener=transport or self.transport,
                              clock=self.clock.time, sleep=self.clock.sleep) as client:
            return collect_sample(client, self.seeds, self.metadata, directory, load_rules())

    def test_production_only_intermediary_creates_new_two_hop_paths(self):
        output = self.root / "sample"
        manifest = self.run_sample(output)
        self.assertEqual(manifest["frontiers"][0]["selected_ids"], [PRODUCER])
        expansion = next(s for s in manifest["selections"] if s["stage"] == "expansion")
        self.assertEqual(expansion["browse"]["reported_total"], 0)
        self.assertEqual(expansion["selected_ids"], [NEW, NEW_OTHER])
        self.assertEqual(expansion["excluded_discovery_relationships"][0]["recording_id"], EXECUTIVE)
        self.assertEqual(manifest["stats"]["recordings"], 4)
        self.assertEqual(manifest["coverage"]["seed_only_two_hop_candidates"], 1)
        self.assertEqual(manifest["coverage"]["expanded_two_hop_candidates"], 3)
        self.assertEqual(manifest["coverage"]["new_two_hop_candidate_ids"], [CANDIDATE, OTHER])
        self.assertEqual(manifest["collection_status"], "complete_with_declared_limits")
        records, saved = load_dataset(output)
        graph = build_graph(records, saved["graph_rules"])
        rows = {r["artist"]["id"]: r for r in recommend(graph, [SEED])}
        self.assertEqual((rows[CANDIDATE]["direct_score"], rows[CANDIDATE]["two_hop_score"]), (0, 2))
        self.assertEqual(rows[CANDIDATE]["score"], sum(c["value"] for c in rows[CANDIDATE]["contributions"]))
        recording_calls = [r for r in self.transport.calls if "/recording/" in r.full_url]
        for request in recording_calls:
            self.assertIn("artist-rels", parse_qs(urlparse(request.full_url).query)["inc"][0])
            self.assertIn("work-level-rels", parse_qs(urlparse(request.full_url).query)["inc"][0])

    def test_offline_replay_has_identical_sources_scores_and_sample_id(self):
        online = self.run_sample(self.root / "online")
        with patch.object(socket, "socket", side_effect=AssertionError("Network forbidden")):
            offline = self.run_sample(self.root / "offline", offline=True,
                                      transport=lambda *a, **k: self.fail("Network forbidden"))
        self.assertEqual(online["sample_id"], offline["sample_id"])
        self.assertEqual(online["sources"], offline["sources"])
        self.assertEqual(online["stats"], offline["stats"])
        self.assertEqual(online["coverage"], offline["coverage"])
        self.assertEqual(offline["network_attempts"], 0)
        for method in ("direct", "two-hop"):
            self.assertEqual((self.root / f"online/recommendations_{method}.json").read_bytes(),
                             (self.root / f"offline/recommendations_{method}.json").read_bytes())

    def test_budget_and_offline_misses_save_partial_sample(self):
        for mode in ("budget", "offline"):
            manifest = self.run_sample(self.root / mode, offline=mode == "offline", limits=replace(self.limits, max_requests=1))
            self.assertEqual(manifest["collection_status"], "partial")
            self.assertEqual(manifest["missing_seed_ids"], [SEED])
            self.assertTrue(manifest["failures"])
            self.assertTrue((self.root / mode / "manifest.json").exists())
            self.assertLessEqual(manifest["network_attempts"], 1)

    def test_sample_is_not_overwritten_and_snapshot_hashes_are_checked(self):
        output = self.root / "sample"
        self.run_sample(output)
        with self.assertRaises(FileExistsError):
            self.run_sample(output, offline=True)
        (output / f"recordings/{FIRST}.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            load_dataset(output)

    def test_browse_and_expansion_truncation_are_visible(self):
        manifest = self.run_sample(self.root / "sample", limits=replace(self.limits, expansion_recordings=1))
        seed = next(s for s in manifest["selections"] if s["stage"] == "seed")
        self.assertTrue(seed["browse"]["browse_incomplete"])
        self.assertEqual(seed["browse"]["unfetched_count"], 7)
        expansion = next(s for s in manifest["selections"] if s["stage"] == "expansion")
        self.assertEqual(expansion["selected_ids"], [NEW])
        self.assertEqual(expansion["omitted_ids"], [NEW_OTHER])

    def test_seed_file_requires_verified_distinct_ids(self):
        path = self.root / "seeds.json"
        path.write_text(json.dumps(self.metadata))
        seeds, _ = load_seeds(path)
        self.assertEqual(seeds, self.seeds)
        for seeds in ([], self.seeds * 2, [{"id": SEED, "name": "Unverified"}]):
            path.write_text(json.dumps({"format_version": 1, "seeds": seeds}))
            with self.assertRaises(ValueError):
                load_seeds(path)


if __name__ == "__main__":
    unittest.main()
