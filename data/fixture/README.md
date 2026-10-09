# Public recording fixture, version 1

These four unmodified MusicBrainz API responses were retrieved on 2026-10-06.
They are the deliberately selected test fixture, not a representative sample.
The demo and tests never fetch data. `manifest.json` records the exact API queries,
UTC retrieval times, SHA-256 hashes, seed ID, and inspection notes.

| Recording | Version | MusicBrainz ID | Eligible artists | Edges contributed |
|---|---|---|---:|---:|
| [Get Back](https://musicbrainz.org/recording/beaf49d4-c864-4141-9ce0-162e16778d87) | original mono studio mix | beaf49d4-c864-4141-9ce0-162e16778d87 | 8 | 28 |
| [Don't Let Me Down](https://musicbrainz.org/recording/76a0136f-d130-4a63-81e9-f7a438a86442) | original mono studio mix | 76a0136f-d130-4a63-81e9-f7a438a86442 | 7 | 21 |
| [While My Guitar Gently Weeps](https://musicbrainz.org/recording/863288d1-0fb0-410f-ac45-98e0bd62eac1) | original mono studio mix | 863288d1-0fb0-410f-ac45-98e0bd62eac1 | 8 | 28 |
| [Tears in Heaven](https://musicbrainz.org/recording/21ddde6c-90f4-469e-bdd0-1f438d011917) | studio recording | 21ddde6c-90f4-469e-bdd0-1f438d011917 | 11 | 55 |

Primary artist IDs and all artist-target recording relationships were inspected
by Codex against the recording/track credit pages. The source single for the first
two recordings is [Get Back](https://musicbrainz.org/release/a9108a9c-0bcb-42f2-85ff-5219ac4e07bb).
This was agent inspection, not an independent human audit. The API responses were
not edited or reduced to manufacture the expected graph shape.

For hand arithmetic, the shared core is The Beatles, George Martin, George
Harrison, John Lennon, Paul McCartney, and Ringo Starr. Get Back adds Billy Preston
and Glyn Johns; Don't Let Me Down adds Billy Preston; While My Guitar Gently Weeps
adds Ken Scott and Eric Clapton. Tears in Heaven includes Clapton and ten artists
outside the preceding recordings. See the full names and scores in
[the milestone report](../../reports/graph_fixture.md).

The snapshot retains instrument attributes and dated credit rows. Get Back has
credits from both January 27 and January 28, 1969. Eric Clapton's guest attribute
on While My Guitar Gently Weeps remains eligible. Ed Cherney's recording and mix
credits on Tears in Heaven remain separate roles but one pair/recording evidence.
The Beatles and Billy Preston remain separate primary artists even when the
displayed artist credit joins their names with “with.”

There are eight excluded work-level artist credits: two writers on Get Back,
two writers on Don't Let Me Down, composer and lyricist on While My Guitar Gently
Weeps, and two writers on Tears in Heaven. Will Jennings has no eligible credit
in this fixture and does not become a graph node. Work-to-work relationships do
not create artist edges. No album performers or group membership are inferred.

The graph rules use official recording relationship type IDs from
[MusicBrainz](https://musicbrainz.org/relationships/artist-recording). Tests that
exercise executive, release-level, unknown, and malformed input cases use clearly
synthetic modifications in memory; they do not alter the source fixture.
