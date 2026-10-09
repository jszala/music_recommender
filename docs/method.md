# Production-credit method

This exploratory data science method is an offline work in progress. The question is whether connections through creative contributors yield useful recommendations, and how that behavior differs from listening-behavior recommendations. The latter comparison is future work. Equal/current weights compare versions of this credit method.

## Data and matching

The illustration uses 39 frozen MusicBrainz snapshots and three constructed favorites: Shygirl’s TWELVE, Cate Le Bon’s Are You With Me Now?, and A Certain Ratio’s Lucinda. They were chosen after inspecting readable paths, rather than sampled for evaluation. Queries, dates, and checksums are in [the manifest](../data/demo/manifest.json). A separate four-recording fixture tests historical artist-graph arithmetic.

Live tooling normalizes title/main-artist text to find compatible representatives. Album, duration, and version evidence rank compatible candidates. This does not verify exact liked audio. Recognized trailing annotations are normalized; literal alternate titles and bounded search pages can remain unresolved. See [seed matching](../src/seed_matching.py) and [the audit](../reports/mvp_matching_audit.md).

Recording relationships supply performance, production, and engineering; linked works supply songwriting. Primary artist credit is a disclosed performance proxy. Group members and missing contributors are not inferred. Multiple roles in one category contribute one category weight. [Credit extraction](../src/credits.py) retains source, scope, relationship ID, attributes, and observed work identities.

## Base affinity

[The scorer](../src/recommend_songs.py) uses [fixed weights](../config/song_weights.json): musician 1, songwriter 1, producer 1, staff 0.25. Each contributor receives one weight per distinct eligible category. These are provisional assumptions, not learned importance. The equal baseline assigns 1 to each category and shares every other policy.

Multiply shared contributors’ favorite/candidate weights and sum to x. Pair affinity is **x/(1+x)**, bounding each pair below 1 and reducing increasingly dense-credit influence. This transform is heuristic; no experiment establishes it as optimal.

Average affinities within each favorite-artist group and multiply by **n/(n+5)**, where n counts distinct favorites in the group. More favorites have increasing but diminishing influence; constant 5 is provisional. With one favorite per group, all factors are 1/6 and do not distinguish counts in the public illustration. Sum group contributions for the base score. Multi-artist favorites can contribute to multiple credited-artist groups, as the evidence discloses.

## Checked example

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

## README demonstration

The [README](../README.md) shows the complete 4/3/4 outputs of the three recent
runs, with their original per-run ranks. [Saved public reports](../data/recommendations/README.md)
retain every credit path and adjustment. Nineteen unmodified snapshots contain the
11 candidates and eight matched favorites needed to reproduce all displayed base
scores with the existing scorer. Unused sampled likes, full candidate pools, and
the personal familiar-act registry stay private; the entire historical selection
process is not reproduced from this reduced context.

[The Markdown renderer](../src/readme_demo.py) only formats those saved reports.
It does not score, filter, merge, rerank, or fetch data. There is no separate web
application, screenshot, cover-art placeholder, or GitHub Pages deployment. Missing
art is omitted. Title links point to MusicBrainz; Apple links are labeled DE-region
searches. [Recording evidence](recommendations.md) keeps durations, versions, all
roles, source links, and arithmetic outside the main list.

The separate [constructed fixture](../data/demo/README.md) retains full offline
scoring/selection and the worked example above through `src.demo`. A later API can
serve the same recommendation report; [the roadmap](../ROADMAP.md) describes that work.
