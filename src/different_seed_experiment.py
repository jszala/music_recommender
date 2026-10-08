"""Freeze and execute the bounded different-favorite-song experiment, without tuning."""

import argparse
from pathlib import Path
import time

from .build_graph import ROOT
from .compare_methods import prepare_export_review
from .fetch_musicbrainz import digest, utc_now
from .library_job import atomic_json, read_json
from .match_recordings import load_input
from .quick_recommend import recommend_from_likes, sample_likes
from .recommend_songs import load_weights
from .seed_matching import POLICY, main_artist_key, matching_allocation, title_keys


def seed_identity(sample):
    row = sample["source_row"]
    return main_artist_key(row["artist_text"]), title_keys(row["song_text"])["base"]


def select_cohorts(tracks, prior_samples, *, sampler=sample_likes):
    """First three song-disjoint cohorts in integers 6..35; metadata only."""
    used = {seed_identity(s) for s in prior_samples}
    prior_artists = {a for a, _ in used}
    new_artists, cohorts, previews = set(), [], []
    for integer in range(6, 36):
        samples, _ = sampler(tracks, random_seed=integer, seed_count=10)
        identities = [seed_identity(s) for s in samples]
        distinct = set(identities)
        eligible = len(identities) == len(distinct) == 10 and not distinct & used
        retain = eligible and len(cohorts) < 3
        previews.append({"sampling_integer": integer, "retained": retain,
                         "sampled_count": len(samples), "distinct_identity_count": len(distinct),
                         "song_overlap_count": len(distinct & used)})
        if retain:
            artists = {a for a, _ in distinct}
            cohorts.append({"run_id": len(cohorts) + 1, "sampling_integer": integer,
                            "ordered_samples": samples, "ordered_identities": [list(i) for i in identities],
                            "artist_reuse_from_prior": sorted(artists & prior_artists),
                            "artist_reuse_from_new": sorted(artists & new_artists)})
            used.update(distinct)
            new_artists.update(artists)
        if len(cohorts) == 3:
            break
    return cohorts, previews


def implementation_hashes():
    # Bind the executed method, input handling, protocol runner, and fixed settings.
    paths = sorted((ROOT / "src").glob("*.py")) + sorted((ROOT / "config").glob("*.json"))
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}


def prepare(input_path, prior_runs, followup, output):
    input_path, output = Path(input_path), Path(output)
    prior_runs = [Path(p) for p in prior_runs]
    if len(prior_runs) != 3:
        raise ValueError("Declare exactly three preserved original runs")
    tracks, metadata = load_input(input_path)
    prior = [read_json(p / "recommendations.json") for p in prior_runs]
    if any(r["input_sha256"] != metadata["input_sha256"] for r in prior):
        raise ValueError("Favorites changed since prior runs; historical cohort comparison needs review")
    cohorts, previews = select_cohorts(tracks, [s for r in prior for s in r["sampled_seeds"]])
    weights = load_weights()
    configuration = {"seed_count": 10, "limit": 10, "max_requests": 35, "runtime_limit_seconds": 55,
                     "seed_matching_policy": POLICY, "matching_only": False,
                     "selection_policy": "source_balanced_greedy_v1", "min_seed_groups": 3,
                     "max_per_seed": 2, "deduplicate_known_works": True, **matching_allocation(35),
                     "role_weights": weights["role_weights"], "saturation_k": weights["saturation_k"]}
    files = [p / "recommendations.json" for p in prior_runs] + [Path(followup) / "comparison.json"]
    protocol = {"format_version": 1, "created_at": utc_now(), "input_path": str(input_path.resolve()),
                "input_sha256": metadata["input_sha256"], "full_input_rows": metadata["input_rows"],
                "submitted_artist_name_count": len(metadata["submitted_artists"]),
                "configuration": configuration, "implementation_sha256": implementation_hashes(),
                "prior_runs": [str(p.resolve()) for p in prior_runs], "followup": str(Path(followup).resolve()),
                "reference_sha256": {str(p.resolve()): digest(p.read_bytes()) for p in files},
                "cohorts": cohorts, "previews": previews, "declared_runs": len(cohorts),
                "cohort_shortfall": 3 - len(cohorts), "listening_run_ids": [1, 2][:len(cohorts)],
                "sampling_rule": "Existing weighted sampler; first three song-disjoint previews, integers 6..35. No credit or outcome screening.",
                "artist_rule": "Artist disjointness is preferred but not required; reuse is disclosed without changing the first-eligible rule.",
                "stopping_rule": "One fresh sequential call per declared cohort; no replacements, retries, budget increases, or relaxed policies.",
                "structural_target": "Zero previous recording, observed work, and primary-artist overlap, reported separately; no history filter.",
                "interpretation": "Ten sampled favorites differs from historical eight. Provider conditions also differ. No causal or listener-quality claim."}
    output.mkdir(parents=True, exist_ok=False)
    # Frozen full input, including all submitted artist exclusions; no subset input.
    raw = input_path.read_bytes()
    if digest(raw) != metadata["input_sha256"]:
        raise ValueError("Input changed during preparation")
    (output / "favorites.json").write_bytes(raw)
    atomic_json(output / "protocol.json", protocol)
    return protocol


def execute(output, contact_file, *, runner=recommend_from_likes):
    output = Path(output)
    protocol = read_json(output / "protocol.json")
    if implementation_hashes() != protocol["implementation_sha256"]:
        raise ValueError("Implementation changed since protocol freeze")
    for path, expected in protocol["reference_sha256"].items():
        if digest(Path(path).read_bytes()) != expected:
            raise ValueError("Historical reference changed since protocol freeze")
    input_path = output / "favorites.json"
    for path in (input_path, Path(protocol["input_path"])):
        if digest(path.read_bytes()) != protocol["input_sha256"]:
            raise ValueError("Favorites input changed since protocol freeze")
    directories = [output / f"run_{c['run_id']:03d}" for c in protocol["cohorts"]]
    if any(p.exists() for p in directories):
        raise ValueError("A declared run already exists; refusing to rerun or overwrite")
    contact = Path(contact_file).read_text().strip()
    completed = []
    for cohort, directory in zip(protocol["cohorts"], directories):
        config = protocol["configuration"]
        started = time.monotonic()
        result = runner(input_path, random_seed=cohort["sampling_integer"], seed_count=config["seed_count"],
                        limit=config["limit"], max_requests=config["max_requests"],
                        runtime_limit_seconds=config["runtime_limit_seconds"], contact=contact,
                        output_directory=directory)
        elapsed = time.monotonic() - started
        expected_config = config | {"random_seed": cohort["sampling_integer"]}
        if (result["sampled_seeds"] != cohort["ordered_samples"] or
                result["input_sha256"] != protocol["input_sha256"] or result["configuration"] != expected_config):
            raise ValueError("Export disagrees with frozen cohort or configuration; evidence retained")
        completed.append({"run_id": cohort["run_id"], "sampling_integer": cohort["sampling_integer"],
                          "complete_call_seconds": elapsed, "recommendations": len(result["recommendations"]),
                          "requested": config["limit"], "attempts": result["requests"]["attempts"],
                          "stop_reason": result["stop_reason"], "export_sha256": digest((directory / "recommendations.json").read_bytes())})
        atomic_json(output / "progress.json", {"protocol_sha256": digest((output / "protocol.json").read_bytes()), "completed": completed})
        print(f"Run {cohort['run_id']}: {len(result['recommendations'])}/10 tracks; "
              f"{result['requests']['attempts']}/35 attempts; {elapsed:.3f}s; {result['stop_reason']}", flush=True)
    for directory in directories:
        prepare_export_review([directory], directory / "review", requested_limit=10)
    if directories:
        prepare_export_review(directories[:2], output / "listening_review", requested_limit=10)
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, default=ROOT / "data/private/favorites.json")
    parser.add_argument("--prior-runs", type=Path, nargs=3)
    parser.add_argument("--followup", type=Path)
    parser.add_argument("--contact-file", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            if not args.prior_runs or not args.followup:
                raise ValueError("Preparation requires --prior-runs and --followup")
            p = prepare(args.input, args.prior_runs, args.followup, args.output)
            print(f"Frozen {p['declared_runs']}/3 cohorts; integers {[c['sampling_integer'] for c in p['cohorts']]}")
        else:
            if not args.contact_file:
                raise ValueError("Run requires --contact-file")
            execute(args.output, args.contact_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
