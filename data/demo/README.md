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

This is the runnable example introduced in the [README](../../README.md), with
the Shygirl/Sega Bodega calculation explained in [the method](../../docs/method.md#worked-example).
The separate [saved historical results](../recommendations/README.md) retain all
11 recordings returned by three later live runs; their reduced public context
does not reproduce full historical selection.

The weighted example returns five songs assigned 2/2/1 across source groups.
The candidate pool is bounded and selected for exposition. This result verifies
code behavior and traceable explanations, rather than listener usefulness.
