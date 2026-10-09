# Architecture

The current recommender ranks recordings through shared contributor credits.
The offline demo and the fast live collector call the same scoring and selection
functions; they differ in how they obtain their inputs and candidate snapshots.

## Pipeline and modules

| Stage | Main modules | Responsibility |
|---|---|---|
| Input preparation | [`parse_library.py`](../src/parse_library.py), [`match_recordings.py`](../src/match_recordings.py) | Convert copied favorites into local JSON and validate input metadata. `match_recordings.py` also retains the earlier matching workflow. |
| Sampling and representative matching | [`quick_recommend.py`](../src/quick_recommend.py), [`seed_matching.py`](../src/seed_matching.py) | Sample artist groups reproducibly, find compatible recordings, and retain matching outcomes and version notices. |
| Candidate collection | [`quick_recommend.py`](../src/quick_recommend.py), [`collect_song_graph.py`](../src/collect_song_graph.py) | Explore contributor routes under bounded collection policies. The fast path orchestrates fresh runs; the separate collector supports matched datasets. |
| Credit extraction | [`credits.py`](../src/credits.py) | Map observed recording/work relationships into role categories while retaining provenance and unmapped evidence. |
| Eligibility and source identity | [`song_policy.py`](../src/song_policy.py), [`source_songs.py`](../src/source_songs.py) | Build the familiar-act registry, check candidate eligibility, and identify source groups and known compositions. |
| Affinity and list selection | [`recommend_songs.py`](../src/recommend_songs.py) | Compute contributor features and base scores, then apply deterministic list constraints and reuse penalties. |
| Public entry points | [`demo.py`](../src/demo.py), [`readme_demo.py`](../src/readme_demo.py) | Recompute the illustrative fixture or render separate saved historical outputs. |
| Evaluation | [`compare_methods.py`](../src/compare_methods.py), [`evaluate_songs.py`](../src/evaluate_songs.py), [`benchmark_matching.py`](../src/benchmark_matching.py), [`benchmark_recommendations.py`](../src/benchmark_recommendations.py) | Prepare comparisons and listening panels, check declared holdouts, and measure live matching and collection behavior. |

`score_song_candidates` creates the base ranking. `select_song_list` chooses the
final list and records selection adjustments and rejection reasons.
`recommendation_report` combines these stages with coverage and policy metadata.
An explanation is assembled from the contributor evidence used in scoring.

## Data boundaries

- **Recording:** a particular performance/recording identity, with primary artists
  and observed performance, production, and engineering relationships.
- **Work:** a composition identity linked from a recording, supplying observed
  songwriting relationships and known-work deduplication evidence.
- **Contributor feature:** one entity with a set of eligible role categories and
  the source credit rows behind them. Multiple credits in one category add one
  category weight.
- **Artist group:** favorites grouped by each credited primary artist for score
  aggregation. A collaboration can contribute to more than one artist group.
- **Source-song group:** favorites grouped by equal nonempty observed work-ID
  sets, falling back to recording identity when work evidence is unknown. These
  groups govern assignment and list balancing, separately from artist influence.

Manifests bind snapshots to queries, retrieval times, and SHA-256 checksums.
[`build_graph.load_dataset`](../src/build_graph.py) validates public snapshot
integrity before the demo or saved-output checks use them.

## Execution modes

The [offline fixture](../data/demo/README.md) supplies all snapshots needed to
recompute scoring and selection. It is selected for illustration.
The [saved historical outputs](../data/recommendations/README.md) include enough
public context to recompute their base scores, but omit the full private candidate
pools and exclusion registry. Their final selection scores are retained outputs.

Live tools write inputs, snapshots, request events, and checkpoints under ignored
private directories. The fast collector charges transport attempts, shares request
pacing across processes, reserves capacity for discovery, and uses a supervisor to
stop stalled collection. Sampling is reproducible from a random seed; live provider
responses and deadline-dependent coverage are not.

## Related and historical tooling

[`process_library.py`](../src/process_library.py),
[`library_job.py`](../src/library_job.py), and
[`library_discovery.py`](../src/library_discovery.py) retain the larger checkpointed
library workflow. [`apple_music.py`](../src/apple_music.py) and
[`check_apple_music.py`](../src/check_apple_music.py) provide optional catalog checks;
the default offline and fast-live paths do not apply an Apple availability filter.

[`build_graph.py`](../src/build_graph.py) and [`recommend.py`](../src/recommend.py)
also retain an earlier artist-graph prototype. Its separate four-recording
[fixture](../reports/graph_fixture.md) checks direct and two-hop artist scores.
That prototype is distinct from the current recording recommender.

The [method](method.md) defines the score and current demo/live selection policy.
The split evaluator retains other selection defaults; comparisons must declare
their policy, rather than assuming every entry point selects lists identically.
