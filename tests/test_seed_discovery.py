"""Per-source scheduling, shared route attribution, and coverage-aware stopping."""

from collections import Counter
from urllib.parse import parse_qs, urlparse
import unittest

import test_quick_recommend as quick
from test_quick_recommend import favorite, record
from test_fetch_musicbrainz import Response, identifier


class SeedDiscoveryTests(unittest.TestCase):
    setUp = quick.CollectionTests.setUp
    collection = quick.CollectionTests.collection

    def transport(self, shared=False):
        def fetch(request, timeout):
            parsed = urlparse(request.full_url)
            endpoint = parsed.path.removeprefix("/ws/2/")
            params = parse_qs(parsed.query)
            if endpoint.startswith("recording/"):
                n = int(endpoint.split("/")[-1].split("-")[-1])
                return Response(record(n, n-99, 10 if shared else n-90))
            if endpoint.startswith("artist/"):
                return Response({"id": endpoint.split("/")[-1], "relations": []})
            if endpoint == "recording":
                aid = int(params["artist"][0].split("-")[-1])
                rows = ([record(200+n, 20+n, 10) for n in range(3)] if shared and aid == 10 else
                        [record(200+aid, 20+aid, aid)] if aid >= 10 else [])
                return Response({"recordings": rows, "recording-count": len(rows), "recording-offset": 0})
            raise AssertionError(endpoint)
        return fetch

    def tracks(self):
        return [favorite(n=100+n, act=1+n, line=1+n, recording_mbid=identifier(100+n)) for n in range(3)]

    def test_three_sources_receive_attempts_before_the_next_round(self):
        collector = self.collection(self.transport(), self.tracks(), limit=3)
        collector.run()
        events = [e for e in collector.client.events if "sponsor_source_group" in e]
        sponsors = [e["sponsor_source_group"] for e in events]
        self.assertEqual(len(set(sponsors[:3])), 3)
        self.assertEqual(sponsors[:3], sponsors[3:6])
        self.assertEqual(collector.state["stop_reason"], "target_reached")
        self.assertEqual(collector.report()["selection_summary"]["represented_source_groups"], 3)

    def test_shared_contributor_is_fetched_once_and_retains_all_connections(self):
        collector = self.collection(self.transport(shared=True), self.tracks(), limit=3)
        collector.run()
        events = [e for e in collector.client.events if "sponsor_source_group" in e]
        self.assertEqual(Counter(e["operation"] for e in events), {"contributor_lookup": 1, "artist_browse": 1})
        self.assertTrue(all(len(e["beneficiary_source_groups"]) == 3 for e in events))
        rows = collector.report()["recommendations"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(len(row["contributions"]) == 3 for row in rows))
        self.assertEqual(len({row["primary_seed_song"]["source_group_id"] for row in rows}), 3)

    def test_single_source_cannot_claim_coverage_target(self):
        collector = self.collection(quick.QuickTransport(), limit=2)
        collector.run()
        result = collector.report()
        self.assertEqual(result["selection_summary"]["returned"], 2)
        self.assertEqual(result["selection_summary"]["source_coverage_shortfall"], 1)
        self.assertEqual(collector.state["stop_reason"], "routes_exhausted")


if __name__ == "__main__":
    unittest.main()
