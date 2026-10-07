# Decision log

These decisions cover Milestones 1–2 of `plan.md` and the approved favorites input.
Research results remain pending; matching and evaluation remain later milestones.

## D-001: Recording co-credits define an edge

Date: 2026-10-06
Status: accepted

Question: What relationship does the graph represent?

Options considered: Recording co-credits; inferred personal collaborations; group membership.

Choice: Join distinct MusicBrainz artist IDs with eligible credits on one recording. Preserve the recording and roles. Say “both credited on [recording]” in explanations. A group remains its own entity; do not expand its membership.

Evidence or assumption: MusicBrainz distinguishes artists, recording artist credits, and recording relationships. Co-crediting does not establish that artists met or directly worked together.

Consequence: Every edge is auditable, but is a limited signal of musical association.

How to check it: Trace every edge to a recording and eligible roles; test that membership alone never creates an edge.

## D-002: Use an explicit recording-role allowlist

Date: 2026-10-06
Status: accepted

Question: Which credits are eligible?

Options considered: All relationships; performers only; primary recording artists plus selected performance and production roles.

Choice: Include primary recording artists and recording-level performer, instrument, vocal, producer, mix, engineer, audio, sound, and recording-engineer relationship IDs. Exclude executive attributes, release-only credits, work-level writing, and every other relationship. Keep exclusions with reasons.

Evidence or assumption: Definitions and IDs come from https://musicbrainz.org/relationships/artist-recording. These roles are a starting rule, not evidence of preference relevance.

Consequence: Coverage is deliberately bounded; composers, arrangers, and mastering credits do not enter the main graph.

How to check it: Audit source relationships and test the allowlist, executive attributes, relationship levels, and unknown types.

## D-003: Deduplicate evidence without removing dense recordings

Date: 2026-10-06
Status: accepted

Question: How should duplicate credits and dense recordings affect evidence?

Options considered: Count every role; cap recording size; retain all recordings and deduplicate artist-pair evidence per recording.

Choice: One edge contribution per artist pair and recording, retaining all distinct roles and attributes. Merge repeated recording IDs. Do not use a density threshold; report eligible artists per recording, edge counts, and artist degrees.

Evidence or assumption: Multiple roles and duplicated input rows are not independent recordings. No measured evidence justifies a size cutoff.

Consequence: Dense recordings still create cliques and may dominate results.

How to check it: Duplicate rows, roles, and recording objects must leave scores unchanged; inspect dense-recording statistics.

## D-004: Direct evidence plus capped two-hop recording pairs

Date: 2026-10-06
Status: accepted

Question: How are recommendation scores counted?

Options considered: Direct evidence only; count every intermediary path; count each unordered recording pair once per seed and candidate.

Choice: Direct score is the count of distinct seed–candidate–recording contributions. Two-hop score adds one per seed–candidate–unordered pair of distinct recordings with a valid intermediary. Three artist IDs must be distinct; intermediaries cannot be seeds. Retain all qualifying paths in the single contribution. Exclude seed candidates. Sort by descending score, case-insensitive name, then artist ID.

Evidence or assumption: The user chose counting once per recording pair to limit amplification by multiple intermediaries. Distinct seeds supply separate contributions.

Consequence: Scores are hand-checkable evidence counts, not probabilities. Directly connected candidates can also gain two-hop evidence. Multiple paths through the same recording pair do not increase its score.

How to check it: Compare all fixture scores with independent arithmetic; verify contribution sums, path validity, and invariance to duplicate seeds and rows.

## D-005: Equal weights; defer degree penalties

Date: 2026-10-06
Status: accepted

Question: Are role weights or intermediary penalties justified now?

Options considered: Tuned role weights; inverse-degree penalties; equal weights without penalties.

Choice: Use unit evidence weights in Milestone 1. Report degrees and density. Defer penalty experiments and role weighting to later comparative evaluation.

Evidence or assumption: The fixture verifies arithmetic, not predictive quality; tuning to these examples would be unjustified.

Consequence: Prolific intermediaries remain influential, transparently.

How to check it: Later compare equal weights and degree penalties using the same graph, candidates, seeds, and fixed splits.

## D-006: Defer matching; never force ambiguous identities

Date: 2026-10-06
Status: accepted

Question: How should ambiguous favorite-song matches be handled?

Options considered: Choose the highest search result; require conservative acceptance and manual review.

Choice: Matching is outside Milestone 1. Preserve original artist/title text during the requested local conversion. Future ambiguous recording matches remain unresolved for review; only accepted recording identities may supply primary-artist seeds.

Evidence or assumption: Artist and title text alone may omit recording version, album, or identity information.

Consequence: JSON conversion does not create MusicBrainz matches or graph seeds.

How to check it: Inspect ambiguous conversion rows now; audit precision and coverage of future accepted matches separately.

## D-007: Defer evaluation; hold out complete artists

Date: 2026-10-06
Status: accepted

Question: What will an honest evaluation require?

Options considered: Random track holdout; complete-artist holdout.

Choice: Evaluation is outside Milestone 1. Later hold out complete artists and all their input tracks, using fixed splits shared across methods. Report overall and reachable Recall@10/20 with counts; protect final test splits from tuning. Call small-data evaluation exploratory when separate validation/test sets are impractical.

Evidence or assumption: Track holdout can leak the same artist through another saved track. A single favorites list remains a one-person case study.

Consequence: No predictive metric is reported from the fixture.

How to check it: Later test disjoint held-out and seed artist IDs and inspect split provenance and coverage counts.

## D-008: Favorites replace the delayed Spotify export

Date: 2026-10-06
Status: revised

Question: Must the project wait for the Spotify export?

Options considered: Wait for the full export; use copied favorites only for a demo; use copied favorites as the study input.

Choice: The user selected favorites as the eventual input, one “Artist — Song” entry per line. Convert the supplied file locally to private JSON, preserving original lines and reviewable ambiguities. Preserve `plan.md`; this decision documents the approved input change.

Revision on 2026-10-06: The supplied `copied_favorite_songs.txt` actually contains 1,316 tab-separated rows, all with eight columns: title, an unlabeled column, duration, artist, album, genre, and two unlabeled columns. Accept this observed format as well as the originally planned format. Preserve all eight source columns and original lines. Do not interpret unlabeled numeric columns or split artist text such as “Artist A & Artist B” into identities.

Evidence or assumption: Explicit user preference plus inspection of the actual file. All 1,316 rows have nonempty title/artist and a duration matching minutes:seconds. The copied list may be a selected subset rather than a full saved library; its source application has not been established.

Consequence: The final claim concerns recovery from this person's selected favorites. Private text, converted JSON, exports, and downloaded caches stay outside Git. Milestone 1 proceeds independently of the file's arrival.

How to check it: Confirm preservation of source rows and Git ignore coverage; identify the actual sampling basis in later reports.

## D-009: A small frozen source-backed fixture

Date: 2026-10-06
Status: accepted

Question: What data and storage are sufficient for Milestone 1?

Options considered: Fictional credits; broad MusicBrainz sampling; four verified public recording snapshots.

Choice: Freeze Get Back and Don't Let Me Down (original mono), While My Guitar Gently Weeps (original mono), and Tears in Heaven (studio), with full eligible credits and source provenance. Use JSON and in-memory Python structures, with a fixed Beatles demo seed. Do not build an API crawler, matcher, database, web interface, or evaluation pipeline.

Evidence or assumption: The user requested verified credits. Planning arithmetic predicts 20 graph artists, 96 distinct edges, and 132 recording-backed edge contributions; verify fresh source responses before accepting these expectations.

Consequence: A small offline demo is reproducible but deliberately selected and unsuitable for performance claims.

How to check it: Manually inspect the snapshot against recording pages, compare counts and scores with independent expectations, and run tests without network access.

## D-010: Fix a favorites-based pilot before fetching

Date: 2026-10-06
Status: accepted

Question: Which seeds and collection bounds should the first real-data sample use?

Options considered: Extend the Beatles fixture; hand-pick well-connected favorites; use the three most frequent exact artist-text entries in the local favorites.

Choice: Use Unknown Mortal Orchestra (`e2305342-0bde-4a2c-aed0-4b88694834de`), Cate Le Bon (`f2393e49-b791-46da-a6d7-1e9e60743405`), and Kendrick Lamar (`381086ea-f511-4aba-bdf9-71c753dc5077`). Agent inspection of the artist pages confirmed group/person identity and discography; independent human identity review remains pending. Store the selection locally, with its source hash and identity-check notes. No individual favorite song is matched. Fetch the first browse page of at most eight primary-credit recordings per seed in MusicBrainz's returned order. Do not filter live recordings, mixes, or collaborations to improve the result. Select up to two nonseed intermediaries per seed by distinct shared seed-recording count, descending, breaking ties by MBID. Expand that fixed frontier once, in MBID order, with up to six previously uncollected recordings per intermediary, chosen by ascending MBID from eligible recording relationships plus one first browse page (limit six). Maximum depth is two artist edges; there is no recursive frontier. At most 60 recording lookups, nine artist lookups, and nine browse calls before retries; cap all HTTP attempts at 100. Use 1.1 seconds between request starts, a 20-second timeout, a 16 MiB response bound, and at most one retry for transient errors.

Evidence or assumption: The three names are most frequent in the observed private input; frequency is a sampling rule, not a preference-strength estimate. IDs were inspected at https://musicbrainz.org/artist/e2305342-0bde-4a2c-aed0-4b88694834de, https://musicbrainz.org/artist/f2393e49-b791-46da-a6d7-1e9e60743405, and https://musicbrainz.org/artist/381086ea-f511-4aba-bdf9-71c753dc5077 before collection. No API sample has yet been inspected when this decision is written.

Consequence: Initial results depend on MusicBrainz ordering, recording versions, and intermediary selection. Prolific producers may dominate. The sample cannot estimate recall or comprehensive favorites coverage. Report sparse or disappointing coverage before changing bounds or considering a dump.

How to check it: Freeze seeds, parameters, frontier evidence, browse totals/offsets, selected and omitted IDs, retrieval timestamps, and failures in the manifest. Compare seed-only and expanded graph reachability, then inspect several paths and excluded credits with the user.

## D-011: Relationship-aware collection and immutable offline snapshots

Date: 2026-10-06
Status: accepted

Question: How can a small API sample discover two-hop evidence reproducibly?

Options considered: Primary-credit browse only; full dump; explicitly fetch artist recording relationships and recording-level credits using a bounded local cache.

Choice: Browse supplies primary-credit recordings; artist lookups explicitly include `recording-rels` to find eligible performance/production recordings for selected intermediaries. Artist relationship lists have no paging interface; record returned counts without claiming completeness. Recording lookups include `artist-credits+artist-rels+work-rels+work-level-rels`, so work-artist exclusions can be inspected separately. Release credits and group membership are never promoted. Cache raw response text in version-1 URL-keyed JSON envelopes with timestamps, hashes, status, and attempt history, including failures. Reuse successful and failed responses; retry cached failures only when explicitly requested. Offline runs never use network. Save frozen recording snapshots, rule configuration, source hashes, collection coverage, diagnostics, both rankings, and a review sheet under ignored `data/private/`. Refuse to overwrite a saved sample. Keep contact information in ignored local metadata and require a real contact email or URL for live HTTP requests. Serialize collection per cache directory and persist request timing across runs.

Evidence or assumption: MusicBrainz documents artist credits and relationships separately, browse limits, and identification/rate constraints at https://musicbrainz.org/doc/MusicBrainz_API and https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting. A cache freezes a retrieval, not the whole changing database.

Consequence: Offline reruns preserve observed data and scores; failures and truncation remain visible. The Linux collector uses only Python's standard library. Users must coordinate other applications sharing the same IP. Graph artist entities, including engineers/producers, remain candidates under D-002; inspect them before considering new candidate rules.

How to check it: Test with synthetic API responses: production-only intermediary expansion, bounded pages and frontier, retry/rate/budget behavior, corrupt-cache rejection, failure preservation, and network-disabled replay. Verify frozen-source hashes and contribution sums. Mark human source review pending until actually performed.

Pilot observation on 2026-10-06: The fixed bounds yielded 60 recordings and 85 additional reachable candidates in 78 API attempts without collection failures. Nine identified recording-page review attempts remained within the same 100-attempt cap, but all returned browser verification; page inspection and independent human review remain pending. Offline replay used zero requests and reproduced both rankings. See `reports/results.md` for recording-version inflation, technical candidates, and first-page coverage; no collection or modeling rule was changed in response to these findings.
