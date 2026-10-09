# First public version: v0.1 candidate

An explainable music-credit recommendation prototype. The README introduces the
problem, pipeline, one worked example, experiment findings, and runnable offline
demo. The [case study](docs/case_study.md) explains design tradeoffs and research
priorities; the [architecture](docs/architecture.md) maps the pipeline to code.

The runs returned 4/10, 3/10, and 4/10; the livestream and continuous mix remain
visible in the [saved-results document](data/recommendations/README.md), in their
original order. The [full evidence](docs/recommendations.md) retains every credit
path and score adjustment. Scores, weights, exclusions, and historical results
are unchanged. The constructed fixture reproduces scoring and selection offline;
`src.readme_demo --check-docs` verifies the saved-results documentation.

MusicBrainz core metadata is CC0. Private inputs, contacts, ratings, audio, and
artwork are excluded. MIT is proposed for code; attribution/selection remain pending.
See [verification](docs/verification.md) and [the inventory](PUBLIC_FILES.txt).
No remote push or release is implied by this prepared candidate.
