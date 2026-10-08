"""Compare fixed credit pools and prepare a score-blinded single-listener review."""

import argparse
import csv
import json
from pathlib import Path
import random

from .build_graph import load_dataset
from .fetch_musicbrainz import digest, json_bytes
from .library_job import atomic_json, read_json
from .recommend_songs import CATEGORIES, load_weights, profile_favorites, recommendation_report, write_song_review
from .song_policy import build_registry


def _dataset_context(dataset):
    dataset = Path(dataset)
    records, manifest = load_dataset(dataset)
    configuration = load_weights()
    if (dataset / "example.json").exists():
        favorites = read_json(dataset / "example.json")["favorite_recording_ids"]
        registry = build_registry(records, favorites)
    else:
        favorites = profile_favorites(dataset / "profile.json", manifest)
        registry = read_json(dataset / "profile.json")["artist_registry"]
        if (dataset / "recommendations.json").exists():
            run = read_json(dataset / "recommendations.json")
            configuration.update(run["configuration"])
    return records, manifest, favorites, registry, configuration


def compare_dataset(dataset: Path, *, excluded_ids=None) -> dict:
    dataset = Path(dataset)
    records, _, favorites, registry, configuration = _dataset_context(dataset)
    methods = {}
    for method in ("equal", "weighted"):
        weights = {c: 1.0 for c in CATEGORIES} if method == "equal" else configuration["role_weights"]
        methods[method] = recommendation_report(records, favorites, registry=registry, weights=weights,
            saturation_k=configuration["saturation_k"], excluded_ids=excluded_ids, limit=5, contributor_policy="penalized",
            seed_balancing=True, min_seed_groups=configuration.get("min_seed_groups", 3),
            max_per_seed=configuration.get("max_per_seed", 2), deduplicate_works=True)
    ids = {method: {r["recording"]["id"] for r in report["recommendations"]} for method, report in methods.items()}
    union = ids["equal"] | ids["weighted"]
    return {"dataset": str(dataset), "manifest_sha256": digest((dataset / "manifest.json").read_bytes()),
            "methods": methods, "excluded_recording_ids": sorted(excluded_ids or ()),
            "recording_id_jaccard": len(ids["equal"] & ids["weighted"]) / len(union) if union else None,
            "interpretation": "Same frozen candidates and selection constraints; output differences do not establish preference improvement."}


def prepare_comparison(datasets, output):
    datasets = [Path(p) for p in datasets]
    if not datasets:
        raise ValueError("Provide at least one frozen dataset")
    comparisons = [compare_dataset(p) for p in datasets]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "comparison.json", {"format_version": 1, "comparisons": comparisons,
        "listening_status": "pending", "panel_uses": "First two declared datasets, union of each method's top five recordings."})
    songs, membership = {}, {}
    for run_number, comparison in enumerate(comparisons[:2], 1):
        for method, report in comparison["methods"].items():
            for row in report["recommendations"]:
                rid = row["recording"]["id"]
                songs[rid] = row["recording"]
                membership.setdefault(rid, []).append({"run": run_number, "method": method, "rank": row["selection_rank"]})
    panel_manifest = _write_panel(output, songs, membership,
        [{k: c[k] for k in ("dataset", "manifest_sha256")} for c in comparisons[:2]])
    return {"datasets": len(comparisons), "panel_size": len(panel_manifest["items"]), "listening_status": "pending"}


def _write_panel(output, songs, membership, datasets, *, metadata=None):
    ordered = sorted(songs)
    random.Random(42).shuffle(ordered)
    panel = [{"item_id": f"item_{index:03d}", "recording_id": rid} for index, rid in enumerate(ordered, 1)]
    # The union is at most 2 datasets * 2 methods * 5 songs, with duplicates rated once.
    if len(panel) > 20:
        raise ValueError("Listening panel unexpectedly exceeds 20 recordings")
    panel_manifest = {"format_version": 1, "items": panel,
                      "datasets": datasets,
                      "rating_schema": {"familiar": ["yes", "no"], "enjoyment": ["like", "neutral", "dislike"], "would_save": ["yes", "no"]},
                      **(metadata or {})}
    atomic_json(output / "panel_manifest.json", panel_manifest)
    atomic_json(output / "method_key.json", {"panel_sha256": digest(json_bytes(panel_manifest)), "membership": membership})
    with (output / "ratings.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["item_id", "artist", "title", "source_url", "familiar", "enjoyment", "would_save"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in panel:
            row = songs[item["recording_id"]]
            writer.writerow({"item_id": item["item_id"], "artist": ", ".join(c.get("name", c["artist"]["name"]) for c in row["artist_credit"] if isinstance(c, dict)),
                             "title": row["title"], "source_url": row["source_url"]})
    (output / "LISTENING_REVIEW.md").write_text(
        f"# Listening review — pending\n\n{len(panel)} distinct recordings were selected before any ratings. "
        "The order is shuffled with random seed 42.\n\n"
        "Open ratings.csv, find each recording in your music player, and fill familiar (yes/no) "
        "and enjoyment (like/neutral/dislike). would_save (yes/no) is optional; leave it blank "
        "when save intention is not being evaluated. Source links identify the recording; "
        "they do not establish streaming availability. Leave unrated rows blank.\n\n"
        "Keep comparison.json, method_key.json, and CONNECTIONS.md closed until you finish: they reveal scores and explanations. "
        "Each song is rated once, including songs shared by both methods.\n\n"
        "After rating, run python3 -B -m src.compare_methods --review DIRECTORY --ratings DIRECTORY/ratings.csv. "
        "The summary reports rated counts and denominators, with pending rows kept visible. "
        "This is a small single-listener convenience sample, not a general preference estimate.\n", encoding="utf-8")
    return panel_manifest


def prepare_export_review(datasets, output, *, requested_limit=10):
    """Review every track in one or two actual exports without reranking them."""
    datasets = [Path(p) for p in datasets]
    if not 1 <= len(datasets) <= 2 or type(requested_limit) is not int or not 1 <= requested_limit <= 10:
        raise ValueError("Provide one or two runs and a requested limit of 1 through 10")
    songs, membership, bindings = {}, {}, []
    for run_number, dataset in enumerate(datasets, 1):
        path = dataset / "recommendations.json"
        run = read_json(path)
        rows = run["recommendations"]
        ids = [row["recording"]["id"] for row in rows]
        summary = run["selection_summary"]
        if (run["configuration"]["limit"] != requested_limit or
                summary["requested"] != requested_limit or summary["returned"] != len(rows) or
                summary["shortfall"] != requested_limit - len(rows) or
                len(rows) > requested_limit or len(set(ids)) != len(ids)):
            raise ValueError("Export length or selection summary disagrees with declared review")
        bindings.append({"dataset": str(dataset.resolve()), "recommendations_sha256": digest(path.read_bytes()),
                         "requested": requested_limit, "returned": len(rows), "ordered_recording_ids": ids})
        for rank, row in enumerate(rows, 1):
            rid = row["recording"]["id"]
            songs[rid] = row["recording"]
            membership.setdefault(rid, []).append({"run": run_number, "method": "current", "rank": rank})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    panel = _write_panel(output, songs, membership, bindings, metadata={
        "kind": "actual exported tracks; no role-weight comparison", "requested_limit": requested_limit})
    (output / "LISTENING_REVIEW.md").write_text(
        f"# Listening review — pending\n\nAll {len(panel['items'])} distinct tracks from the declared exports "
        f"are included. Each run requested {requested_limit}; short lists retain their actual lengths. "
        "Order is shuffled with integer 42; scores and credit explanations are omitted.\n\n"
        "Fill ratings.csv: familiar=yes/no; enjoyment=like/neutral/dislike; would_save=yes/no is optional. "
        "Leave pending rows blank. Keep the run JSON, SONG_REVIEW.md, method_key.json, and explanation "
        "reports closed until ratings are recorded. Prior feedback is not carried over. Viewing earlier "
        "explanations means verified blinding cannot be claimed. Recording links do not establish playback availability.\n\n"
        "Summarize with python3 -B -m src.compare_methods --review DIRECTORY --ratings DIRECTORY/ratings.csv. "
        "This is a descriptive single-listener review.\n", encoding="utf-8")
    return {"panel_size": len(panel["items"]), "listening_status": "pending", "datasets": bindings}


def prepare_followup(dataset, previous_review, output):
    """Select current-weight top five after excluding explicitly familiar recordings."""
    dataset, previous_review, output = Path(dataset), Path(previous_review), Path(output)
    panel, _, rated = _load_ratings(previous_review, previous_review / "ratings.csv")
    if len(rated) != len(panel["items"]):
        raise ValueError("Complete the previous familiarity/enjoyment review before a follow-up")
    excluded = set(panel.get("excluded_recording_ids", [])) | {
        rid for rid, values in rated.items() if values["familiar"] == "yes"}
    if not excluded:
        raise ValueError("Previous review contains no explicitly familiar recordings")
    _, _, favorites, _, configuration = _dataset_context(dataset)
    protocol = {"format_version": 1, "kind": "known_recording_followup",
        "dataset": str(dataset), "manifest_sha256": digest((dataset / "manifest.json").read_bytes()),
        "previous_review": str(previous_review),
        "previous_panel_sha256": digest(json_bytes(panel)),
        "previous_method_key_sha256": digest((previous_review / "method_key.json").read_bytes()),
        "previous_ratings_sha256": digest((previous_review / "ratings.csv").read_bytes()),
        "excluded_recording_ids": sorted(excluded), "favorite_recording_ids": favorites,
        "method": "weighted", "role_weights": configuration["role_weights"],
        "saturation_k": configuration["saturation_k"], "requested": 5,
        "contributor_policy": "penalized", "seed_balancing": True,
        "min_seed_groups": configuration.get("min_seed_groups", 3),
        "max_per_seed": configuration.get("max_per_seed", 2), "deduplicate_works": True,
        "shuffle_seed": 42, "new_provider_requests": 0,
        "interpretation": "Exact known recording exclusions; familiarity remains a listener judgment. Adaptive follow-up, not an independent holdout."}
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "protocol.json", protocol)
    # Persist inputs and the stopping rule before observing selection outcomes.
    comparison = compare_dataset(dataset, excluded_ids=excluded)
    if comparison["manifest_sha256"] != protocol["manifest_sha256"]:
        raise ValueError("Dataset changed after the follow-up protocol was saved")
    report = comparison["methods"]["weighted"]
    songs = {row["recording"]["id"]: row["recording"] for row in report["recommendations"]}
    membership = {row["recording"]["id"]: [{"run": 1, "method": "weighted", "rank": row["selection_rank"]}]
                  for row in report["recommendations"]}
    atomic_json(output / "comparison.json", {"format_version": 1, "comparisons": [comparison],
        "listening_status": "pending", "panel_uses": "Current-weight top five from one declared frozen pool; known recordings excluded."})
    _write_panel(output, songs, membership,
        [{k: comparison[k] for k in ("dataset", "manifest_sha256")}],
        metadata={"kind": "known_recording_followup", "excluded_recording_ids": sorted(excluded),
                  "protocol_sha256": digest(json_bytes(protocol))})
    write_song_review(output / "CONNECTIONS.md", report)
    with (output / "LISTENING_REVIEW.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\nThis follow-up requested five songs and returned {len(songs)}; "
            f"shortfall {5 - len(songs)}. {len(excluded)} explicitly known recording IDs are excluded. "
            "Favorites, weights, and selection constraints are unchanged. No new provider requests were made. "
            "Other versions may still be familiar. Record familiarity honestly; a different recommendation "
            "does not establish discovery novelty. The original review is preserved.\n")
    summary = summarize_ratings(output, output / "ratings.csv")
    return {"datasets": 1, "panel_size": len(songs), "requested": 5, "shortfall": 5 - len(songs),
            "represented_source_groups": report["selection_summary"]["represented_source_groups"],
            "excluded_recordings": len(excluded), "new_provider_requests": 0,
            "listening_status": summary["status"]}


def _rating_summary(selected, rated):
    reviewed = selected & rated.keys()
    save_reviewed = {rid for rid in reviewed if rated[rid].get("would_save")}
    saves = sum(rated[rid]["would_save"] == "yes" for rid in save_reviewed)
    return {"rated": len(reviewed), "pending": len(selected - reviewed),
            "familiar": sum(rated[rid]["familiar"] == "yes" for rid in reviewed),
            "previously_unfamiliar": sum(rated[rid]["familiar"] == "no" for rid in reviewed),
            "liked": sum(rated[rid]["enjoyment"] == "like" for rid in reviewed),
            "would_save_rated": len(save_reviewed),
            "would_save": saves if save_reviewed else None,
            # Only rows with an explicit save rating contribute to this denominator.
            "would_save_fraction_of_rated": saves / len(save_reviewed) if save_reviewed else None}


def _load_ratings(review, ratings):
    review = Path(review)
    panel = read_json(review / "panel_manifest.json")
    key = read_json(review / "method_key.json")
    if key["panel_sha256"] != digest(json_bytes(panel)):
        raise ValueError("Method key belongs to a different review panel")
    expected = {r["item_id"]: r["recording_id"] for r in panel["items"]}
    with Path(ratings).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(expected) or {r["item_id"] for r in rows} != set(expected):
        raise ValueError("Ratings must contain exactly the declared panel item IDs")
    rated = {}
    for row in rows:
        values = {k: (row.get(k) or "").strip().casefold() for k in panel["rating_schema"]}
        if all(not value for value in values.values()):
            continue
        if any(values[k] not in choices for k, choices in panel["rating_schema"].items()
               if k != "would_save" or values[k]):
            raise ValueError(f"Incomplete or invalid rating for {row['item_id']}")
        rated[expected[row["item_id"]]] = values
    return panel, key, rated


def summarize_ratings(review, ratings):
    review = Path(review)
    panel, key, rated = _load_ratings(review, ratings)
    expected = {r["item_id"]: r["recording_id"] for r in panel["items"]}
    methods = {}
    for method in sorted({m["method"] for memberships in key["membership"].values() for m in memberships}):
        selected = {rid for rid, memberships in key["membership"].items() if any(m["method"] == method for m in memberships)}
        methods[method] = {"selected_distinct_recordings": len(selected), **_rating_summary(selected, rated)}
    result = {"format_version": 1, "status": "no_items" if not expected else "complete" if len(rated) == len(expected) else "pending",
              "panel_size": len(expected), **_rating_summary(set(expected.values()), rated), "methods": methods,
              "ratings_sha256": digest(Path(ratings).read_bytes()),
              "interpretation": "Descriptive single-listener review; overlapping methods share ratings. No significance or generalization claim."}
    atomic_json(review / "listening_results.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--known-review", type=Path,
                        help="Completed previous review; prepare one current-weight follow-up excluding familiar recording IDs")
    args = parser.parse_args()
    try:
        if args.review and args.ratings and not args.runs and not args.output and not args.known_review:
            result = summarize_ratings(args.review, args.ratings)
        elif args.runs and args.output and not args.review and not args.ratings:
            if args.known_review:
                if len(args.runs) != 1:
                    raise ValueError("A known-recording follow-up requires exactly one declared frozen dataset")
                result = prepare_followup(args.runs[0], args.known_review, args.output)
            else:
                result = prepare_comparison(args.runs, args.output)
        else:
            raise ValueError("Use --runs with --output, or --review with --ratings")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
