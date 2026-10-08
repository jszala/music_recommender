"""Automatically check the eligible candidate pool with Apple's free country-specific lookup."""

import argparse
import json
from pathlib import Path

from .apple_music import AppleClient, collect_availability, country_code, load_apple_rules
from .build_graph import ROOT, load_dataset
from .fetch_musicbrainz import FetchError, digest, save_json
from .recommend_songs import load_weights, profile_favorites, score_song_candidates
from .song_policy import candidate_eligibility, registry_for


def check_recommendation_run(recommendations_path: Path, *, output: Path, country="DE",
                             rules_path=ROOT / "config/apple_lookup_rules.json",
                             cache=ROOT / "data/cache/apple_itunes", offline=False,
                             retry_failures=False, _client_options=None) -> dict:
    """Annotate the selected list, preserving its original membership and order."""
    recommendations_path = Path(recommendations_path)
    raw = recommendations_path.read_bytes()
    run = json.loads(raw)
    if run.get("format_version") != 1 or run.get("kind") != "quick_recommendation_run":
        raise ValueError("Expected an exported quick recommendation run")
    directory = recommendations_path.parent
    records, manifest = load_dataset(directory)
    favorites = profile_favorites(directory / "profile.json", manifest)
    if run.get("input_sha256") != manifest.get("input_sha256") or sorted(run.get("favorite_recording_ids", [])) != favorites:
        raise ValueError("Recommendation run does not match its dataset")
    by_id = {record["id"]: record for record in records}
    candidate_ids = []
    for row in run["recommendations"]:
        recording = row["recording"]
        rid = recording["id"]
        if rid not in by_id or rid in favorites or recording["title"] != by_id[rid]["title"]:
            raise ValueError("Recommendation recording does not match its snapshot")
        candidate_ids.append(rid)
    rules = load_apple_rules(Path(rules_path))
    with AppleClient(Path(cache), rules, offline=offline, retry_failures=retry_failures,
                     **(_client_options or {})) as client:
        availability = collect_availability(client, records, candidate_ids, rules=rules, output=Path(output),
                                            country=country, favorite_ids=favorites)
    index = {row["recording_id"]: row for row in availability["recordings"]}
    annotated = {"format_version": 1, "kind": "separate Apple recommendation check",
                 "source_recommendations_sha256": digest(raw), "country": country_code(country),
                 "original_order_preserved": True, "summary": availability["summary"],
                 "recommendations": [row | {"apple_availability": index[row["recording"]["id"]],
                     "availability_label": "API-indicated streaming match" if index[row["recording"]["id"]]["reason"] == "available"
                     else "No confident Apple match; catalog absence is not established"} for row in run["recommendations"]]}
    save_json(Path(output) / "recommendation_check.json", annotated)
    return annotated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", type=Path)
    source.add_argument("--recommendations", type=Path, help="Check only an exported quick run's selected songs")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--country", default="DE", type=country_code)
    parser.add_argument("--rules", type=Path, default=ROOT / "config/apple_lookup_rules.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache/apple_itunes")
    parser.add_argument("--output", type=Path, required=True, help="New private output directory")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()
    try:
        if args.recommendations:
            report = check_recommendation_run(args.recommendations, output=args.output, country=args.country,
                rules_path=args.rules, cache=args.cache, offline=args.offline, retry_failures=args.retry_failures)
            print(json.dumps(report["summary"], indent=2))
            print(f"Saved {args.output / 'recommendation_check.json'}")
            if {"request_failure", "budget_exhausted"} & report["summary"]["reason_counts"].keys():
                raise SystemExit(2)
            return
        if args.profile is None:
            raise ValueError("--profile is required with --dataset")
        records, manifest = load_dataset(args.dataset)
        favorites = profile_favorites(args.profile, manifest)
        profile = json.loads(args.profile.read_bytes())
        registry = registry_for(records, favorites, profile=profile, input_path=args.input)
        if profile.get("input_sha256") and registry["scope"] != "full_input":
            raise ValueError("Older profile lacks full-input artist exclusions; supply --input")
        by_id = {record["id"]: record for record in records}
        weights = load_weights()
        rows = score_song_candidates(records, favorites, weights=weights["role_weights"], saturation_k=weights["saturation_k"])
        candidates = [row["recording"]["id"] for row in rows if row["score"] > 0
                      and candidate_eligibility(by_id[row["recording"]["id"]], registry)["eligible"]]
        rules = load_apple_rules(args.rules)
        with AppleClient(args.cache, rules, offline=args.offline, retry_failures=args.retry_failures) as client:
            report = collect_availability(client, records, candidates, rules=rules, output=args.output,
                                          country=args.country, favorite_ids=favorites)
    except (OSError, ValueError, KeyError, TypeError, FetchError) as error:
        parser.error(str(error))
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved {args.output / 'availability.json'}")
    failures = {"request_failure", "budget_exhausted"} & report["summary"]["reason_counts"].keys()
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
