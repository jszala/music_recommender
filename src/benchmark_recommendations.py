"""Compare fresh recommendation runs across sampling seeds and seed counts."""

import argparse
import csv
from itertools import combinations
from pathlib import Path
import statistics
import time

from .fetch_musicbrainz import utc_now
from .library_job import atomic_json
from .quick_recommend import add_run_arguments, recommend_from_likes


def list_overlap(left, right):
    left, right = set(left), set(right)
    return len(left & right) / len(left | right) if left | right else None


def run_experiments(input_path, *, random_seeds, seed_counts=(8, 10), repeats=1,
                    output_directory, contact, limit=15, max_requests=35,
                    runtime_limit_seconds=55, _runner=recommend_from_likes, on_run_complete=None):
    random_seeds, seed_counts = list(random_seeds), list(seed_counts)
    if not random_seeds or any(type(seed) is not int for seed in random_seeds):
        raise ValueError("Provide at least one integer random seed")
    if not seed_counts or any(type(n) is not int or not 1 <= n <= 1000 for n in seed_counts):
        raise ValueError("Provide positive seed counts, at most 1000")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    previous = []
    for count in seed_counts:
        for seed in random_seeds:
            for repeat in range(1, repeats + 1):
                run_id = len(rows) + 1
                started = time.monotonic()
                result = _runner(input_path, random_seed=seed, seed_count=count, limit=limit,
                                 max_requests=max_requests, runtime_limit_seconds=runtime_limit_seconds,
                                 contact=contact, output_directory=directory / f"run_{run_id:03d}")
                elapsed = time.monotonic() - started
                ids = [row["recording"]["id"] for row in result["recommendations"]]
                matching = result["matching_summary"]
                selection = result.get("selection_summary", {})
                row = {"run_id": run_id, "random_seed": seed, "seed_count": count, "repeat": repeat,
                       "elapsed_seconds": elapsed, "engine_elapsed_seconds": result["elapsed_seconds"],
                       "requests": result["requests"]["attempts"],
                       "accepted_seeds": matching["accepted_recordings"],
                       "sampled_rows": matching.get("sampled"),
                       "accepted_sampled_rows": matching.get("accepted_sampled_rows"),
                       "match_rate": matching.get("match_rate"),
                       "distinct_accepted_recordings": matching["accepted_recordings"],
                       "seeds_with_additional_credits": matching.get("seeds_with_additional_credits"),
                       "source_groups_represented": selection.get("represented_source_groups"),
                       "largest_assigned_seed_share": selection.get("largest_assigned_seed_share"),
                       "source_coverage_shortfall": selection.get("source_coverage_shortfall"),
                       "known_work_exclusions": selection.get("known_work_exclusions"),
                       "requests_by_operation": result["requests"].get("by_operation", {}),
                       "per_seed_discovery": result["candidate_coverage"].get("per_seed", []),
                       "candidates": result["candidate_coverage"]["admitted_candidates"],
                       "recommendations": len(ids), "stop_reason": result["stop_reason"],
                       "runtime_target_met": elapsed < 60,
                       "overlap_with_previous": list_overlap(previous, ids) if rows else None,
                       "recommendation_ids": ids, "output_directory": result["output_directory"]}
                rows.append(row)
                previous = ids
                # Preserve finished runs if a later run or user interruption stops the batch.
                atomic_json(directory / "progress.json", {"completed_runs": rows})
                if on_run_complete is not None:
                    on_run_complete(row)
    timings = [row["elapsed_seconds"] for row in rows]
    summary = {"format_version": 1, "kind": "fresh recommendation experiments", "created_at": utc_now(),
               "fresh_api_data": True, "runtime_limit_applies_to": "each run", "runs": rows,
               "runtime_seconds": {"minimum": min(timings), "median": statistics.median(timings),
                                   "maximum": max(timings)},
               "total_http_attempts": sum(row["requests"] for row in rows),
               "all_runs_under_60_seconds": all(row["runtime_target_met"] for row in rows),
               "list_overlaps": [{"left_run": left["run_id"], "right_run": right["run_id"],
                                  "jaccard": list_overlap(left["recommendation_ids"], right["recommendation_ids"])}
                                 for left, right in combinations(rows, 2)],
               "interpretation": "Runtime and coverage diagnostics, not identity precision or listening quality."}
    atomic_json(directory / "summary.json", summary)
    fields = [key for key in rows[0] if key not in {"recommendation_ids", "output_directory", "requests_by_operation", "per_seed_discovery"}]
    with (directory / "summary.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return summary


def print_run(row):
    print(f"Run {row['run_id']}: random seed {row['random_seed']}, {row['seed_count']} sampled artists; "
          f"{row['recommendations']} recommendations, {row['requests']} requests, "
          f"{row['elapsed_seconds']:.2f}s ({row['stop_reason']})", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_arguments(parser)
    parser.add_argument("--random-seeds", type=int, nargs="+", required=True)
    parser.add_argument("--seed-counts", type=int, nargs="+", default=[8, 10])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_experiments(args.input, random_seeds=args.random_seeds, seed_counts=args.seed_counts,
            repeats=args.repeats, output_directory=args.output, contact=args.contact_file.read_text().strip(),
            limit=args.limit, max_requests=args.max_requests, runtime_limit_seconds=args.runtime_limit_seconds,
            on_run_complete=print_run)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Saved {args.output / 'summary.csv'}")


if __name__ == "__main__":
    main()
