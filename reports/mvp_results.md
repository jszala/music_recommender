# Bounded recommendation results, 2026-10-08

Latest checkpoint: the [different favorite-song experiment](different_seed_results.md)
returned 4/10, 3/10, and 4/10 recordings from three predeclared new cohorts.
None reached ten; two outputs were long-form recordings, and new listener ratings
remain pending. The historical outcomes below are preserved.

The implementation provides a deterministic public demonstration and fresh, bounded recommendations. The listener reported liking all eight panel songs, but all were already familiar: the panel demonstrates no new-to-listener discovery. Independent human identity precision remains unmeasured. The 90% matching target and 15-song live list target were not achieved.

## Fresh recommendation experiment

Random seeds 3, 4, and 5, eight sampled artist groups, 35 attempts, and the normal 55-second worker budget were fixed before the runs. Each run began with an empty response store. Input hashes and ordered sampled rows agree with the retained earlier runs. Responses and provider failures differ, so this is an operational comparison rather than a controlled quality experiment.

| Run | Accepted / sampled | Additional-credit seeds | Candidates | Songs / 15 | Assigned sources | Largest share | Work exclusions | Complete call | Attempts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1, seed 3 | 4/8 | 3 | 82 | 5 | 3 | 40.0% | 4 | 38.132 s | 35 |
| 2, seed 4 | 4/8 | 0 | 10 | 3 | 3 | 33.3% | 4 | 38.787 s | 35 |
| 3, seed 5 | 7/8 | 5 | 51 | 3 | 3 | 33.3% | 1 | 38.663 s | 35 |

All runs stopped at the request ceiling. Complete runtime includes sampling, worker startup, collection, scoring, exports, and returning. All three calls were below 60 seconds. Limits apply per run.

Aggregate matching was 15/24; seven rows had provider failures and two had no compatible candidate. Matching attempts were 12, 14, and 16, below the 20 ceiling. Discovery used the remaining 23, 21, and 19 attempts. Per-source sponsored attempts sum to these totals. Shared operations record one sponsor and all beneficiaries; connected candidate counts can overlap.

Assignments were 2/2/1, 1/1/1, and 1/1/1. Each song has one supported assignment. All runs met the three-source target and two-per-source cap, with zero repeated observed performers. Familiar collaborations were 0, 1, and 0. Unknown selected work identities were 2, 0, and 1; composition uniqueness covers observed IDs only.

The earlier seed-3 list contained five versions connected to one composition. The new list has one result assigned to that source and four from two others. This demonstrates constraints on observed data, rather than listening improvement. The seed-4 list illustrates why no additional credits must remain separate from useful retrieval: primary-artist proxies can connect to other roles on candidates. One seed-5 matched source had additional credits but no selected result within the budget.

Private evidence is under `data/private/mvp_recommendations_2026-10-08/`: summary CSV/JSON, readable lists, matching outcomes, per-seed coverage, charged requests, and frozen responses. All three saved lists replayed in the final selector with exactly the same recording order.

## Baseline comparison and listening panel

Equal and current role weights used identical frozen pools, artist exclusions, saturation, contributor penalties, source balancing, composition uniqueness, and a top-five limit. **All three selected lists and their order were identical between methods** (recording-ID Jaccard 1.0). There is no observed selection advantage for current weights in this experiment.

The first two predetermined pools supplied eight distinct recordings from the union of both methods' top five lists, shuffled with random seed 42. The panel was prepared with method labels and scores separated from the ratings CSV. On 2026-10-08 the listener supplied a bulk assessment that every song was familiar and enjoyable. This is user-reported feedback; a separately blinded listening session was not verified. The frozen panel manifest and method key were preserved.

| Listener observation | Count / reviewed songs |
|---|---:|
| Enjoyable (`enjoyment=like`) | 8/8 |
| Already familiar (`familiar=yes`) | 8/8 |
| Previously unfamiliar (`familiar=no`) | 0/8 |
| Pending familiarity/enjoyment ratings | 0/8 |

Save intention was not collected at the listener's request; `would_save` remains blank and its summary is uncollected, rather than a negative response. Each method selected all eight panel recordings across the first two runs, so both share these same ratings. Identical method lists mean their reviews cannot distinguish the weighting schemes here.

Enjoyment supports relevance for this listener and panel. It does not demonstrate discovery novelty: a song or artist absent from the submitted favorites may still be familiar to the listener. A follow-up should declare already-heard exclusions before selection and measure unfamiliar-song counts and enjoyment separately, retaining this original result.

The panel is under `data/private/mvp_method_comparison_2026-10-08/`, with completed `ratings.csv`, `listening_results.json`, and a `review_response.json` recording the user statement and collection method. The summary tool retains selected, rated, and pending denominators. Optional save-intention ratings have their own denominator. This is a descriptive single-listener convenience sample, not a holdout study, significance test, or general preference estimate. `comparison.json` retains the initial preparation checkpoint; `listening_results.json` records the completed review.

## Follow-up with explicitly known recordings excluded

The follow-up uses only the first predetermined saved candidate pool (`run_001`, random seed 3), current role weights, and five requested songs. The eight recording IDs reported familiar in the original panel are explicit exclusions. Favorites, base scoring, full-input artist exclusions, contributor penalties, source balancing, and known-work uniqueness are unchanged. A protocol binds the dataset, prior panel, ratings, exclusions, weights, and constraints before selection. There are no new provider requests and no replacement pool when the list is short.

Selection returned **four of five requested songs across three source groups**; assignments are 2/1/1. None of the eight excluded IDs appears. Exact recording exclusions do not establish composition novelty or listener unfamiliarity. All four familiarity/enjoyment ratings remain blank, so discovery usefulness is pending. This adaptive follow-up is reported separately from the original eight-song assessment.

Inspection prompted by the listener's feedback found that **3/4 follow-up recordings repeat a primary artist from the original panel**. The fourth has a different artist but shares a known composition ID with an original suggestion. Thus every result repeats either an observed artist or composition across reviews. The saved follow-up snapshots have no release metadata, so album overlap cannot be verified from them. `novelty_diagnostics.json` records these structural overlaps without inferring listener ratings. Excluding exact recording IDs was too narrow to move beyond neighboring tracks and covers; a stronger cross-review policy requires an explicit choice about artist versus song discovery.

Private artifacts are under `data/private/mvp_novelty_followup_2026-10-08/`: `protocol.json`, `ratings.csv`, `panel_manifest.json`, `method_key.json`, `comparison.json`, and the score/explanation-bearing `CONNECTIONS.md`. Keep explanations closed while collecting new ratings. The public CLI reproduces this workflow with `--known-review` and exactly one declared pool.

## Public reproducibility and quality checks

The public example has 39 unmodified snapshots and three constructed favorites. Both methods return five results across three source groups. Their lists share two recordings (Jaccard 0.25). The example was chosen after examining available paths; this demonstrates weight sensitivity rather than preference improvement.

The four historical fixture snapshots are also distributed. A fresh checkout needs no private files, account, installation, or network for the demo and tests. CI checks both methods and byte-identical repeated JSON output. See [the readable public list](mvp_demo.md) and [public fixture documentation](../data/demo/README.md).

All **211 offline tests passed in 18.875 seconds** in a clean temporary copy of the tracked and pending public files, with `data/private/` absent. Both demo methods ran there, and repeated JSON output was byte-identical. Checks include historical strict matching/selection, standalone Apple compatibility, stalled-worker termination, small/stage budgets, shared-route attribution, source assignment, compositions, and listener-panel binding. `git diff --check` passed. CI configuration is included; a remote CI run has not been claimed. Historical counts remain in their original reports.

After recording the listener's feedback and making save intention optional, **212 offline tests passed in 18.820 seconds** in the current checkout. The added regression verifies completion without save ratings, a separate denominator when only some save ratings exist, and rejection of invalid or incomplete required ratings. The earlier clean-copy check remains the public reproducibility checkpoint.

With the known-recording follow-up implemented, **215 offline tests passed in 19.069 seconds** in a new clean copy of all tracked and pending public files, with no private directory. Both demo methods returned five songs across three groups with network creation forbidden, and repeated CLI JSON was byte-identical. The new follow-up regressions verify protocol-before-selection, unchanged base scores, original-review preservation, deterministic exports, rejection of pending/tampered prior panels, and a visible shortfall when known IDs exhaust the pool. CI includes these tests; no remote CI execution is claimed.

## Remaining limitations

- The fixed matching audit accepted 73/100, including provider failures in the denominator; see [the matching checkpoint](mvp_matching_audit.md).
- Provider failures, bounded pages, literal identity differences, and uneven credits still limit retrieval. A database import is deferred.
- Greedy assignments can block a feasible better combination. Adaptive pauses and assignment repair remain deferred.
- Requested 15-song lists returned 5/3/3. Constraints are preserved; more candidates do not guarantee more picks.
- The eight-song user report shows enjoyment but zero discovery novelty. Broader listener usefulness, exact audio identity, holdout recovery, and multi-user generalization remain unverified.
