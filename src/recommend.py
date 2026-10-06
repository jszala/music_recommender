"""Rank artists and explain scores using the contributions that created them."""

import argparse
from itertools import product
import json
from pathlib import Path

from .build_graph import DEFAULT_FIXTURE, Graph, build_graph, load_fixture


def recommend(graph: Graph, seeds: list[str], method: str = "two-hop") -> list[dict]:
    if method not in {"direct", "two-hop"}:
        raise ValueError(f"Unknown method: {method}")
    seed_ids = set(seeds)
    if missing := seed_ids - graph.artists.keys():
        raise ValueError(f"Unknown seed IDs: {', '.join(sorted(missing))}")
    if not seed_ids:
        return []
    recommendations = []
    for candidate in sorted(graph.artists.keys() - seed_ids):
        contributions = []
        for seed in sorted(seed_ids):
            for edge in graph.evidence(seed, candidate):
                contributions.append({"kind": "direct", "value": 1,
                                      "seed_id": seed, "candidate_id": candidate,
                                      "evidence": edge})
            if method == "direct":
                continue
            pairs = {}
            intermediaries = (graph.adjacency[seed].keys() & graph.adjacency[candidate].keys()) - seed_ids - {candidate}
            for intermediary in sorted(intermediaries):
                for first, second in product(graph.evidence(seed, intermediary),
                                             graph.evidence(intermediary, candidate)):
                    r1, r2 = first["recording"]["id"], second["recording"]["id"]
                    if r1 == r2:
                        continue
                    pair = tuple(sorted((r1, r2)))
                    pairs.setdefault(pair, []).append({
                        "intermediary_id": intermediary,
                        "intermediary_degree": len(graph.adjacency[intermediary]),
                        "first_edge": first, "second_edge": second,
                    })
            for pair, paths in sorted(pairs.items()):
                contributions.append({"kind": "two-hop", "value": 1,
                                      "seed_id": seed, "candidate_id": candidate,
                                      "recording_pair": list(pair), "paths": paths})
        direct = sum(c["value"] for c in contributions if c["kind"] == "direct")
        two_hop = sum(c["value"] for c in contributions if c["kind"] == "two-hop")
        recommendations.append({"artist": graph.artists[candidate], "score": direct + two_hop,
                                "direct_score": direct, "two_hop_score": two_hop,
                                "contributions": contributions})
    return sorted(recommendations,
                  key=lambda row: (-row["score"], row["artist"]["name"].casefold(), row["artist"]["id"]))


def explain_edge(graph: Graph, edge: dict) -> str:
    descriptions = []
    for aid, credits in edge["credits"].items():
        roles = sorted({c["role"] + (f" ({', '.join(c['attributes'])})" if c["attributes"] else "")
                        for c in credits})
        descriptions.append(f"{graph.artists[aid]['name']} [{'; '.join(roles)}]")
    recording = edge["recording"]
    version = f" ({recording['disambiguation']})" if recording["disambiguation"] else ""
    return (f"{' and '.join(descriptions)} both credited on {recording['title']}{version} "
            f"<{recording['source_url']}>")


def explain_contribution(graph: Graph, contribution: dict) -> list[str]:
    if contribution["kind"] == "direct":
        return ["+1: " + explain_edge(graph, contribution["evidence"])]
    paths = contribution["paths"]
    lines = [f"+1 for this recording pair ({len(paths)} valid paths, counted once):"]
    for path in paths:
        intermediary = graph.artists[path["intermediary_id"]]["name"]
        lines.append(f"  via {intermediary} (degree {path['intermediary_degree']}): "
                     + explain_edge(graph, path["first_edge"]) + "; "
                     + explain_edge(graph, path["second_edge"]))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=["direct", "two-hop"], default="two-hop")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--seed", action="append", help="MusicBrainz artist ID; repeat for several seeds")
    args = parser.parse_args()
    try:
        records, manifest = load_fixture(args.fixture)
        graph = build_graph(records)
        seeds = manifest["seed_artist_ids"] if args.seed is None else args.seed
        rows = recommend(graph, seeds, args.method)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    for row in rows:
        row["explanations"] = [line for c in row["contributions"] for line in explain_contribution(graph, c)]
    if args.format == "json":
        print(json.dumps({"method": args.method, "seed_artist_ids": sorted(set(seeds)),
                          "stats": graph.stats(), "exclusions": graph.exclusions,
                          "recommendations": rows}, ensure_ascii=False, indent=2))
        return
    stats = graph.stats()
    print(f"Fixture: {stats['artists']} artists, {stats['recordings']} recordings, "
          f"{stats['edges']} edges, {stats['edge_contributions']} recording-backed edge contributions")
    print("Seeds: " + ", ".join(graph.artists[s]["name"] for s in sorted(set(seeds))))
    print(f"Method: {args.method}. Scores are evidence counts, not probabilities.\n")
    for density in stats["recording_density"]:
        print(f"Recording: {density['title']}: {density['eligible_artists']} eligible artists, {density['edges']} edges")
    print(f"Excluded artist credits: {stats['exclusions']} (details in JSON output)\n")
    for rank, row in enumerate(rows, 1):
        print(f"{rank:2}. {row['artist']['name']}: {row['score']} "
              f"(direct {row['direct_score']} + two-hop {row['two_hop_score']})")
        for line in row["explanations"]:
            print("    " + line)
        if not row["contributions"]:
            print("    No eligible evidence for this method; score 0.")


if __name__ == "__main__":
    main()
