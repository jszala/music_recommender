# Fresh recommendation prototype: runtime and coverage

The original measurements below precede the D-026 representative-version change. The
[matching audit](seed_matching_failures.md) records the original failures and the
subsequent user-directed change. Earlier run exports are preserved unchanged.

Measured on 2026-10-08 with the supplied parsed favorites JSON and fresh public
MusicBrainz responses. These are runtime and coverage observations, not recording
identity precision or recommendation-quality measurements.

## Setup

The input contains 1,316 rows, 1,315 distinct artist/title/album/duration entries,
and 425 normalized credited-artist groups. One duplicate row is retained through
its source-line provenance. The sampling tiers contain 322 weight-1 groups,
63 weight-2 groups, and 40 weight-3 groups. Only sampled, confidently matched songs
contribute preference evidence; all 425 submitted artist names supply exclusions.

Four runs executed sequentially with random seeds 1 and 2 and sample sizes 8 and
10. Each run used a new response store, up to 35 HTTP attempts, a 55-second total
budget, a 50-second collection deadline, up to 100 admitted candidates, and a
requested list of 15 songs. Apple checking was not invoked. The original cancelled
full-library job and its saved evidence were not changed or restarted.

```bash
python3 -B -m src.benchmark_recommendations --random-seeds 1 2 --seed-counts 8 10 --contact-file data/private/musicbrainz_contact.txt --output data/private/quick_benchmark_2026-10-08
```

Exact summaries and individual evidence are preserved privately in
`data/private/quick_benchmark_2026-10-08/`. Each `run_NNN` directory contains its
ordered `recommendations.json`, readable `SONG_REVIEW.md`, matching outcomes,
request audit, input snapshot, and frozen recording/credit evidence.

## Results

The experiment runner measures the complete function call, including scoring,
exporting, and returning. `engine_elapsed_seconds` separately records the engine's
last pre-return measurement. CSV runtimes use the complete call measurement.

| Run | Random seed | Sampled artists | Accepted recordings | Candidates admitted | Recommendations / 15 | Complete runtime | HTTP attempts |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 8 | 2 | 39 | 6 | 38.15 s | 35 |
| 2 | 2 | 8 | 3 | 22 | 4 | 41.05 s | 35 |
| 3 | 1 | 10 | 4 | 5 | 3 | 38.55 s | 35 |
| 4 | 2 | 10 | 3 | 46 | 4 | 38.78 s | 35 |

**All four runs met the under-60-second target.** Minimum/median/maximum runtimes
were 38.15 / 38.67 / 41.05 seconds. The four calls together took 156.53 seconds and
charged 140 HTTP attempts. The budget applies to each run, not the entire batch.
Every run stopped because its request budget was exhausted; none reached 15 songs.
Shortfalls were 9, 11, 12, and 11 respectively.

Requests by operation show where the time and budget went:

| Run | Seed searches | Seed details | Contributor relationships | Artist browse pages | Work browse pages | Candidate details |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 8 | 4 | 7 | 7 | 6 | 3 |
| 2 | 8 | 3 | 8 | 8 | 3 | 5 |
| 3 | 10 | 5 | 6 | 5 | 4 | 5 |
| 4 | 10 | 4 | 7 | 6 | 4 | 4 |

Browse responses supplied usable credits directly; candidate collection did not
require an individual detail lookup for every admitted song. Run 1 spent 12.45
seconds matching and 25.57 seconds discovering candidates; its request audit records
28.30 seconds waiting for request spacing and 8.38 seconds in transport. Final
scoring took 0.008 seconds. These timing categories overlap: matching and discovery
already include pacing and transport, and collection total also includes worker
startup/cleanup. They must not all be added together.

Conservative matching skipped ambiguous and unsuccessful seeds without replacements.
Runs 3 and 4 each recorded one HTTP 503 seed-search failure, charged it, and made
no automatic retry. Unexplored contributor routes were 7, 2, 12, and 13 respectively.
Browse pages can leave later results unexplored; the saved page totals and routes
describe partial coverage. Selection retained full-input familiar-act exclusions,
zero repeated observed musicians in every list, and the familiar-collaboration
allowance. Repeated explanatory contributors were allowed with reduced selection
contributions, as specified in D-025.

Lists from different random seeds had zero recording-ID overlap in this sample.
With the same random seed, the 8-artist and 10-artist lists had Jaccard overlaps
2/7 (0.286) and 2/6 (0.333). These comparisons change the sample size and available
discovery budget; they are not repeatability or listening-quality estimates.

After final safeguards disabled automatic redirects and required fallback for
missing nested work-credit fields, a further fresh run verified the final code:

```bash
python3 -B -m src.benchmark_recommendations --random-seeds 1 --seed-counts 8 --contact-file data/private/musicbrainz_contact.txt --output data/private/quick_final_verification_2026-10-08
```

This run took **38.07 seconds**, charged 35 attempts, accepted two seeds, admitted
39 candidates, and returned six songs with a nine-song shortfall. It stopped at
the request budget. Its evidence and readable list are in
`data/private/quick_final_verification_2026-10-08/run_001/`. Across all five measured
calls, runtimes were 38.07–41.05 seconds and lists contained 3–6 songs.

## Verification and interpretation

`python3 -B -m unittest discover -s tests` passed **181 offline tests** in 14.94
seconds. The added tests cover artist weights and deduplication, reproducible
sampling, ambiguous/capped searches, supplied recording IDs, full-input exclusions,
batched recording and nested work credits, missing-credit fallback, within-run
deduplication, large contributor frontiers, the 100-candidate cap, repeated-contributor
penalties, performer uniqueness, and compatibility with strict historical selection.
They also verify charged attempts before transport, shared pacing between runs,
provider backoff without retry, exhausted budgets, empty results, and separate Apple
checking that preserves the original list and ordering.

Real cancellable-worker tests use a transport that sleeps for ten seconds and
ignores its timeout. The supervisor terminates it at the collection deadline,
exports a valid empty result if matching stalled, and preserves a completed seed
snapshot if discovery stalled. No live Apple requests are part of these tests or
benchmarks.

The measured runtime target is achieved for these runs, while the desired 15-song
list remains unmet. Increasing seed count did not reliably increase list size in
this small sample: searches and matching leave fewer requests for discovery.
This implementation makes the scope and stopping reasons inspectable; it does
not establish recommendation usefulness, complete credit coverage, or robust
performance across other networks, seeds, libraries, or provider conditions.
Independent identity auditing and listening review remain pending. Saved evidence
supports audit and tests; it is never reused to accelerate the next live run.

## D-026 representative-version verification

One further fresh run with random seed 1 and eight sampled artists used the
user-directed representative-version choice. It accepted two seeds, admitted 29
candidates, and returned three recommendations in **40.51 seconds**, charging
35 HTTP attempts and stopping at the request budget. Outputs are preserved in
`data/private/quick_representative_versions_2026-10-08/`.

Kevin Morby's previously ambiguous seed was accepted after choosing one version.
The Style Council seed proceeded to one detail lookup but failed the remaining
exact album check. The Replacements and Addison Rae & Arca retained their album
failures, and the Talk Talk query still returned zero results. Dean Blunt and
PinkPantheress searches failed operationally in this fresh run, so the unchanged
accepted-seed count cannot be interpreted as no effect from the policy change.
Version choice does not normalize title/album wording, create missing credits, or
remove provider failures. No recommendation-quality improvement is claimed.
The complete offline suite after this change passed **184 tests** in 14.98 seconds.
