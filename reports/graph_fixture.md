# Historical artist-graph fixture

This separate, four-recording arithmetic fixture predates the song recommender.
It tests graph evidence counts, rather than recommendation quality.
Reproduce it with `python3 -B -m src.recommend`.

## Verified graph

The frozen 2026-10-06 snapshot produces **20 eligible artists, 4 recordings,
96 distinct undirected edges, and 132 recording-backed edge contributions**.
Every edge contribution retains both artists' eligible roles and recording URL.
All fresh source artist sets match the planning expectations; no credits were
altered to make the counts match. Independent human inspection remains pending.

| Recording | Eligible artists | Pair evidence |
|---|---:|---:|
| Get Back (original mono) | 8 | 28 |
| Don't Let Me Down (original mono) | 7 | 21 |
| While My Guitar Gently Weeps (original mono) | 8 | 28 |
| Tears in Heaven (studio) | 11 | 55 |
| Total recording-backed evidence | — | **132** |

For each recording, pair count is `n × (n − 1) / 2`. Don't Let Me Down's 21 pairs
already occur on Get Back. While My Guitar Gently Weeps overlaps Get Back in six
artists, hence 15 pairs. Tears in Heaven intersects that neighborhood only at
Clapton and contributes no already-seen pair. Thus distinct edges are
`28 + (21 − 21) + (28 − 15) + 55 = 96`.

Eight work-level artist credits are excluded, with reasons available in the JSON
demo output. Source records, queries, hashes, and inspection notes are in
[the fixture manifest](../data/fixture/manifest.json) and
[fixture documentation](../data/fixture/README.md).

## Complete fixture ranking

Seed: **The Beatles**, MusicBrainz ID `b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d`.
Both methods use the same 19 nonseed candidates. Zero direct scores remain visible.
This table follows the two-hop method's deterministic order; run the direct demo
to see its independently sorted order.

| Rank | Artist | Direct | Added two-hop | Total |
|---:|---|---:|---:|---:|
| 1 | George Harrison | 3 | 3 | 6 |
| 2 | George Martin | 3 | 3 | 6 |
| 3 | John Lennon | 3 | 3 | 6 |
| 4 | Paul McCartney | 3 | 3 | 6 |
| 5 | Ringo Starr | 3 | 3 | 6 |
| 6 | Billy Preston | 2 | 3 | 5 |
| 7 | Eric Clapton | 1 | 2 | 3 |
| 8 | Glyn Johns | 1 | 2 | 3 |
| 9 | Ken Scott | 1 | 2 | 3 |
| 10 | Alex Haas | 0 | 1 | 1 |
| 11 | Ed Cherney | 0 | 1 | 1 |
| 12 | Gayle Levant | 0 | 1 | 1 |
| 13 | Jay Dee Maness | 0 | 1 | 1 |
| 14 | Jeff DeMorris | 0 | 1 | 1 |
| 15 | Jimmy Bralower | 0 | 1 | 1 |
| 16 | Lenny Castro | 0 | 1 | 1 |
| 17 | Nathan East | 0 | 1 | 1 |
| 18 | Randy Kerber | 0 | 1 | 1 |
| 19 | Russ Titelman | 0 | 1 | 1 |

## Hand calculation of every score

Let G = Get Back, D = Don't Let Me Down, W = While My Guitar Gently Weeps,
and T = Tears in Heaven, using the exact recording IDs in the fixture manifest.
A direct recording contributes +1. Each unordered pair of different recordings
with a valid intermediate artist contributes +1 per seed and candidate, regardless
of how many paths it supplies. Candidates can have both direct and two-hop evidence.

| Candidates | Direct recordings | Two-hop recording pairs | Sum |
|---|---|---|---|
| Harrison, Martin, Lennon, McCartney, Starr | G, D, W | G–D, G–W, D–W | 3 + 3 = 6 |
| Preston | G, D | G–D, G–W, D–W | 2 + 3 = 5 |
| Clapton, Scott | W | G–W, D–W | 1 + 2 = 3 |
| Johns | G | G–D, G–W | 1 + 2 = 3 |
| Ten T-only candidates | none | W–T | 0 + 1 = 1 |

For G–D evidence to George Martin, five intermediaries qualify: George Harrison,
John Lennon, Paul McCartney, Ringo Starr, and Billy Preston. Both recording
orientations are valid, yielding ten paths. The entire pair still supplies **one**
point, and all ten paths are retained. Other core artists can use Martin as an
intermediary; G–W and D–W likewise have shared core intermediaries.

For Billy Preston's G–W and D–W points, one witness is George Martin: The Beatles
and Martin are both credited on W; Martin and Preston are both credited on G or D.
Preston does not need to be credited on W himself.

For Nathan East's W–T point, the only intermediary is Eric Clapton: The Beatles
and Clapton are both credited on W; Clapton and East are both credited on T.
The same two-hop evidence pair supplies each of the other nine T-only candidates.
The demo prints actual roles and source URLs for both legs of every retained path.

## Checks and observed limitations

The offline test suite checks independent artist sets, counts and scores; snapshot
checksums; source and role evidence for every edge; all contribution sums and path
validity; duplicate rows, roles, recordings and seeds; both recording orientations;
group separation; excluded work, executive, release-level and unknown credits;
seed exclusion; empty and unknown seeds; deterministic ordering; and the JSON CLI.
Private text conversion checks both supported layouts and preserves ambiguous rows.

Both historical artist-ranking methods and text/JSON output were run locally. Tests disable socket
creation for fixture loading and ranking to verify that those functions work offline.

Final verification on 2026-10-06: **24 tests passed** with
`python3 -m unittest discover -s tests -v`. The direct baseline returns 19
candidates, 9 with positive scores, and 20 total unit score contributions.
The two-hop baseline returns the same 19 candidates, all with positive scores,
and 54 total unit score contributions. These totals are fixture diagnostics.
The supplied private input was converted and checked row by row for preservation;
both the original and converted JSON are ignored by Git. Zero format-review rows
does not imply that any recording identity has been matched.

The dense T recording creates 55 edges. Clapton has degree **17** and bridges
the seed to ten equally scored candidates through T. Recording-pair capping
prevents multiple intermediaries from multiplying the same pair contribution,
but does not solve dense-recording or prolific-intermediary bias. No degree
penalty has been added, and no role weights have been selected from these examples.

Will Jennings is excluded as a work-only writer; this illustrates the model's
deliberate loss of songwriting relationships. Graph coverage, matching precision,
holdout leakage, and recommendation quality remain unmeasured. Missing artists
in the favorites list must not be interpreted as disliked artists.
