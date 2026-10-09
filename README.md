# Music-credit recommender

An explainable music-discovery prototype that recommends recordings through shared
musicians, songwriters, producers, and engineers. Given favorite songs, it uses
MusicBrainz metadata to find connected recordings, score their shared credits, and
select a varied list. Each recommendation includes the contributor paths behind
its score.

The project asks whether the people behind favorite songs can provide useful
discovery signals across artists. It combines metadata matching, contributor
features, heuristic ranking, and constrained selection. The weights are fixed
assumptions; the system does not train on listening histories or audio.

A reproducible offline demo and optional live collection tools are included.
Current experiments expose limitations in metadata coverage and discovery;
recommendation-quality improvements remain unproven.

## How it works

```text
Favorite-song metadata
  → Match MusicBrainz recordings
  → Extract recording and composition credits
  → Discover candidates through shared contributors
  → Score credit connections
  → Select recommendations with source and diversity constraints
  → Export scores, explanations, and coverage diagnostics
```

1. **Match songs to recordings.** Normalized titles and main artists establish
   compatibility. Version, album, and duration evidence rank compatible matches.
   A match represents a song; exact liked audio is not independently verified.
2. **Build contributor features.** Recording relationships supply performance,
   production, and engineering credits; linked works supply songwriting credits.
   Primary artist credits act as performance proxies. Source links and role
   evidence remain attached to each feature.
3. **Collect candidates.** Live collection explores contributor connections under
   request and runtime budgets, recording failures and partial coverage. The
   offline demo starts from frozen snapshots and makes no provider calls.
4. **Score affinity.** For each shared contributor, multiply their favorite-song
   and candidate role weights, then sum the products. Transform that sum with
   `x / (1 + x)` and aggregate across favorite-artist groups with diminishing
   influence from additional favorites by the same artist.
5. **Select a list.** A deterministic greedy selector balances source songs,
   penalizes repeated explanatory contributors, and applies familiar-act,
   performer, and known-composition constraints. It can return fewer songs than
   requested when the pool cannot satisfy those policies.

The current role weights are **musician 1, songwriter 1, producer 1, and engineering
staff 0.25**. Scores measure shared-credit affinity, not enjoyment probability.
The [method](docs/method.md) explains the arithmetic and assumptions;
the [architecture](docs/architecture.md) maps the stages to code.

## One recommendation explained

The offline fixture connects Shygirl's **TWELVE** to Sega Bodega's **Adulter8**:

```text
TWELVE → Sega Bodega → Adulter8
         producer       musician
         songwriter     producer
         engineer
```

Sega Bodega's weights are `1 + 1 + 0.25 = 2.25` on TWELVE and `1 + 1 = 2` on
Adulter8. Their product is `4.5`, giving a pair affinity of `4.5 / 5.5 = 0.818182`.
The favorite-artist influence is `1 / (1 + 5)`, producing a base score of
**0.136364**. Adulter8 is selected second in this constructed example.

This is a traceable metadata connection. The fixture was chosen for readable
examples and does not measure listener usefulness. See the
[source evidence and full calculation](docs/method.md#worked-example).

## What the experiments show

| Experiment | Observation | Interpretation |
|---|---|---|
| Fixed matching audit | 73/100 accepted; 18 HTTP 503 failures; 9 no-compatible outcomes | End-to-end acceptance includes provider failures; identity precision is not independently established. |
| Credit coverage in that audit | 31/73 accepted inputs had additional eligible credit evidence | Sparse metadata limits the available discovery signal. |
| Equal versus current weights on three historical pools | Identical selected lists and order | No selection advantage from the chosen weights was observed on those pools. |
| Initial listener review | 8/8 enjoyable and 8/8 already familiar | Enjoyment was reported, but new-to-listener discovery was not demonstrated. |
| Three later live runs | 4/10, 3/10, and 4/10 delivered; all reached 35 attempts | Retrieval coverage and selection constraints limited list length. |

The constructed offline fixture returns five recommendations and shows that
weights can change selection: equal and current weights share two of five
results. That illustration is separate from the historical experiments above.
Later listening reviews remain pending, and a listening-behavior baseline has
not been implemented.

Read the [case study](docs/case_study.md) for design tradeoffs and findings, or the
[results](docs/results.md) for protocols, denominators, and limitations.
[Saved recommendation evidence](docs/recommendations.md) retains every result
from the later runs, including a livestream and continuous mix.

## Run the offline demo

Python **3.12 or later**, using only the standard library. Run from the repository
root; the demo and tests need no installation, account, credentials, or network.

```bash
python3 -B -m src.demo
python3 -B -m src.demo --method equal
python3 -B -m src.demo --format json
python3 -B -m unittest discover -s tests -v
```

`src.demo` recomputes scoring and selection from 39 frozen MusicBrainz snapshots
and three illustrative favorites. To inspect the separate historical exports:

```bash
python3 -B -m src.readme_demo --format details
python3 -B -m src.readme_demo --check-docs
```

The saved exports allow base-score and credit-path verification, but their full
historical candidate pools and personal exclusions are private. See
[dataset scope](data/demo/README.md) and [saved-run scope](data/recommendations/README.md).
[Live research tools](docs/research_tools.md) accept local favorites and require
network access and provider contact information; they produce new observations.

## Repository guide

| Location | Purpose |
|---|---|
| [`src/`](src/) | Matching, collection, credit extraction, scoring, selection, and evaluation tools; see the [module map](docs/architecture.md). |
| [`config/`](config/) | Fixed role weights, matching rules, and collection limits. |
| [`data/demo/`](data/demo/) | Complete offline scoring and selection fixture. |
| [`data/recommendations/`](data/recommendations/) | Saved historical outputs and supporting source snapshots. |
| [`tests/`](tests/) | Arithmetic, policy, leakage, transport, and reproducibility checks. |
| [`reports/`](reports/) | Detailed experiment records and the separate historical artist-graph fixture. |

[Method decisions](DECISIONS.md) · [Roadmap](ROADMAP.md) ·
[Verification](docs/verification.md) · [Data and license status](DATA_LICENSE.md)

MusicBrainz core metadata is CC0. Audio and artwork are not included.
Developed with Codex assistance.
