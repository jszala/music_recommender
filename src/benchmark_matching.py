"""Freeze a weighted sample before fresh matching-only runs; never re-sample batches."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import time

from .build_graph import ROOT
from .fetch_musicbrainz import utc_now
from .library_job import atomic_json
from .match_recordings import load_input
from .quick_recommend import recommend_from_likes, sample_likes
from .seed_matching import POLICY


def benchmark_matching(input_path, *, contact, output, sample_size=100, random_seed=42,
                       _runner=recommend_from_likes):
    tracks, metadata = load_input(Path(input_path))
    sampled, sampling = sample_likes(tracks, random_seed=random_seed, seed_count=sample_size)
    if len(sampled) < sample_size:
        raise ValueError("Input has too few distinct artist groups for the fixed sample")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"format_version": 1, "policy": POLICY, "input_sha256": metadata["input_sha256"],
                "random_seed": random_seed, "sample_size": sample_size, "batch_size": 8,
                "frozen_at": utc_now(), "sampling": sampling, "sampled_rows": sampled}
    atomic_json(output / "sample_manifest.json", manifest)
    results, batches = [], []
    for start in range(0, len(sampled), 8):
        batch = sampled[start:start + 8]
        began = time.monotonic()
        result = _runner(input_path, random_seed=random_seed, seed_count=8, contact=contact,
            output_directory=output / f"batch_{start // 8 + 1:03d}",
            _sampled_seeds=batch, _matching_only=True)
        elapsed = time.monotonic() - began
        batches.append({"batch": start // 8 + 1, "elapsed_seconds": elapsed,
                        "requests": result["requests"]["attempts"], "summary": result["matching_summary"],
                        "stop_reason": result["stop_reason"]})
        for sample, outcome in zip(batch, result["matching_outcomes"]):
            row = {"source_row": sample["source_row"], **outcome}
            if row["status"] == "accepted":
                import json
                record = json.loads((Path(result["output_directory"]) / "recordings" / f"{row['recording_id']}.json").read_bytes())
                row["chosen_title"] = record["title"]
                row["chosen_artist_credit"] = record["artist-credit"]
                row["chosen_disambiguation"] = record.get("disambiguation", "")
            results.append(row)
        atomic_json(output / "progress.json", {"completed_rows": results, "batches": batches})
        print(f"Matching batch {start // 8 + 1}: {result['matching_summary']['accepted_sampled_rows']}/{len(batch)} accepted; {elapsed:.2f}s", flush=True)
    counts = dict(Counter(r["status"] for r in results))
    accepted = counts.get("accepted", 0)
    summary = {"format_version": 1, "policy": POLICY, "sampled_rows": len(sampled),
               "accepted_rows": accepted, "distinct_accepted_recordings": len({r["recording_id"] for r in results if r["status"] == "accepted"}),
               "match_rate": accepted / len(sampled), "target_match_rate": 0.9,
               "target_met": accepted / len(sampled) >= 0.9, "outcomes": counts,
               "batches": batches, "rows": results, "fresh_api_data": True,
               "inspection": "Automated identity diagnostics attached; source inspection and independent human audit must be reported separately."}
    atomic_json(output / "summary.json", summary)
    with (output / "identities.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_lines", "input_artist", "input_title", "status", "recording_id", "chosen_title", "chosen_artists", "version_notice"])
        writer.writeheader()
        for row in results:
            writer.writerow({"source_lines": row["source_lines"], "input_artist": row["source_row"]["artist_text"],
                "input_title": row["source_row"]["song_text"], "status": row["status"], "recording_id": row.get("recording_id"),
                "chosen_title": row.get("chosen_title"), "chosen_artists": "; ".join(c.get("name", c["artist"]["name"]) for c in row.get("chosen_artist_credit", []) if isinstance(c, dict)),
                "version_notice": row.get("representative_version_notice")})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/private/favorites.json")
    parser.add_argument("--contact-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()
    try:
        result = benchmark_matching(args.input, contact=args.contact_file.read_text().strip(), output=args.output,
                                    sample_size=args.sample_size, random_seed=args.random_seed)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Accepted {result['accepted_rows']}/{result['sampled_rows']} ({result['match_rate']:.1%}); target met: {result['target_met']}")


if __name__ == "__main__":
    main()
