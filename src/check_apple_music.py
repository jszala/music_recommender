"""Automatically check the eligible candidate pool with Apple's free country-specific lookup."""

import argparse
import json
from pathlib import Path

from .apple_music import AppleClient, collect_availability, country_code, load_apple_rules
from .build_graph import ROOT, load_dataset
from .fetch_musicbrainz import FetchError
from .recommend_songs import load_weights, profile_favorites, score_song_candidates
from .song_policy import candidate_eligibility, registry_for


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--country", default="DE", type=country_code)
    parser.add_argument("--rules", type=Path, default=ROOT / "config/apple_lookup_rules.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache/apple_itunes")
    parser.add_argument("--output", type=Path, required=True, help="New private output directory")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()
    try:
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
