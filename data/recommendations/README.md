# Saved recommendation example

These are the complete selected outputs of the three different-song cohorts
(integers 6, 9, and 10), collected on 2026-10-08: 4/10, 3/10, and 4/10 recordings.
Every returned recording remains in its original run and rank, including a
livestream and continuous mix. No list was filled, filtered, or reranked for display.

The root [README](../../README.md) renders these 11 recordings as ordinary Markdown.
`python3 -B -m src.readme_demo` reproduces that list. `--format details` shows every
credit path and score adjustment; `--format json` returns the saved public reports.

Nineteen unmodified MusicBrainz snapshots cover the 11 recommendations and the
eight matched favorites that appear in their credit paths. Each run manifest binds
queries, recording IDs, retrieval times, and snapshot checksums. `index.json` binds
the three saved reports. With this context, the existing scorer reproduces every
displayed base score and contribution exactly.

This is a frozen output demonstration. Full candidate pools, unused sampled likes,
personal input, familiar-act registry, contact files, and ratings remain private.
The public context does not reproduce the entire historical selection process.
The separate [constructed fixture](../demo/README.md) runs full scoring/selection
offline and retains its five-result illustration.

Core metadata is [CC0](https://musicbrainz.org/doc/About/Data_License). No artwork or
audio is included. Apple links are labeled DE-region searches, not verified track
matches. See [the protocol/results](../../reports/different_seed_results.md) and
[full credit evidence](../../docs/recommendations.md).
