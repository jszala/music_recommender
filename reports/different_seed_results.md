# Different favorite-song experiment, 2026-10-08

Three predeclared fresh cohorts returned **4/10, 3/10, and 4/10 recordings**.
None achieved the ten-song goal. Run 1 also returned a 149.45-minute livestream
and a 120-minute continuous mix, so delivered recording counts do not establish
individual-song suitability. These outputs were preserved without replacements.

## Protocol

Before any requests, preview the existing weighted favorite sampler with integers
6 through 35 in ascending order. Retain the first three ten-song cohorts whose
normalized main-artist/base-title identities overlap neither the three original
cohorts nor an earlier retained new cohort. This selected integers **6, 9, 10**.
All 30 song identities differ; two prior artist groups recur and are disclosed
in private evidence. No cohort was selected using credits or provider outcomes.

Freeze the full-input hash, ordered samples, normalization, implementation hashes,
reference hashes, requested length, weights, policies, and stopping rules. Each
cohort gets one fresh sequential call with 35 charged attempts, at most 20 for
matching, a 55-second engine budget, and a measured complete-call target below
60 seconds. Use the full favorites input for exclusions. Do not replace failed
seeds, increase budgets, relax constraints, or combine runs to fill a list.

Weights, scoring, contributor penalties, three-group target, two-per-source cap,
known-work uniqueness, performer uniqueness, and familiar-collaboration limit
remain fixed. Earlier runs sampled eight favorites; these sample ten and encounter
different provider conditions. This is an operational comparison, not a controlled
estimate of improvement from changing songs.

## Outcomes

| Run / integer | Accepted / sampled | Additional-credit seeds | Admitted candidates | Productive / assigned sources | Delivered / requested | Complete call | Attempts |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 / 6 | 7/10 | 4 | 50 | 3 / 3 | 4/10 | 38.620 s | 35/35 |
| 2 / 9 | 5/10 | 5 | 3 | 2 / 2 | 3/10 | 38.166 s | 35/35 |
| 3 / 10 | 6/10 | 2 | 51 | 3 / 3 | 4/10 | 38.783 s | 35/35 |

Matching accepted 18/30 rows. Eight rows failed with HTTP 503 and four had no
compatible candidate. A further contributor request failed with HTTP 503 in run 3.
All attempts, including failures, remain in the denominator. Total charged attempts
were 105. Matching used 18/18/17 attempts; discovery used 17/17/18.

A productive group has at least one eligible positively connected candidate;
that does not guarantee feasible assignment. Three, two, and three productive
groups give source-cap upper bounds of six, four, and six before other conflicts.
Ten requires at least five. Unexplored contributor routes were 7/21/5 when the
budget stopped collection. More accepted matches alone cannot solve list length.

Runs 1 and 3 also lost candidates to observed-performer conflicts and duplicate
known works. Selector reasons are attribution categories, not independent causal
effects. Run 2 selected all three admitted eligible candidates and missed the
configured three-source target by one group. All runs retained the two-per-source
cap and zero repeated observed performers; each used one allowed familiar
collaboration. A missing credit is not evidence that no credit exists.

## Structural difference and listening

Reference: the union of all three original lists and the four-recording follow-up.
Overlap counts below count new selected recordings, with the delivered denominator.
Primary artist means any structured artist-credit ID, including collaborations.
Composition overlap uses observed work IDs, never title similarity.

| New run | Exact recording overlap | Primary-artist overlap | Observed-work overlap | Unknown selected work identity |
|---|---:|---:|---:|---:|
| 1 | 1/4 | 1/4 | 0/4 | 3/4 |
| 2 | 0/3 | 0/3 | 0/3 | 0/3 |
| 3 | 0/4 | 0/4 | 0/4 | 1/4 |

The three new lists share no recording, credited artist, or observed work IDs with
one another. Missing work identities prevent a complete composition-novelty claim.
Release metadata is missing for 4/4, 1/3, and 4/4 selected recordings; observed
release identities are not assumed to identify albums. Album overlap is unresolved.

The first two runs were declared for listening before collection. Their full union
contains seven recordings, all with blank familiarity/enjoyment ratings: **0/7
reviewed, 7/7 pending**. Save intention remains optional. Every delivered recording
also has a per-run blank review sheet. No five-track truncation or new weight
comparison was used. Previous listener feedback was not copied. New-to-listener
and unfamiliar-and-enjoyable usefulness remain unmeasured. Verified blinding is
not claimed, especially if the reviewer sees the other lists or explanations.

## Reproduction and checks

`src.different_seed_experiment` separates `prepare` from `run`. Preparation accepts
the full input, exactly three original directories, a follow-up directory, and a
new output directory. Running verifies frozen input, implementation, and reference
hashes before collection and checks exported ordered samples/configuration after
each call. Existing run directories prevent accidental reruns or overwrite.

`prepare_export_review` in `src.compare_methods` reads actual selected exports
without reranking, binds their hashes and ordered membership, includes every track,
retains shortfall denominators, and creates blank shuffled ratings. Existing
five-track comparison/follow-up defaults remain available for historical callers.

Private evidence: `data/private/different_seeds_ten_tracks_2026-10-08/` contains
`protocol.json`, all three run exports/responses, `progress.json`, `summary.json`,
`ALL_LISTS.md`, `EVIDENCE.md`, per-run reviews, and `listening_review/ratings.csv`.
`build_report.py` rebuilds the consolidated readable report using saved evidence.
No private songs or contact information are published in this aggregate report.

Baseline: 215 offline tests passed in 19.038 seconds. Seven added regressions
cover duplicate/remaster identities, first-eligible selection, bounded cohort
shortfalls, full-input preservation and change rejection, all-ten-track membership,
two-run unions, blank ratings, short/empty exports, and invalid declared counts.
The expanded suite passed 222 tests in 19.133 seconds. Every new list replayed
exactly from saved snapshots; frozen samples, full-input binding, charged counts,
source caps, and review membership were verified. Historical reference hashes
remain unchanged. Public demonstration and whitespace checks passed. Remote CI
execution is not claimed.

A clean copy of tracked and pending public files, with no private directory,
also passed all 222 tests in 19.161 seconds. Both public demo methods ran there,
and repeated weighted JSON output was byte-identical. The private evidence
directory retains both test logs.

## Smallest next changes to evaluate separately

First, declare an individual-song format policy that excludes explicit continuous
mixes/livestreams and explains how duration and missing metadata are handled.
Test legitimate long songs separately. This addresses an observed product failure;
it was not applied retrospectively to improve these results.

For length, evaluate a larger request budget on the same frozen cohorts while
holding the scorer and source caps fixed. Declare the new cap and runtime target
first; it may conflict with the current under-60-second goal. Retain failures and
check whether more routes actually produce at least five useful sources. Retrieval
scheduling changes would be a further separate experiment if needed. None of
these proposals establishes better listening results without new ratings.
