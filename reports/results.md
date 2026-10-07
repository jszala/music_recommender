# Milestones 1–2 results

Research result: **pending**. This report verifies a deliberately selected public
fixture; it does not measure artist recovery, Recall@K, or listener preference.
The eventual study concerns one person's selected favorites, following D-008.

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

Both CLI methods and text/JSON output were run locally. Tests disable socket
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

## Milestone 1 boundary

Milestone 1 delivers the public fixture, graph, two rankings, source-backed
explanations, checks, README, and decision log. The requested private text-to-JSON
conversion is a small intake utility, not a recording matcher. Matching, holdout
evaluation, and degree-penalty comparisons remain later work. API sampling is
documented below.

## Milestone 2: bounded real-data pilot

Implementation and API collection are complete. Independent human identity and
recording-page review remain **pending**. No recommendation-quality metric or
library-coverage estimate has been measured.

The pilot was collected on **2026-10-06, 19:06:09–19:07:34 UTC**. The frozen
sample ID is
`6e84c0d93daeada06785206d3a74a70bdb419c95dd4e2b726e66f0ea5435554b`.
Its ignored local directory is `data/private/musicbrainz_sample_2026-10-06/`.
Raw recording responses, contact information, favorites provenance, cache, and
the detailed review files are kept out of Git. This report contains aggregate
diagnostics and a few public source links, not the downloaded dataset.

Seed choice, limits, and expansion policy were written in D-010/D-011 before
collection. The three seeds are the most frequent exact artist names in the
private favorites. Artist-page identity checks were performed by Codex; no
favorite song was matched. Initial collection takes eight recordings from each
seed's first primary-credit browse page, preserving the server's returned order.
The frontier takes two intermediaries per seed by shared-recording count, with
MBID tie-breaking. One expansion round takes six additional recordings per
intermediary from eligible recording relationships and one primary-credit browse
page, sorted by MBID. It does not recursively expand newly discovered candidates.

| Seed | Primary-credit recordings reported by API | Initial recordings fetched | Direct neighbors in pilot |
|---|---:|---:|---:|
| Unknown Mortal Orchestra | 165 | 8 | 3 |
| Cate Le Bon | 141 | 8 | 12 |
| Kendrick Lamar | 1,921 | 8 | 13 |

These are browse totals observed at retrieval, not numbers of unique songs in
the favorites or estimates of complete relationship coverage. The first pages
favor titles near the start of the API ordering. Multiple versions and recordings
with only a primary artist consume the same eight-recording allowance.

Selected intermediaries were Action Bronson, Yelawolf, Queen, Free Nationals,
St. Vincent, and Manic Street Preachers. Their selection was mechanical, not
chosen after inspecting whether the recommendations looked attractive. The
manifest preserves all unselected frontier IDs, selected/omitted expansion IDs,
reported browse totals, returned relationship counts, and the evidence behind
each selection. Artist relationship-list completeness is not certified.

| Diagnostic | Observed count |
|---|---:|
| Seed recordings / additional recordings | 24 / 36 |
| Eligible graph artist entities | 116 |
| Eligible artist–recording credit pairs | 223 |
| Distinct eligible role-credit rows | 327 |
| Distinct undirected artist edges | 533 |
| Recording-backed edge contributions | 640 |
| Excluded artist-credit rows | 134 |
| Positive direct candidates, seed-only / expanded | 28 / 28 |
| Positive two-hop candidates, seed-only / expanded | 28 / 113 |
| Candidates newly reachable by expansion | 85 |
| API HTTP attempts / recorded collection failures | 78 / 0 |
| HTTP attempts in offline replay | 0 |

The 134 exclusions comprise 120 work-level rows and 14 recording-level rows:
writers, composers, lyricists, and publishing at work level; programming,
editor/arranger/orchestrator/copyright roles and two executive producer credits
at recording level. The manifest records relationship IDs and observed role
counts; `exclusions.json` retains each artist, source recording, role, level, and
reason. Release-only credits were not queried, so their absence is not an observed
exclusion count.

All 113 nonseed graph entities receive positive two-hop scores in the expanded
pilot. That follows from collecting around an existing frontier and demonstrates
reachability under this sampling policy; it does not demonstrate preference
relevance, recall, or coverage of the user's favorites.

## Pilot recommendation paths for review

| Candidate | Direct score | Two-hop score | Total |
|---|---:|---:|---:|
| The Alchemist | 0 | 9 | 9 |
| A$AP Rocky | 3 | 4 | 7 |
| Anderson .Paak | 0 | 7 | 7 |
| Loz Williams | 1 | 6 | 7 |
| Manic Street Preachers | 1 | 6 | 7 |
| Cian Riordan | 0 | 6 | 6 |
| Brian May | 0 | 4 | 4 |

This table selects leading candidates and two useful audit cases; it is not the
complete ranking. All contributions and qualifying paths are stored in the
sample's recommendation JSON. The following descriptions were inspected against
cached API responses. **Recording-page verification is still pending.**

- **The Alchemist via Action Bronson:** Kendrick Lamar and Action Bronson are
  both primary credited artists on [1 Train, clean](https://musicbrainz.org/recording/5982a185-a053-4a48-bcd5-7db1ba83e628).
  Action Bronson (primary artist, guest vocal) and The Alchemist (primary artist,
  producer, mix) are both credited on [Daily News, 2023 reissue](https://musicbrainz.org/recording/2c09a670-06cf-43c5-9e20-8c9f71eb1b80).
  This recording pair contributes +1. His complete nine points are three distinct
  1 Train recording IDs (clean, unspecified, explicit) paired with three expanded
  recordings: Daily News, 5 Minute Beats 1 Take Raps, and Red Dot Music. They are
  nine recording pairs, not nine independent song-level associations. Work-level
  writing credits are excluded even when those same people have eligible roles.
- **Cian Riordan via St. Vincent:** Cate Le Bon and St. Vincent are both primary
  credited artists on [All Born Screaming, Dolby Atmos mix](https://musicbrainz.org/recording/28d7be9d-19ed-4a41-ad85-a4f2bccdf767).
  St. Vincent (producer) and Riordan (engineer) are both credited on
  [The Dog/The Body](https://musicbrainz.org/recording/04ee8cfc-e85b-43ef-9a48-02a4e6dfa34b).
  This pair contributes +1. All six points come from three Cate Le Bon–St. Vincent
  recordings paired with The Dog/The Body and Hurry on Home. Riordan's eligible
  roles in this sample are engineering roles. The graph does not establish that
  he is a recording artist to listen to.
- **Brian May via Queen:** Unknown Mortal Orchestra and Queen are both primary
  credited artists in the API response for [Bicycle (interlude)](https://musicbrainz.org/recording/0a76e7fb-5917-4aa3-91e7-352105d0e304).
  Queen (primary artist, producer) and May (guitar, background vocals) are both
  credited on [Hammer to Fall](https://musicbrainz.org/recording/0002b951-4fd1-4a99-bb20-6c8fc648d73b).
  This pair contributes +1. The unexpected first-leg credit deserves a human
  identity/version/context check. Co-credits do not establish a studio session
  between the bands; membership alone was not used to connect May.

## Pilot checks, limits, and outstanding review

Final verification on 2026-10-06: **40 tests passed** with
`python3 -m unittest discover -s tests -v`, including the 24 existing fixture/intake
checks and 16 collector checks. Synthetic HTTP tests cover producer-only expansion,
cache reuse/failures/corruption, network-disabled replay, request bounds and timing,
retry hints, truncation, immutable sample outputs, and missing-seed diagnostics.
Both real-sample CLI methods reproduced their saved contribution outputs.

The real sample was rebuilt from cache with zero HTTP requests. Source hashes,
sample ID, graph statistics, coverage, and both complete ranking JSON files were
identical. Every score contribution sum, path, distinct recording-pair key, and
collection origin was checked. All 78 API attempts were within the 100-attempt
cap; the minimum observed request-start interval exceeded one second.

The implementation agent attempted nine recording-page GETs using the approved
User-Agent and the same rate limiter, bringing collection plus page review to
87 HTTP attempts. All nine returned MusicBrainz's browser-verification screen,
so **none is counted as a completed page inspection**. Those responses and
retrieval metadata are cached locally. API snapshot inspection and automated
checks do not replace independent human review. The local `REVIEW.md` includes
six candidate cases, recording versions/durations, roles, excluded credits, and
space for the user's notes; `AGENT_REVIEW.md` records what was actually checked.

The largest recording, Reachin’ 2 Much (clean), has 19 eligible entities and
supplies 171 of the 640 recording-backed edge contributions. St. Vincent has 24
neighbors and connects Cate Le Bon to technical contributors as well as recording
artists. Separate clean/explicit/mix versions can multiply evidence. Unknown
Mortal Orchestra's first-page sample has only three direct neighbors, including
the surprising Queen credit. These are material coverage and modeling limits,
not reasons to change the sample after seeing its results.

Keep role eligibility, candidate rules, and recording-ID deduplication unchanged
until reviewing these paths with the user. Discuss whether production staff are
useful outputs, whether repeated versions overstate independent evidence, and
whether the first-page/selected-frontier coverage is adequate for the next step.
No dump, role weights, degree penalty, song matching, holdout evaluation, or recall
numbers were added in Milestone 2. The implementation supports traceable real
records; the milestone's human-review component remains open.
