"""Compare song methods on declared recording splits, labeling collection limitations."""

import argparse
import json
from pathlib import Path

from .apple_music import country_code, validate_availability
from .build_graph import DEFAULT_FIXTURE, ROOT, load_dataset
from .fetch_musicbrainz import digest
from .recommend_songs import CATEGORIES, load_weights, profile_favorites, score_song_candidates, select_song_list
from .song_policy import build_registry, candidate_eligibility, registry_digest


def equivalence_map(groups: list[list[str]]) -> dict[str, str]:
    parent = {}

    def find(item):
        parent.setdefault(item, item)
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]

    for group in groups:
        if len(set(group)) < 2:
            raise ValueError("Established equivalence groups need two distinct recording IDs")
        for item in group[1:]:
            left, right = find(group[0]), find(item)
            parent[max(left, right)] = min(left, right)
    return {item: find(item) for item in parent}


def evaluate_split(records: list[dict], training_ids: list[str], heldout_ids: list[str], *,
                   weights: dict, saturation_k: float, equivalent_groups: list[list[str]] | None = None,
                   research: bool = False, collection_training_ids: list[str] | None = None,
                   collection_registry: dict | None = None, availability: dict | None = None,
                   country: str = "DE") -> dict:
    training, heldout = set(training_ids), set(heldout_ids)
    if not training or not heldout:
        raise ValueError("A split needs nonempty training and held-out recording sets")
    aliases = equivalence_map(equivalent_groups or [])
    canonical = lambda rid: aliases.get(rid, rid)
    training_groups, targets = {canonical(r) for r in training}, {canonical(r) for r in heldout}
    if training_groups & targets:
        raise ValueError("Training and held-out recordings overlap, including established equivalents")
    if research and (collection_training_ids is None or set(collection_training_ids) != training):
        raise ValueError("Research evaluation requires collection provenance bound to training recordings")
    registry = build_registry(records, sorted(training),
                              input_sha256=collection_registry.get("input_sha256") if collection_registry else None)
    train_artists = {r["id"] for r in registry["submitted_artists"]}
    heldout_artists = {c["artist"]["id"] for r in records if r["id"] in heldout
                       for c in r.get("artist-credit", []) if isinstance(c, dict)}
    if train_artists & heldout_artists:
        raise ValueError("Discovery evaluation requires complete-artist holdouts; primary artists overlap")
    if research and collection_registry != registry:
        raise ValueError("Research evaluation requires artist exclusions derived only from training recordings")
    excluded = {r["id"] for r in records if canonical(r["id"]) in training_groups}
    variants = [("equal", {c: 1.0 for c in CATEGORIES}, saturation_k, "none"),
                ("weighted", weights, saturation_k, "none"), ("weighted_without_saturation", weights, None, "none"),
                ("weighted_contributor_diversity", weights, saturation_k, "contributors")]
    comparisons = []
    available = validate_availability(availability, records, country=country) if availability is not None else None
    for name, role_weights, k, diversity in variants:
        rows = score_song_candidates(records, sorted(training), weights=role_weights,
                               saturation_k=k, excluded_ids=excluded)
        # One ranked item per established identity; different live/remix IDs stay separate unless explicitly grouped.
        seen, unique = set(), []
        for row in rows:
            identity = canonical(row["recording"]["id"])
            if identity not in seen:
                unique.append(row)
                seen.add(identity)
        positive = [r for r in unique if r["score"] > 0]
        selection_rows = unique
        if available is not None:
            representatives = {}
            for row in rows:
                rid = row["recording"]["id"]
                identity = canonical(rid)
                previous = representatives.get(identity)
                if previous is None or (available.get(rid, {}).get("reason") == "available"
                                        and available.get(previous["recording"]["id"], {}).get("reason") != "available"):
                    representatives[identity] = row
            selection_rows = list(representatives.values())
        selected = select_song_list(selection_rows, records, registry, limit=20, diversity=diversity,
                                    availability=availability, country=country)
        final = selected["recommendations"]
        in_graph = targets & {canonical(r["id"]) for r in records}
        by_id = {r["id"]: r for r in records}
        eligible = [r for r in positive if candidate_eligibility(by_id[r["recording"]["id"]], registry)["eligible"]]
        reachable = targets & {canonical(r["recording"]["id"]) for r in eligible}
        available_reachable = (targets & {canonical(r["recording"]["id"]) for r in selection_rows
                              if r["score"] > 0 and available.get(r["recording"]["id"], {}).get("reason") == "available"
                              and candidate_eligibility(by_id[r["recording"]["id"]], registry)["eligible"]}
                               if available is not None else reachable)
        metrics, raw_metrics = {}, {}
        for cutoff in (10, 20):
            hits = targets & {canonical(r["recording"]["id"]) for r in final[:cutoff]}
            metrics[str(cutoff)] = {"hits": len(hits), "overall_denominator": len(targets),
                                   "overall_recall": len(hits) / len(targets),
                                   "reachable_denominator": len(reachable),
                                   "reachable_recall": len(hits) / len(reachable) if reachable else None,
                                   "available_reachable_denominator": len(available_reachable),
                                   "available_reachable_recall": len(hits) / len(available_reachable) if available_reachable else None}
            raw_hits = targets & {canonical(r["recording"]["id"]) for r in positive[:cutoff]}
            raw_metrics[str(cutoff)] = {"hits": len(raw_hits), "overall_recall": len(raw_hits) / len(targets)}
        comparisons.append({"method": name, "saturation_k": k, "role_weights": role_weights,
                            "heldout_distinct_identities": len(targets), "heldout_in_graph": len(in_graph),
                            "heldout_reachable": len(reachable), "positive_candidates": len(positive),
                            "policy_eligible_positive_candidates": len(eligible), "diversity": diversity,
                            "metrics": metrics, "raw_score_metrics": raw_metrics,
                            "selection_summary": selected["selection_summary"],
                            "availability_summary": selected["availability_summary"],
                            "skipped_candidates": selected["skipped_candidates"],
                            "raw_ranking": [{"recording_id": r["recording"]["id"], "score": r["score"]} for r in positive],
                            "ranking": [{"recording_id": r["recording"]["id"], "score": r["score"],
                                         "selection_score": r["selection_score"]} for r in final]})
    return {"status": "exploratory_research" if research else "demonstration_diagnostics",
            "training_recording_ids": sorted(training), "heldout_recording_ids": sorted(heldout),
            "established_equivalent_groups": equivalent_groups or [], "comparisons": comparisons,
            "evaluation_task": "complete_artist_song_discovery", "policy": "D-020",
            "training_artist_registry": registry, "policy_sha256": registry_digest(registry),
            "limitations": ["One-person saved-song recovery does not establish listening usefulness.",
                            "Cross-ID equivalence not explicitly established remains unresolved.",
                            "Collection follows the declared provenance; no final-test tuning is permitted."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--split", type=Path, required=True, help="Version-1 declared recording split")
    parser.add_argument("--weights", type=Path, default=ROOT / "config/song_weights.json")
    parser.add_argument("--research", action="store_true", help="Require collection provenance for training favorites")
    parser.add_argument("--availability", type=Path)
    parser.add_argument("--country", type=country_code, default="DE")
    args = parser.parse_args()
    try:
        records, manifest = load_dataset(args.dataset)
        raw = args.split.read_bytes()
        split = json.loads(raw)
        if split.get("format_version") != 1:
            raise ValueError("Unsupported split format")
        configuration = load_weights(args.weights)
        profile_path = args.dataset / "profile.json"
        collection_profile = json.loads(profile_path.read_bytes()) if profile_path.exists() else {}
        if collection_profile:
            profile_favorites(profile_path, manifest)
        result = evaluate_split(records, split["training_recording_ids"], split["heldout_recording_ids"],
                                weights=configuration["role_weights"], saturation_k=configuration["saturation_k"],
                                equivalent_groups=split.get("established_equivalent_groups", []),
                                research=args.research,
                                collection_training_ids=manifest.get("candidate_collection_training_recording_ids"),
                                collection_registry=collection_profile.get("artist_registry"),
                                availability=json.loads(args.availability.read_bytes()) if args.availability else None,
                                country=args.country)
        result["split_sha256"] = digest(raw)
        result["dataset_sample_id"] = manifest.get("sample_id")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
