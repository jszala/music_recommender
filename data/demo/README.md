# Public illustrative song demo

This constructed example uses TWELVE (Shygirl), Are You With Me Now? (Cate Le Bon),
and Lucinda (A Certain Ratio). They were chosen to demonstrate several productive
source groups and readable shared-credit paths, after inspecting available
snapshots. This is illustrative selection, not an unbiased evaluation sample or
a published personal favorites list.

The 39 recording snapshots contain frozen MusicBrainz core metadata collected on
2026-10-07. Recording IDs, exact source queries, retrieval times, and snapshot
checksums appear in `manifest.json`. The snapshots are unmodified public provider
responses extracted from the bounded historical collection. Private favorites,
contact information, request caches, personal provenance, audio, and artwork are
not included. Core metadata is CC0; see
[MusicBrainz data licensing](https://musicbrainz.org/doc/About/Data_License).

Run `python3 -B -m src.demo` from the repository root. `--method equal` changes
only role weights; scorer, saturation, candidate snapshots, and hard selection
policies remain shared with the weighted run and live prototype.

The main [README example](../../README.md) shows all 11 saved results from three
recent runs. This smaller constructed fixture is retained for scoring/selection
reproduction and the checked Shygirl/Sega Bodega example in [the method](../../docs/method.md).

The weighted example returns five songs assigned 2/2/1 across source groups.
The candidate pool is bounded and selected for exposition. This result verifies
code behavior and traceable explanations, rather than listener usefulness.
