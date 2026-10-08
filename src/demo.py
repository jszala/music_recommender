"""Reproduce an illustrative public example offline with the live engine's scorer."""

import argparse
import json
from pathlib import Path

from .build_graph import ROOT, load_dataset
from .library_job import read_json
from .recommend_songs import CATEGORIES, load_weights, recommendation_report, write_song_review
from .song_policy import build_registry


DEFAULT_DEMO = ROOT / "data/demo"


def demo_report(*, method="weighted", dataset=DEFAULT_DEMO, limit=5):
    if method not in {"equal", "weighted"}:
        raise ValueError("Unknown demonstration method")
    records, manifest = load_dataset(Path(dataset))
    favorites = read_json(Path(dataset) / "example.json")["favorite_recording_ids"]
    configuration = load_weights()
    weights = {c: 1.0 for c in CATEGORIES} if method == "equal" else configuration["role_weights"]
    registry = build_registry(records, favorites)
    report = recommendation_report(records, favorites, registry=registry, weights=weights,
        saturation_k=configuration["saturation_k"], limit=limit, contributor_policy="penalized",
        seed_balancing=True, deduplicate_works=True)
    return report | {"kind": "illustrative_offline_demo", "method": method, "fresh_api_data": False,
                     "favorite_recording_ids": favorites, "dataset_sample_id": manifest["sample_id"],
                     "role_weights": weights, "saturation_k": configuration["saturation_k"],
                     "interpretation": "Hand-selected public example demonstrating behavior; not a recommendation-quality evaluation."}


def render_demo(report):
    summary = report["selection_summary"]
    lines = ["Music-credit recommendations — illustrative offline example",
             f"Method: {report['method']}; {summary['returned']}/{summary['requested']} songs; "
             f"{summary['represented_source_groups']} source groups; no network requests.",
             "This example demonstrates the method; listening usefulness remains unmeasured.", ""]
    for row in report["recommendations"]:
        recording = row["recording"]
        names = ", ".join(c.get("name", c["artist"]["name"]) for c in recording["artist_credit"] if isinstance(c, dict))
        lines += [f"{row['selection_rank']}. {names} — {recording['title']}",
                  f"   Source song: {', '.join(row['primary_seed_song']['titles'])}",
                  f"   Base affinity {row['score']:.6f}; selection score {row['selection_score']:.6f}"]
        for connection in row["contributions"]:
            for credit in connection["contributors"]:
                lines.append(f"   {connection['favorite_recording_title']} → {credit['contributor']['name']} "
                             f"({'/'.join(credit['favorite_roles'])} → {'/'.join(credit['candidate_roles'])})")
                lines.append(f"   {connection['favorite_source_url']}")
                lines.append(f"   https://musicbrainz.org/artist/{credit['contributor']['id']}")
        lines += [f"   {recording['source_url']}", ""]
    lines += ["Weights are provisional. Known-work uniqueness covers observed IDs only.",
              "Greedy selection can miss a better combination; see the README for assumptions."]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("equal", "weighted"), default="weighted")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DEMO)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args()
    try:
        result = demo_report(method=args.method, dataset=args.dataset, limit=args.limit)
        if args.review_output:
            write_song_review(args.review_output, result)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else render_demo(result))


if __name__ == "__main__":
    main()
