# Implementation results and limitations

Research result: **pending**. This report verifies a deliberately selected public
fixture; it does not measure artist recovery, Recall@K, or listener preference.
The eventual study concerns one person's selected favorites, following D-008.

## Milestone 4c: API scale-up cancelled as impractical

The full-library workflow is implemented under D-023. **152 offline tests pass**,
including a synthetic job across multiple provider tranches and a fresh zero-network
replay with identical matching decisions, consolidated profiles, recording snapshots,
four scoring reports, selected order, and playlist preparation. Interruption,
persistent budgets, conflicting snapshots, discovery breadth/paging/refill, operational
retries, Apple raw-response reuse, expanded-dataset binding, and partial-stage reporting
are covered. Existing scoring and hard selection constraints remain in force.

The user cancelled full-list collection and its queued continuation on 2026-10-07.
**The MusicBrainz public API approach is not feasible for the intended full-library
matching, broad contributor discovery, and repeated experiments.** Rate-limited
serial collection with several requests per row and neighborhood expansion takes
hours; transient failures add retries. Resumability and caching preserve work but
do not remove the cost of discovering new evidence. Small bounded API pilots remain useful.

The discontinued run imported the frozen 20-row pilot. The first additional
100 rows required 320 HTTP attempts and about 435 seconds. The observed remaining
matching estimate at that checkpoint was about 87 minutes, before discovery and
Apple collection. This timing sample does not estimate matching precision or acceptance
coverage. An additional 2–4 hours for the complete pipeline was estimated before
cancellation; this was a projection, not a measured completed runtime.

Final retained outcomes: **538 checkpointed rows**, comprising 187 accepted rows
(187 distinct recordings, 156 resolved primary-artist IDs), 342 unresolved rows,
and nine operational failures caused by HTTP 503 responses. Of the unresolved rows,
94 had literal searches with no result, 14 were ambiguous, and 234 had no confident
match. One additional row was interrupted and 777 were unattempted. **1,663 new
MusicBrainz HTTP attempts** remain charged, including the interrupted send; the
56 historical pilot attempts are recorded separately. Discovery and Apple each
made zero new attempts. No expanded graph, full-profile batch, or complete live
offline verification was produced.

[The cancellation report](full_library_run.md) records final partial coverage.
Both processes are stopped; completed row checkpoints and frozen responses remain
in `data/private/full_library_2026-10-07/`, and provider caches and earlier pilot
artifacts are preserved. Full-list completion remains outstanding. The next backend
should evaluate downloaded MusicBrainz data and local indexes under D-024;
download/import and backend adaptation have not been implemented or benchmarked.

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

## Discussion after the pilot: song recommendations and recording versions

On 2026-10-07 the user clarified that the intended outputs are songs, with every
credit contributing to some extent. Recording staff should have lower impact than
songwriters, producers, and central musicians; the role definitions and numerical
weights are pending. Many favorites from one artist should have saturated influence.
The user subsequently clarified that all musicians have the same base weight;
songwriting adds a separate contribution, and no central-musician category is used.
These are future requirements recorded in [D-012](../DECISIONS.md#d-012-recommend-songs-using-credits-with-bounded-preference-impact).
The reported pilot continues to use artist candidates and equal unit weights.

Recording-version inflation remains an explicit open problem, recorded in
[D-013](../DECISIONS.md#d-013-recording-identity-and-version-evidence-remain-an-open-problem).
The same recording on a compilation or deluxe edition, and a remaster without a
new performance, mix, or edit, should not supply independent track evidence.
Live recordings and remixes should remain distinct candidates; original/mono mixes
can themselves matter to preference. MusicBrainz recording IDs provide an initial
deduplication boundary, but cross-ID duplicates and ambiguous version metadata
remain unresolved. Candidate identity and independence of evidence need separate
rules; collapsing titles or all recordings of one work would lose meaningful
differences. No version grouping, role weighting, or saturation has been implemented.

## Milestone 3 implementation and song-ranking foundation, 2026-10-07

The previous discussion paragraph records the state before this implementation.
Conservative recording matching, a credit audit, bounded contributor-based song
collection, additive role scoring, artist saturation, and fixed recording-split
evaluation tools are now implemented. The original fixture and artist pilot remain
historical baselines. Full-favorites matching, independently reviewed identity
precision, the approximately 100-match audit, and listening-quality evaluation are
still pending; the tools do not complete those human/research requirements.

### Initial 20-song matching batch

The D-014 review selection supplied the input. D-015 fixed literal search, two
25-result pages, at most four recording lookups per song, a 2-second duration
allowance, and a 120-attempt cap before collection. Automatic acceptance also
requires exact normalized title/combined artist, an observed matching album release,
one qualifying recording, resolved version markers, complete declared search, and
inspection of returned exact alternatives. Human decisions require source-bound
reviewer/evidence fields; ambiguous cases are never forced into the profile.

| Diagnostic | Count |
|---|---:|
| Favorite rows processed | 20 |
| Rule-accepted distinct recordings | 9 |
| Rows needing review | 4 |
| Literal queries returning no results | 7 |
| Candidate recording snapshots fetched | 32 |
| HTTP attempts / collection failures | 56 / 0 |
| Offline replay HTTP attempts | 0 |
| Independently human-reviewed rows | 0 |

The mixed 5+15 selection is a workflow audit, not a representative sample for
precision or library coverage. Zero literal results do not establish that the song
is absent from MusicBrainz; aliases, source spelling, combined artist text, and
version titles remain possible causes. Three review rows had exact alternatives
beyond the lookup cap; one search also exceeded the page cap. Every review row
lacked a candidate with all required acceptance evidence. Collection complete under
its limits does not mean every identity is resolved.

Among the nine rule-accepted recordings, all have primary-artist musician-category
proxies, but only two have detailed performer credits. Four have observed songwriting
credits, two have producer credits, and two have staff credits. An arranger and a
phonographic-copyright credit remain unmapped and preserved. Missing roles are not
evidence that nobody performed those roles. This sparse coverage limits the intended
sound/contributor signal even when recording identity is reliable.

The ignored directory `data/private/recording_matches_2026-10-07/` contains exact
snapshots, hashes, query history, alternatives, check results, source rows, a deduplicated
recording profile, credit audit, review sheet, and source-bound manual-review template.
Offline replay reproduced the sample fingerprint and matching/profile/audit outputs.

### Bounded song graph and scoring

D-017 fixes contributor selection and candidate bounds. Collection starts at the
nine rule-accepted recordings, selects six contributors by distinct favorite evidence,
and uses recording relationships, paginated primary-credit browse, and eligible
songwriting-work relationships. It produced 36 additional recording candidates in
56 HTTP attempts without collection failures. Offline replay used zero requests.
The 45-recording graph has observed songwriting on 19 recordings, production on 17,
and staff credits on 15. All 36 candidates have positive shared-credit scores,
which reflects frontier-based collection and is not preference-quality evidence.

D-016 records provisional category weights: musician 1, songwriter 1, producer 1,
staff 0.25. Each distinct category contributes once per contributor/recording;
musician and songwriter add, while repeated instruments and duplicated rows do not.
Shared-contributor products are bounded as `x/(1+x)`, averaged within primary
favorite-artist groups, and multiplied by `n/(n+5)`. This bounds each group's total
influence. The equal-role and unsaturated comparators use the same graph and favorites.
No weight, saturation parameter, or sampling rule was tuned to these results.

`data/private/song_graph_2026-10-07/` stores the graph, all three ranking JSON files,
and `SONG_REVIEW.md` with ten suggestions and their source paths for user review.
Favorite recording IDs are excluded. Cross-ID audio equivalence, unknown-role mapping,
release-level credits, contributor-degree penalties, and final-list diversity remain
open. Separate live/remix IDs remain available; titles or shared works are not merged.

The evaluator compares the three methods on declared recording splits, groups only
explicitly established equivalent identities, rejects training/held-out overlap,
and reports overall and reachable denominators separately. Research mode requires
collection provenance bound to training favorite IDs. Only the public fixture
demonstration has been run; its output is labeled `demonstration_diagnostics` and is
not a saved-favorites evaluation result.

Validation: 76 offline tests pass, including matching ambiguity, truncation, failures,
review binding, credit scope, songwriting/engineering discovery, pagination, additive
role arithmetic, saturation bounds, duplicate invariance, contribution sums, snapshot
hashes, and evaluation leakage. Both real collections replay from cache; all saved
song-ranking contribution sums and per-artist influence bounds were checked. Personal
inputs, downloaded data, and generated review/ranking artifacts remain ignored by Git.

## Historical D-018/D-019 discovery-policy implementation, 2026-10-07

The first user review identified familiar acts dominating the song list: nine of
the ten highest-ranked songs carried one input act's primary credit, and all ten
carried an input artist's credit. Artist saturation had bounded each favorite
artist's contribution to an individual candidate, but did not constrain list
membership; collection still allocated contributor slots by raw favorite counts.

D-018/D-019 now exclude submitted acts, permit at most one supported familiar-artist
collaboration across the list, and use each observed musician once. Production,
engineering, writing, and artwork alone do not consume musician appearances.
Distinct credited aliases and side projects remain eligible; canonical aliases
retain the same musician identity. Private, source-bound override evidence handles
the user's explicitly identified related performer. Group membership does not
create inferred recording credits. Joint credits without detailed familiar
performance evidence or reviewed collaboration evidence remain pending review.

The full-input registry preserves all 425 submitted normalized artist names and
their original source lines, including unmatched favorites. Six primary-artist
IDs are backed by the nine automatically accepted recording snapshots. This is
not independently audited resolution of all input acts; differently named or
ambiguous identities among unmatched rows remain a coverage limitation.

Applying these rules to the original graph selects eight songs and reports a
shortfall of two. The broader collection in
`data/private/song_graph_discovery_2026-10-07/` explores all twelve eligible
contributors by balanced favorite-artist allocation, admits 44 eligible candidates
alongside the same nine favorites, and uses 117 of 120 permitted HTTP attempts with
zero failures. Per-contributor audit entries record 255 familiar-act exclusions
and 17 collaboration-review exclusions; these are route occurrences and may repeat
recording IDs across contributors, not counts of distinct songs.

The weighted, equal, no-saturation, and contributor-diversity methods each return
ten songs with one familiar collaboration and zero repeated observed musicians.
The weighted list contains 31 distinct observed musicians. Its largest explanatory
contributor supplies about 21.9% of base-score evidence, compared with about 64.0%
on the eight-song old-graph list under the same hard rules. The pools differ, so
this is a collection/concentration diagnostic, not a controlled preference result.
The optional contributor-diversity method swaps two positions and retains the same
weighted-list membership; it remains opt-in rather than being presented as a
quality improvement.

Each `recommendations_*.json` retains base affinities, apportioned contributor
evidence, selection adjustments, observed musician sets, eligibility, and skipped
candidates. `SONG_REVIEW_weighted.md` and the corresponding comparison review files
provide source links for listening and credit inspection. Independent identity
and listening review remain pending.

Offline replay reproduces the sample fingerprint, snapshots, source hashes,
registry checksum, collection selections, and resulting recommendations with
zero network requests. The CLI agrees with the Python API. Evaluation now rejects
overlapping primary-artist holdouts and requires training-only registry provenance
in research mode; raw ranking metrics and constrained-list metrics are separate.
Only the public fixture evaluation has run, with its demonstration label.

Validation: 100 offline tests pass. New cases cover full-input exclusions through
a partial matching batch, source-bound registries and overrides, canonical alias
identity, side projects, the global collaboration allowance, group/member-only
credits, sampled and ambiguous performances, session/vocal/guest uniqueness,
recurring nonperforming staff, deterministic shortfalls, contributor diversity,
balanced collection, rejection refill, and training-only evaluation provenance.
The final selected list independently counts repeated musicians and rejects any
policy invariant violation. `git diff --check` passes; private source and generated
artifacts remain ignored.

## Milestone 4b: contributor uniqueness and automatic Apple lookup, 2026-10-07

D-020 now limits every shared explanatory contributor to one selected song per
batch. Selecting a song reserves all its connecting contributor IDs, across roles
and favorites. Nonconnecting staff are unaffected. Existing musician uniqueness,
unfamiliar-act exclusions, and the single global collaboration allowance remain.
Base affinity scores and weights are unchanged; the old soft-diversity option is
accepted but redundant under the hard cap.

The new Apple checker queries the complete eligible candidate pool using free
German (`DE`) song searches. A candidate needs compatible artist/title/version
metadata, a known duration within the fixed two-second tolerance, and an explicit
boolean `isStreamable=true`. Studio remasters and alternate album appearances are
permitted. Unresolved matches are skipped automatically, without requiring manual
availability confirmation. No developer membership was purchased or required.

The first bounded run made 60 HTTP attempts, saved partial results, and exited with
status 2 because one query exceeded the request budget. A second bounded run reused
the saved responses and made one new request, completing the pool without failures.
The completed snapshot is in `data/private/apple_availability_complete_2026-10-07/`:

| Automatic check result | Candidate recordings |
| --- | ---: |
| Qualifying API-indicated streaming match | 15 |
| No confident metadata match | 26 |
| Search-result cap reached | 3 |
| Total eligible pool | 44 |

The 29 excluded candidates are not established as absent from Apple Music. Search
coverage, credited-artist formatting, version context, missing metadata, and the
conservative duration rule can prevent a match. A capped search cannot establish
that the inspected release is the only compatible identity. The public streaming
flag is observed in live responses but absent from Apple's documented response-key
table; missing or nonboolean flags fail closed. No guaranteed playback or independently
audited audio identity is claimed. [Apple search API](https://performance-partners.apple.com/search-api).

All four methods use the same constraints and availability snapshot:

| Method | Strict graph-only batch | Apple-filtered batch | Apple-filtered shortfall |
| --- | ---: | ---: | ---: |
| Weighted saturation | 7 | 2 | 8 |
| Equal weights | 7 | 3 | 7 |
| Weighted without saturation | 7 | 2 | 8 |
| Weighted contributor diversity | 7 | 2 | 8 |

The weighted batch contains H. Hawkline's **Plastic Man** and Sega Bodega's
**Adulter8**. It has ten distinct observed musicians, four distinct explanatory
contributors, zero repeated musicians or explanatory contributors, and one familiar
collaboration. Its skipped-candidate counts are 29 availability exclusions, nine
musician conflicts, and four further familiar-collaboration conflicts. These reasons
use a deterministic precedence, so a candidate can also conflict with another rule.
The equal-weight batch contains Feel Good, Rainy Summer, and Herbie. Greedy selection
can return fewer songs than another ordering; no scores or hard constraints were
changed to fill the list.

Artifacts are in `data/private/apple_batch_complete_2026-10-07/`: four recommendation
JSON files, corresponding source-linked Markdown reviews, `playlist_preparation.json`,
and `verification.json`. The playlist file preserves batch order, iTunes IDs,
listening URLs, and lookup dates. Verified Apple Music catalog IDs remain null;
no playlist has been created in an Apple account.

Validation: **129 offline tests pass**, including conservative matching, remaster
suffixes, incompatible versions, duration boundaries, explicit/clean ambiguity,
misleading results, true/false/missing streaming flags, cache corruption, partial
budgets, complete CLI replay, country/dataset binding, contributor conflicts across
roles/favorites, multiple connectors, batch resets, replacement selection, and
available equivalent appearances in evaluation. All four real selected lists and
their exact metadata matches reproduce from cache with zero network requests;
the real ranking CLI agrees with the Python API. Independent checks confirm score
contribution sums, performer uniqueness, contributor uniqueness, and the collaboration
allowance. Evaluation retains raw graph reachability and adds availability-reachable
denominators; no private favorites holdout or listening-quality study has been run.

The initial timestamp audit found that request preparation could shorten logged
send spacing by about 20 milliseconds despite the pacing marker. The shared client
now records its send boundary after preparing the request. A regression simulates
slow preparation, and two further bounded live probes observed 3.100916 seconds
between logged sends. Source responses and generated private artifacts remain
ignored by Git. This result motivates broader candidate coverage before expecting
ten-song batches, while preserving the accepted scoring and hard policies.
