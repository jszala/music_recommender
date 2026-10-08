# Handover: different favorite-song seeds and a ten-track list

Date: 2026-10-08
Status: next experiment requested; no new live runs performed for this handover
Repository: `/home/jan/Projects/music_recommender`

## User request and priorities

The user clarified: **a seed is a favorite song that starts discovery, and the
next test must use different favorite songs.** The previous follow-up reused the
first saved pool, which did not meet that expectation. Do not repeat that approach
as the main experiment.

The new recommendation-list goal is **ten tracks**, with genuinely different
recommendations. This supersedes the earlier up-to-fifteen live target and the
five-track follow-up target for the next experiment. The existing public five-song
example is historical and illustrative; it does not meet the new list-size goal.

Keep the current model fixed while testing different seed songs. The project is
an explainable local portfolio MVP for an Amazon Music Data Scientist interview.
Favor a small, reviewable experiment over infrastructure or a broad model rewrite.

## Current state and evidence to preserve

The checkout contains substantial uncommitted implementation, including untracked
modules, tests, public snapshots, and CI. Inspect `git status --short`; preserve
the working tree and private evidence. Git HEAD alone does not contain the MVP.
Do not reset, clean, overwrite old runs, or resume the cancelled full-library job.

| Evidence | Location | Actual result |
|---|---|---|
| Matching audit | `data/private/mvp_matching_2026-10-08/` | 73/100 accepted; 18 HTTP 503 failures; nine no-compatible outcomes |
| Fresh runs, sampling integers 3/4/5 | `data/private/mvp_recommendations_2026-10-08/run_001` through `run_003` | Eight sampled favorites per run; 5/3/3 recommendations; three assigned source groups each; approximately 38 seconds and 35 attempts each |
| Frozen role-weight comparison | `data/private/mvp_method_comparison_2026-10-08/` | Equal/current weights selected identical lists on the three live pools |
| Original listener panel | Same comparison directory, `ratings.csv` and `listening_results.json` | Eight distinct recordings; all reported familiar and enjoyable; save intention uncollected |
| Same-pool follow-up | `data/private/mvp_novelty_followup_2026-10-08/` | Eight exact recording IDs excluded; 4/5 requested results; no new seeds or requests; all four ratings remain pending |
| Structural follow-up diagnosis | Same follow-up directory, `novelty_diagnostics.json` | Three of four results repeat an earlier primary artist; the fourth repeats a known composition |
| Human identity inspection preparation | `data/private/mvp_identity_review_2026-10-08/` | Ten accepted identities and nine unresolved cases prepared; human judgments pending |

The original listener feedback was a bulk user statement, without verified
blinding. It establishes neither broad preference quality nor discovery novelty.
Do not extend those ratings to any later songs.

Last complete check: **215 offline tests passed in 19.069 seconds** in a clean
copy of tracked and pending public files with no private directory. Both public
methods returned five songs across three groups; repeated CLI JSON was identical.
CI is configured, but a remote CI run has not been claimed.

Read [MVP results](mvp_results.md), [matching audit](mvp_matching_audit.md),
[the historical matching/diversity handoff](fast_matching_and_seed_diversity_plan.md),
and [decisions](../DECISIONS.md) for context.

## Why the previous list was similar

It reranked the first saved pool with the same matched favorites and credit
connections. Removing exact recording IDs left neighboring tracks by the same
artists and other performances of already-recommended compositions eligible.
That was an offline follow-up, not a fresh seeding experiment.

In the first live run, four of eight sampled favorites matched, and three supplied
selected recommendations. There were 82 admitted candidates, but collection still
had five unexplored contributor routes when the request budget stopped it.
Discovery starts from a limited credit neighborhood; many recordings can therefore
come from a small set of acts. Balancing source songs does not guarantee new acts
across recommendation lists.

A read-only inspection found 28 eligible positive candidates in that first pool
without previously reviewed primary-artist or observed-work overlap. This count
does not establish a feasible ten-song selection or unfamiliarity to the listener.
The available candidate pool and the exclusion policy both matter.

Candidate snapshots in that follow-up lacked release metadata. The user noticed
album repetition, but it cannot be verified from those snapshots. Do not invent
album identities or equate titles with compositions.

## What “current model” means

Keep these fixed for the primary experiment:

- Role weights: musician 1, songwriter 1, producer 1, staff 0.25.
- Shared-role scoring, the `x/(1+x)` transform, artist averaging, and `n/(n+5)`
  saturation with `k=5`.
- Full-input familiar-artist exclusions, favorite-ID exclusions, observed performer
  uniqueness, and at most one familiar collaboration.
- Contributor reuse multiplier `1/(1+previous appearances)`.
- Deterministic greedy source assignment, the current three-group minimum target,
  maximum two assignments per source group, and known-work uniqueness within a list.
- Representative matching, bounded fallbacks, per-source discovery request rounds,
  and existing transport/runtime protections.

Change the selected seed songs and request `limit=10`. Sampling ten favorites is
a permitted experiment parameter, not a weight change. Record that the earlier
runs sampled eight, so comparisons with them are operational observations rather
than a controlled causal estimate of seeding improvement.

**Ten selected tracks require at least five productive source groups under the
two-per-group cap.** Five accepted matches alone are insufficient: each needs
feasible candidates, and performer/composition conflicts can reduce capacity.
The configured three-group target remains unchanged; ten tracks necessarily
imply at least five assigned groups. Do not silently raise the per-source cap,
merge independent runs into a purported single list, or weaken constraints to
fill ten positions.

## Files and callable interfaces

| File | Use |
|---|---|
| `src/quick_recommend.py` | `sample_likes`, `recommend_from_likes`, discovery, supervision, and exports |
| `src/match_recordings.py` | `load_input`; read the full private input without filtering its artist registry |
| `src/seed_matching.py` | Title/main-artist normalization and representative identity checks |
| `src/benchmark_recommendations.py` | Sequential fresh runs, `--limit`, `--seed-counts`, and summaries |
| `src/recommend_songs.py` | Existing scorer and selector; accepts `excluded_ids` for separately declared diagnostics |
| `src/source_songs.py` | Source grouping and raw relationship-based work IDs |
| `src/compare_methods.py` | Existing panel export and rating validation; currently hardcodes five-song selections |
| `src/demo.py` | Frozen illustrative public demo; not a source of private experimental seeds |

Private favorites: `data/private/favorites.json`.
Private provider contact: `data/private/musicbrainz_contact.txt`.
Read contact only to execute an authorized live call; never print or publish it.
Keep seed manifests, private song lists, responses, ratings, and input hashes
under ignored `data/private/`. Public reports should summarize findings.

`config/song_collection_limits.json` belongs to an older collection workflow;
its 120-request settings are not the fast prototype's limits. The next primary
runs retain **35 charged attempts, at most 20 for matching, a 55-second engine
budget, and a measured complete-call target below 60 seconds**.

## Proposed bounded experiment

1. Establish the checkout's test baseline and inspect prior `sampled_seeds` in all
   three preserved live reports. Each entry contains `source_row`; use normalized
   main artist and base song title for seed identity. A different row number,
   remaster label, or sampling integer alone does not prove a different seed song.

2. Before live calls, declare three new cohorts of ten favorite songs, each with
   ten requested recommendations. Use the existing weighted sampler: artist weights
   1/2/3 for 1/2–10/>10 distinct liked songs, one song per sampled artist group.
   Select cohorts independently of credits, provider outcomes, or recommendations.

3. A reproducible cohort-selection rule: preview sampling integers 6 through 35
   in ascending order, using `seed_count=10`; retain the first three cohorts whose
   normalized seed-song identities have zero overlap with prior sampled songs and
   already retained new cohorts. Prefer disjoint favorite-artist groups too; state
   any artist reuse explicitly. Select using input metadata only. If three suitable
   cohorts cannot be found within that bound, report the shortfall rather than
   search indefinitely. Do not replace individual difficult songs after outcomes.

4. Freeze the full-input hash, ordered source rows, normalized identities, sampling
   integers, seed count, role/selection configuration, requested length ten, prior
   recommendation reference sets, and stopping rules in a new private protocol
   before the first provider request. Verify the input has not changed. Use the
   same full favorites input for eligibility, even if only ten songs seed discovery.

5. Run those cohorts sequentially with fresh responses and new output directories.
   Keep all failed matches and short lists. Do not refill failed seed slots,
   increase budgets, or retain only attractive runs. Verify each exported ordered
   sample agrees with its frozen cohort. Existing CLI calls reproduce a preview
   when the input, sampling integer, and count are identical.

6. Compare each selected list with the union of all three original live lists and
   the four-song follow-up. Report exact recording overlap, observed composition
   overlap, primary-artist overlap, and album overlap only where metadata supports
   it. Also compare the three new lists with each other. Keep unknown composition
   and release identities visible.

7. Prepare an actual ten-song rating sheet for each delivered ten-song list, with
   familiarity and enjoyment blank. Prior feedback must not be copied into it.
   For a small first listening review, declare the first two new runs before
   seeing results and review the union of their selected tracks, at most twenty
   distinct recordings. Hide scores and explanations until ratings are recorded;
   save intention stays optional.

The existing comparison/follow-up exporter truncates selections to five. Do not
use it unchanged to claim a ten-track review. If adapting it, make the requested
length explicit, bind the panel to the actual ten-track exports, retain legacy
defaults for old callers, and test that all declared selected tracks are included.
Do not introduce another role-weight comparison just to create a panel.

### Existing command for one declared cohort

Replace the placeholders with the actual frozen sampling integer and a new
private output directory. These flags exist today; there is no current
`--seed-manifest` CLI flag.

```bash
python3 -B -m src.quick_recommend \
  --input data/private/favorites.json \
  --random-seed FROZEN_INTEGER \
  --seed-count 10 \
  --limit 10 \
  --max-requests 35 \
  --runtime-limit-seconds 55 \
  --contact-file data/private/musicbrainz_contact.txt \
  --output data/private/NEW_EXPERIMENT/run_001
```

The benchmark runner supports the same request/length limits and explicit lists
of sampling integers and seed counts. It does not freeze a preflight seed protocol
or test seed-history overlap for you; prepare those separately. Do not assume
changing `--random-seed` guarantees every sampled song changes.

## Success criteria and honest failure handling

- Seed-song cohorts actually differ from prior experiments and each other, as
  demonstrated by the frozen input identities, not merely different integers.
- Deliver a ten-track list with supported credit paths and all existing constraints
  intact. Report the returned/requested denominator for every run.
- For the requested structural difference, target zero overlap with earlier
  selected recordings, known compositions, and primary artists. Report each
  dimension separately. Different recording IDs alone do not establish success.
- Actual unfamiliarity remains a listener judgment. Record counts of unfamiliar,
  enjoyable, and unfamiliar-and-enjoyable songs with reviewed/pending denominators.
  New artist IDs do not establish that the listener has never heard them.
- Report sampled rows, accepted rows, distinct accepted recordings, additional-credit
  seeds, productive/represented source groups, candidate coverage, requests by stage,
  complete runtime, stopping reasons, and list/coverage shortfalls separately.
- Preserve all three declared runs and their outcomes. No new seeding result is
  currently known; do not describe the ten-track goal as achieved.

If ten tracks or structural difference cannot be achieved within the declared
cohorts, explain where capacity was lost: matching/provider failures, missing
credits, unexplored routes, repeated compositions, source caps, or performer
conflicts. Propose the smallest concrete next adjustment with evidence. Do not
turn this into an indefinite search for successful examples.

The primary comparison keeps current eligibility fixed. A separate opt-in
history filter can exclude previously reviewed primary artists and known works,
but that is a **selection-policy experiment**, not evidence that different seed
songs alone solved novelty. Preserve and report the unfiltered results first.
This task does not authorize silently replacing the model with such a policy.

Keep score tuning, adaptive pauses, assignment repair, a database import, paid
hosting, and the cancelled library crawl deferred. Runtime and source diversity
are not evidence of listening usefulness.

## Checks and final handback

Run focused checks for any sampling, selection, or panel-export changes, including
duplicate/version seed identities, full-input eligibility preservation, exact
ten-track panel membership, and truthful shortfalls. Then run the offline suite:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B -m src.demo
git diff --check
```

For live calls, use the environment's normal network/approval mechanism when
required. Do not ask again about ordinary implementation or experiment choices
already covered by this request. Preserve private input/contact separation.

Hand back links to the private seed protocol, every new readable list, the summary,
and new blank ratings; publish only aggregate findings. State precisely which
favorite-song cohorts changed, whether any list reached ten, how its artists and
compositions differ, what remains familiar to the listener, and what the evidence
does not establish. Update current reports without rewriting historical outcomes.
