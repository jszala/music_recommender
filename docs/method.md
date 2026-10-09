# Contributor-credit recommendation method

The method explores whether connections through creative contributors yield useful
music recommendations. It uses explicit metadata features and fixed scoring
heuristics, with separate stages for recording identity, candidate collection,
affinity, and list selection. Equal/current weights compare versions of the same
credit method; comparison with listening-behavior recommendations is future work.
The [case study](case_study.md) discusses findings and tradeoffs, and the
[architecture](architecture.md) maps the implementation.

## Data and matching

The illustration uses 39 frozen MusicBrainz snapshots and three constructed favorites: Shygirl’s TWELVE, Cate Le Bon’s Are You With Me Now?, and A Certain Ratio’s Lucinda. They were chosen after inspecting readable paths, rather than sampled for evaluation. Queries, dates, and checksums are in [the manifest](../data/demo/manifest.json). A separate four-recording fixture tests historical artist-graph arithmetic.

Live tooling normalizes title/main-artist text to find compatible representatives. Album, duration, and version evidence rank compatible candidates. This does not verify exact liked audio. Recognized trailing annotations are normalized; literal alternate titles and bounded search pages can remain unresolved. See [seed matching](../src/seed_matching.py) and [the audit](../reports/mvp_matching_audit.md).

Recording relationships supply performance, production, and engineering; linked works supply songwriting. Primary artist credit is a disclosed performance proxy. Group members and missing contributors are not inferred. Multiple roles in one category contribute one category weight. [Credit extraction](../src/credits.py) retains source, scope, relationship ID, attributes, and observed work identities.

These boundaries prevent a composition credit from being silently treated as a
performance credit, or missing metadata from becoming an inferred collaborator.
The familiar-act registry uses the full submitted input in live runs, including
acts whose songs were not sampled for collection.

## Candidate collection

The offline fixture supplies a frozen candidate pool. The fast live collector
instead samples artist groups and explores shared-contributor routes under request
and runtime limits. Its defaults are eight sampled groups, 35 charged transport
attempts, and a 55-second engine budget. Matching receives at most 20 attempts;
remaining capacity supports discovery across source groups. Failed attempts are
charged, and partial results retain their stopping reason.

Retrieval is not exhaustive. Candidate coverage depends on provider responses,
credit availability, explored routes, and remaining capacity. A sampling random
seed alone cannot reproduce a live pool. See [research tools](research_tools.md)
for sampling details and provider behavior.

## Base affinity

[The scorer](../src/recommend_songs.py) uses [fixed weights](../config/song_weights.json): musician 1, songwriter 1, producer 1, staff 0.25. Each contributor receives one weight per distinct eligible category. These are provisional assumptions, not learned importance. The equal baseline assigns 1 to each category and shares every other policy.

Multiply shared contributors’ favorite/candidate weights and sum to x. Pair affinity is **x/(1+x)**, bounding each pair below 1 and reducing increasingly dense-credit influence. This transform is heuristic; no experiment establishes it as optimal.

Average affinities within each favorite-artist group and multiply by **n/(n+5)**, where n counts distinct favorites in the group. More favorites have increasing but diminishing influence; constant 5 is provisional. With one favorite per group, all factors are 1/6 and do not distinguish counts in the public illustration. Sum group contributions for the base score. Multi-artist favorites can contribute to multiple credited-artist groups, as the evidence discloses.

The bounded pair affinity limits the marginal effect of dense credits, while
artist influence limits how strongly many favorites from one act dominate the
score. These are explicit design assumptions. Their usefulness needs separate
ablation and listener evidence; inspectable arithmetic does not validate them.

## Worked example

The [TWELVE snapshot](../data/demo/recordings/08d4b15e-5945-45f6-9ed2-d5490c53de4c.json) records Sega Bodega as producer, engineer, and composer of the linked [work](https://musicbrainz.org/work/855c0c20-a402-488e-8bbc-6df42eb00563): producer + staff + songwriter = **1 + 0.25 + 1 = 2.25**.

The [Adulter8 snapshot](../data/demo/recordings/0927e3e5-0664-4a24-89de-b24c3c911b6a.json) records vocal, primary artist, and producer. Vocal and the primary-artist proxy share the musician category: musician + producer = **1 + 1 = 2**.

```text
x = 2.25 × 2 = 4.5
pair affinity = 4.5 / (1 + 4.5) = 0.818181818…
single-favorite influence = 1 / (1 + 5) = 0.166666666…
base score = 0.818181818… × 0.166666666… = 0.136363636…
```

Other favorite groups contribute zero. Adulter8 is selected second; Sega Bodega has no previous explanatory appearance, so its reuse multiplier is 1 and selection score remains 0.136364. Neither score is an enjoyment probability or quality label.

## Separate selection stage

[Selection](../src/recommend_songs.py) preserves base scores and adjusts connector contributions by **1/(1+previous selected appearances)**. It balances supported source assignments, preferring feasible unrepresented sources before second appearances, with at most two results per source. Each result has one supported assignment and retains every other connection.

Hard policies exclude favorite recording IDs, submitted familiar acts, repeated observed performers, and repeated known works within the list. At most one familiar collaboration is allowed. [Full-input familiar-act exclusions](../src/song_policy.py) remain active in live calls, even when only some favorites are sampled; the demo registry contains its three example favorites. Submitted-act familiarity differs from listener-reported familiarity.

[Observed work IDs](../src/source_songs.py) identify compositions; equal titles do not. Equal nonempty work sets group equivalent seeds; unknown works remain unresolved. Deterministic greedy selection can miss a better combination. Source coverage is not listening quality; configured targets stay visible when missed.

Exact-ID exclusions in the historical follow-up were a separate adaptive experiment, not an implicit listening-history filter in the demo. No weights, exclusions, format policy, or historical scores changed for visual polish.

Artist groups used in affinity aggregation differ from source-song groups used in
selection. A source-song group combines favorites with equal nonempty observed
work-ID sets, falling back to recording identity when work evidence is missing.
Balancing assigns each selected result to one supported source group; it does not
change the base affinity or discard the result's other connections.

These are the demo and fast-live policies. The declared-split evaluator retains
strict contributor reuse and other selection defaults; its variants must be
labeled by policy when compared with these paths.

## Reproduction boundaries

The [README](../README.md) introduces the complete runnable fixture through
`python3 -B -m src.demo`. This recomputes scoring and selection from the 39 frozen
snapshots and three illustrative favorites. The equal method uses the same pool
and policies with equal role weights.

The separate [saved public reports](../data/recommendations/README.md) contain the
complete 4/3/4 outputs of three later runs, with their original per-run ranks, and
retain every credit path and adjustment. Nineteen unmodified snapshots contain the
11 candidates and eight matched favorites needed to reproduce all displayed base
scores with the existing scorer. Unused sampled likes, full candidate pools, and
the personal familiar-act registry stay private; the entire historical selection
process is not reproduced from this reduced context.

[The Markdown renderer](../src/readme_demo.py) formats those saved reports and
checks the supporting documents with `--check-docs`. It does not perform fresh
scoring or selection. Title links point to MusicBrainz; Apple links are labeled
DE-region searches. [Recording evidence](recommendations.md) keeps durations,
versions, all roles, source links, and arithmetic alongside the saved lists.

New provider calls are new observations. A later API can serve the same
recommendation report; [the roadmap](../ROADMAP.md) describes that work.
