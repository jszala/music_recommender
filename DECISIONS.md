# Method decisions

These are the current assumptions behind the offline production-credit experiment. Historical policy identifiers remain in the implementation for compatibility. [The method](docs/method.md) and [results](docs/results.md) describe public evidence; the full internal development record is preserved privately.

| Decision | Rationale and consequence |
|---|---|
| Keep recording/work evidence distinct (D-001, D-012, D-013) | Recordings describe performances; works describe compositions. Shared credits do not establish personal collaboration or group membership. |
| Explicit eligible roles (D-002, D-016) | Performance, production, staff, and work-level songwriting form four categories. Primary artist credit is a disclosed performance proxy. |
| Provisional weights/saturation (D-012, D-016) | Weights 1/1/1/0.25 and n/(n+5) make arithmetic inspectable; they are not learned or preference-validated. Equal weights remain a within-method baseline. |
| Representative matching (D-026, D-027) | Normalized title/main artist determine compatibility; album, duration, and version evidence rank representatives. Exact liked audio remains unverified. |
| Separate eligibility/scoring/selection (D-018, D-019, D-025, D-027) | Full-input familiar-act exclusions, performer/work uniqueness, source balancing, and at most one familiar collaboration remain active. Current selection penalizes connector reuse; historical strict callers remain supported. |
| Bounded fresh collection (D-024, D-025) | Charge every attempt, pace requests, preserve partial results and stopping reasons. The cancelled full-library API collection is not resumed. |
| Explicit listener denominators (D-028, D-029) | Familiarity/enjoyment complete a rating; save intention is optional. Exact-ID follow-up exclusions are a declared adaptive experiment. |
| Freeze cohorts before collection (D-030, D-031) | Keep failures, short lists, long-form recordings, blank ratings, and unchanged references. Descriptive differences are not causal improvements. |
| Presentation has no ranking effect | The README explains the pipeline and one illustrative example. Supporting documents retain every saved result in its original run order, with full credit evidence. Documentation changes preserve weights, exclusions, and historical results. |
| Preserve evidence; prepare clean public history | Public fixtures and aggregate findings are distributed; personal inputs and operational diaries are excluded. Existing local history is preserved. |

Historical artist-graph methods (D-001–D-011) remain as a four-recording [arithmetic fixture](reports/graph_fixture.md). They are separate from the song recommender and do not constitute a listening-behavior baseline.
