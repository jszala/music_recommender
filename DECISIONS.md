# Decision log

These decisions cover Milestones 1–2 of `plan.md`, the approved favorites input,
and the user's clarified song-recommendation direction. D-001–D-011 describe the
historical artist baselines. D-012–D-017 record the song implementation and remaining
identity, credit-coverage, weighting, and evaluation questions.
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

## D-012: Recommend songs using credits, with bounded preference impact

Date: 2026-10-07
Status: accepted direction; initial implementation in D-015–D-017, further validation pending

Question: What should the listener receive, and how should repeated favorites and different roles affect recommendations?

Options considered: Continue recommending artist entities; recommend recordings using their credited contributors as connections.

Choice: The user clarified that the intended output is song recommendations. Every credit should matter to some extent, including engineering credits that may be relevant to a preferred sound. Recording staff should have lower impact than songwriting, production, and musical performance. Preserve credit roles and provenance, including work-level songwriting and the scope of any release-level credits; do not silently treat them all as recording-level facts. The influence of many favorites from one artist should saturate so whole albums do not overwhelm other interests.

Clarification on 2026-10-07: Song recommendation is the primary focus. All musicians receive the same base weight; a musician who is also a songwriter receives a separate, additive songwriting contribution. Do not introduce a "central musician" category or infer importance from billing, fame, lead/guest labels, or group membership. Repeated copies of the same credit or multiple instruments must not manufacture additional role contributions. Keep the observed credits as the basis of explanations without requiring the user to identify which sound or contributor they like. Numerical role weights, production/staff mapping, and the saturation function remain pending. The user explicitly authorized proceeding, so `plan.md` is revised to this direction; the preservation instruction in D-008 referred to the earlier input-format substitution.

Evidence or assumption: Explicit user direction. Credit metadata can establish an association, but does not identify who caused a particular snare sound or establish that a chosen role hierarchy predicts preference. D-016 supplies fixed provisional weights and saturation; their empirical justification, missing-role treatment, and broad credit eligibility remain unresolved.

Consequence: The original artist rankings remain documented baselines. Milestone 3 retains accepted recording identities, source album/version information, ambiguity, and contributor provenance rather than reducing matches to primary-artist IDs alone. A graph retaining recordings and contributor-credit edges is now implemented. Evaluation must distinguish new songs by familiar artists from discovery of unfamiliar artists; complete-artist holdout measures only the latter. Saturating saved-artist evidence is separate from penalizing prolific contributors and from diversifying the final recommendation list.

How to check it: Before full matching, inspect a small set of favorite recordings for performer, producer, songwriting, and engineering coverage. Use hand-checkable song examples, including an engineering-only connection, and record unsupported or ambiguous roles. Later compare equal and hierarchical weights on the same recording candidates and fixed splits. Verify that duplicate input does not increase preference strength and that many favorites from one artist have bounded aggregate influence. Specific numerical choices and evaluation splits are not accepted by this entry.

## D-013: Recording identity and version evidence remain an open problem

Date: 2026-10-07
Status: open

Question: Which appearances or versions should share recommendation identity or evidence?

Options considered: Count every recording MBID independently; collapse by title or work; preserve version identities while separately controlling repeated evidence.

User requirements: Reappearances of the same recording on compilations or deluxe editions, and remasters without a new performance, mix, or edit, should not become independent tracks. Live performances and remixes should remain distinct recommendation candidates. Mono/original mixes require care because the mix itself may be part of the listener's preference. Automatic equivalence detection is expected to be difficult; uncertain cases must remain reviewable.

Evidence or assumption: The pilot gives The Alchemist nine points from three versions of 1 Train paired with three expanded recordings. MusicBrainz models a recording separately from its release-track appearances, and copying/mastering alone does not create a recording; distinct performances and mixes generally do. See https://musicbrainz.org/doc/Recording and https://musicbrainz.org/doc/Style/Recording. Database duplication and incomplete version metadata can still defeat ID-based deduplication.

Consequence: The current implementation merges identical recording IDs but does not detect equivalent audio under different IDs. Candidate identity and independence of preference evidence need separate policies: distinct mixes can remain available without necessarily counting as independent signals of artist preference. Do not merge on title alone or on a shared work, which can also join covers, live performances, and remixes. Clean/explicit edits, cross-ID duplicates, mono/stereo variants, and any grouping of recording families remain unresolved.

How to check it: Retain exact IDs, album context, durations, disambiguation, and available version relationships. Audit examples of a compilation reappearance, remaster, live recording, remix, mono/stereo mix, and clean/explicit edit. Document which equivalences are established, proposed, or unknown. Preserve exact candidates and original evidence even if later aggregation reduces repeated influence. No automatic version grouping or scoring change is implemented by this entry.

## D-014: Prepare a small recording-matching review before bulk collection

Date: 2026-10-07
Status: accepted workflow; identities and human audit pending

Question: What concrete first step can validate the song-matching workflow with available data?

Options considered: Match all 1,316 favorites immediately; prepare a small review batch using cached candidates plus broader artist coverage.

Choice: Prepare 20 favorite rows locally: all five rows with case-insensitive, whitespace-normalized artist/title candidates in the frozen Milestone 2 recording sample, then 15 rows from distinct remaining artist texts spaced evenly across their sorted names, taking each artist's first source row. Match against primary artist-credit names and joined artist-credit text only. Preserve the input hash, source row numbers, selection method, cached candidate IDs and hashes, album/duration context, recording versions, observed recording/work credits, and review fields under ignored `data/private/matching_audit_2026-10-07/`. Refuse to overwrite the batch. Text overlap proposes candidates, not accepted identities. Rows without cached candidates are not searched, not declared unmatched. This preparation makes zero API requests.

Evidence or assumption: Local inspection found 1,316 favorite rows, all with album and duration context; five have artist/title candidates among the 60 pilot recordings, and two of those five have multiple recording IDs. These are workflow diagnostics, not matching precision, identity verification, or preference-quality measurements.

Consequence: The first review exposes candidate ambiguity before a conservative cached matcher is implemented. The batch is deliberately mixed and is not a representative precision audit; a later approximately 100-match audit needs its own documented sampling rule. Live search/lookup batches require declared request bounds and preserved query provenance before collection. Keep the original fixture and pilot unchanged.

How to check it: Verify unique selected source rows and the 5+15 selection, source hashes, candidate title/artist checks, retained roles and work scope, and zero network use. Human identity review and broader candidate search remain pending; none of the 20 rows is automatically accepted by preparation.

## D-015: Conservative recording matches and a bounded first live batch

Date: 2026-10-07
Status: accepted implementation policy; independent identity review pending

Question: How should the matcher collect candidates without silently accepting ambiguous versions?

Choice: Search literal artist/title phrases, page up to two 25-result pages, deduplicate recording MBIDs, and look up at most four candidates per song. Prioritize exact title/combined artist, matching album, and duration proximity; search scores never establish acceptance. Automatic acceptance requires one qualifying recording, exact normalized title and combined artist credit, an observed matching album release, duration within 2 seconds, no unresolved version markers, complete declared search, and inspection of every returned exact artist/title candidate. Retain all alternatives and reasons. The 2-second allowance accommodates rounded input durations and is a fixed conservative starting rule, not a tuned confidence probability. Human overrides require a known fetched candidate, reviewer, evidence, and a matching input hash. Independent human audit is distinct from rule-based acceptance.

Collection: Use the existing URL-keyed client and cache, identifying contact file, 1.1-second pacing, 20-second timeout, 16 MiB response limit, one transient retry, and at most 120 HTTP attempts for the initial 20-song batch, including retries. Recording lookups include artist credits, recording/work relationships, linked releases, and ISRCs. Album absence in a limited linked-release list is unknown rather than a confirmed mismatch. Save exact queries, response/snapshot hashes, selection, failures, truncation, match reasons, observed credits, profile, and review template in a new ignored directory. Offline replay never uses network. Budget exhaustion or incomplete lookups preserve partial output and cannot auto-accept affected rows. Do not expand live collection to all favorites until the initial audit is reviewed.

Credit handling: Preserve all observed artist-credit relationships and their recording/work scope. Classify known performer, producer, staff, and songwriting relationship IDs separately for coverage and later scoring; retain unknown, executive, and nonmusical relationships with explicit reasons rather than promoting them. No release-level credits or band members are inferred. Duplicate accepted recording IDs contribute one favorite identity while preserving every original source row.

How to check it: Synthetic HTTP tests must cover wrong artists, versions, album/duration evidence, multiple qualifying IDs, paging and lookup truncation, budget/cache failures, immutable outputs, bound manual reviews, duplicate source rows, work-role provenance, and network-disabled replay. The first live batch measures observed match and credit counts; neither automatic acceptance nor tests establish independently audited precision or listening quality.

## D-016: A hand-checkable song-ranking foundation

Date: 2026-10-07
Status: provisional fixed baseline; empirical comparison and user review pending

Choice: Retain recordings connected to contributor entities through observed credit rows. Each contributor has at most one contribution from each distinct role category per recording: musician, songwriter, producer, and staff. All musicians have weight 1, songwriting adds 1, production adds 1, and staff adds 0.25 as an explicit initial lower-weight setting. An equal-weight comparator gives every category weight 1. Numerical ratios are assumptions, not learned importance. Unknown and executive roles remain preserved and reported, with their scoring mapping unresolved; release credits and group membership are not inferred.

Scoring: For each favorite/candidate recording pair, sum the products of the shared contributors' additive role weights. Transform the sum x to x/(1+x) to bound pair affinity while preserving the effect of additional distinct roles. Within each primary favorite-artist group, average pair affinities over distinct favorite recording IDs, then multiply by n/(n+5), where n is the group's distinct favorite-recording count. Five is a fixed illustrative half-saturation parameter, not a tuned result. A no-saturation comparator multiplies by n instead, exposing linear accumulation. Multi-primary recordings contribute to each named artist group and are reported; no band membership is expanded. Keep complete source credits and each transformation in score contributions so their sum reproduces the final score.

Identity and validation: Exclude favorite recording IDs from suggestions, deduplicate repeated rows and credits, retain separate live/remix IDs, and flag unresolved cross-ID equivalence. On a public fixture and synthetic records, verify equal musician treatment, additive songwriting, engineering-only connections, contribution sums, duplicate invariance, deterministic results, and bounded total influence per favorite artist. Provide offline recording-holdout comparison for explicitly declared, fixed splits, keeping established equivalent identities together. Require retrieval provenance binding collection to training favorites for research evaluation; otherwise label outputs demonstration diagnostics. Do not claim recommendation quality from the existing pilot, test fixture, or unreviewed matches. Final-list diversity and contributor-degree penalties remain separate later work.

## D-017: Collect song candidates around accepted favorite recordings

Date: 2026-10-07
Status: bounded collection policy; coverage and identity audit pending

Choice: Copy only selected accepted favorite snapshots into a new dataset. Select up to six contributors by distinct selected-favorite recording count, descending, breaking ties by artist MBID. Use all mapped musician, songwriter, producer, and staff categories as eligible frontier evidence, preserving omitted contributors. Query selected artists with recording and work relationships, browse up to two primary-credit pages of 25 recordings, and inspect up to two eligible songwriting works in MBID order for their recording relationships. Fetch at most six new recording IDs per contributor from the union, in MBID order, without recursive expansion. Do not infer band members or treat release staff as track-level credits.

Collection: At most 120 paced HTTP attempts per run, including retries, using the same cache and identification constraints. Freeze snapshots, response hashes, selected/omitted recording and work IDs, page offsets/totals, failures, and training favorite-recording IDs. A --favorite subset permits collection from training preferences alone for a later fixed evaluation split. A profile binds favorites to source snapshots; independently audited identity remains a separate status. This bounded convenience sample does not certify a full neighborhood, and prolific contributors or first-page ordering can affect discovery.

How to check it: Synthetic transports must show candidates discovered through engineering-only and songwriting-only relationships, pagination and caps, preserved training provenance, checksum-backed snapshots, partial failures, and zero-request offline replay. Candidate metadata may describe held-out recordings when independently encountered; held-out favorite membership must not guide contributor or recording selection.

## D-018: Recommend unfamiliar acts and enforce diversity across the list

Date: 2026-10-07
Status: implemented; independent identity and listening review pending

Problem: Artist saturation bounds a favorite artist's contribution to each candidate score, but cannot prevent familiar acts or repeated musicians from filling the list. Candidate collection currently prioritizes raw favorite counts, independently of saturation. The first listening review identified this as a failure of the discovery objective.

Required policy: Ordinary suggestions must not be by an act submitted anywhere in the original favorites input, including rows whose recording match remains unresolved. Distinct credited aliases and side projects are allowed exceptions. Spelling and capitalization differences alone do not establish a distinct act. A genuine collaboration with a familiar act or an explicitly identified related performer is an exception, with a hard maximum of one such song across the entire recommendation list. The user confirmed this is a global allowance, rather than one per favorite artist. A group and its own member do not establish an unfamiliar collaborating act merely by having separate credit IDs.

Musician uniqueness: Each observed active musician may appear in at most one selected recording. Count primary artist credits as the existing conservative performance proxy, plus recording-level performer, instrument, and vocal credits. Multiple roles on the same recording consume one appearance. Songwriting, production, engineering, artwork, and other nonperformance roles alone do not consume this allowance. A musician who also produces still consumes it. True aliases retain the same performer identity for this check; distinct bands are not automatically merged with their members or side projects. Missing credits remain a stated coverage limitation, rather than evidence that a musician was absent.

Consequences: Keep eligibility, credit scoring, and complete-list selection separate. Carry a source-bound registry of submitted acts, distinct-alias exceptions, and explicitly identified familiar collaborators. Balance candidate collection across favorite-artist groups and refill after eligibility checks within a declared request budget. Keep the existing preference saturation as one component; plan a separate soft reduction of repeated explanatory contributor evidence across the selected list, without imposing a one-song restriction on engineers or producers. Return fewer songs with an explicit shortfall rather than relaxing a hard rule.

Evaluation: Compare methods under identical discovery and list constraints, using complete-artist holdouts as the main saved-song recovery task. Derive each fold's exclusion registry only from training input. Report raw-score recovery separately from constrained-list recovery, graph coverage, policy eligibility, contributor concentration, and list length. Historical recording-holdout diagnostics retain their historical policy label.

Implementation sequence and acceptance cases: See `reports/recommendation_policy_plan.md`. This decision supersedes the familiar-artist eligibility and deferred list-diversity portions of D-012/D-016 and the raw-count collection priority in D-017. Their descriptions document the earlier implementation; D-019 records the new implementation.

## D-019: Separate discovery eligibility, scoring, and constrained list selection

Date: 2026-10-07
Status: implemented foundation; soft diversity is a provisional opt-in comparison

Identity: New matching profiles retain normalized names and source lines from the entire submitted input before selecting a matching batch. Recording-backed primary IDs augment these names; unresolved recording rows still supply exclusions. The input hash and a registry checksum bind names, IDs, and evidence to profiles and collection manifests. Older personal profiles require the original --input file. Private, hash-bound policy overrides record distinct credited aliases, explicitly related performers, group/member pairs, and reviewed collaborations, each with evidence. Group membership does not establish performance. Known members alone cannot turn their own band's song into an unfamiliar-act collaboration.

Eligibility: Familiar primary acts are rejected unless a distinct alias exception applies or an unfamiliar primary act participates in a supported collaboration. Familiar guest performers also invoke the one global collaboration allowance. A collaboration requires detailed familiar-performer evidence or an explicit reviewed decision; joint primary credits alone and ambiguous mashup/sample routes need review. Familiar artists credited only as nonperforming producers or staff remain permitted connections. Never infer missing performers or creative importance.

Selection: Keep the existing role weights, per-pair bounded affinity, and per-input-artist saturation unchanged. score_song_candidates exposes raw evidence for diagnostics; the public recommend_songs API and CLI apply eligibility and deterministic greedy selection. Each selected song consumes all its observed primary/performance musician IDs and, where applicable, the one global collaboration allowance. Positive-score candidates only; export skip reasons and shortfalls instead of relaxing hard constraints. Greedy selection is not an optimizer for maximum list size or total affinity.

Soft comparison: Apportion each pair contribution among shared contributors in proportion to their raw weight products. --diversity contributors divides each contributor's apportioned evidence by 1 plus its number of previous selected-song appearances, recomputing after every pick. All contributor evidence remains positive. Store base affinities, contributor allocations, multipliers, and selection scores separately. The default keeps this adjustment off: the first real comparison changes order but not list membership, which does not justify a listening-quality claim or parameter tuning.

Collection: Allocate up to twelve contributors round-robin across favorite primary-artist groups, preferring contributors outside the input acts' own discographies within each group. Admit at most six eligible recordings per contributor from two browse pages and up to two linked songwriting works, permitting eighteen detail lookups per contributor to refill after rejection. Alternate detail lookups across contributors. Keep the existing overall cap of 120 paced HTTP attempts. Preserve exclusions with source queries, cache references, and hashes; omissions and per-contributor shortfalls remain visible. --favorite subsets rebuild the registry from their selected training recordings, while retaining the original input hash solely as source provenance.

Evaluation: Require disjoint primary artists as well as disjoint established recording identities. Compare equal weights, weighted saturation, weighted no-saturation, and weighted contributor diversity under identical hard policies. Separate raw-score metrics from final selected-list metrics and report policy-eligible reachability and list diagnostics. Research mode requires collection favorites and the complete registry to derive from the same training recordings; held-out names cannot guide exclusions. This remains a single-list case study with no measured listening usefulness.

Observed check: The original graph yields eight selected songs under the new policy. A broader 44-candidate graph from the same nine favorites yields ten songs with one familiar collaboration and no repeated observed musicians; offline replay reproduces its snapshots, registry, selections, and recommendations with zero requests. See `reports/results.md` for counts and remaining identity limitations.

## D-020: One song per shared contributor in each batch

Date: 2026-10-07
Status: implemented and checked in Milestone 4b

Choice: Every shared explanatory contributor identity may support at most one selected song per batch, across all favorite recordings and mapped roles. Selecting a song reserves every contributor in its score evidence. Preserve D-018's musician uniqueness, unfamiliar-act eligibility, and global collaboration allowance. Leave base scoring unchanged and return a documented shortfall instead of relaxing the cap. Allowances reset between batches; concentrated-input exceptions and recommendation-history exclusions are deferred.

Consequence: This supersedes D-018/D-019's permission for repeated explanatory nonperformers. A recurring staff credit that does not connect a candidate to a favorite does not consume the explanatory allowance. The existing soft-diversity option remains accepted for compatibility but cannot change a list under the hard cap. All evaluation methods use the same policy.

How to check it: Exercise conflicts across roles and favorites, songs with several connectors, replacement candidates, batch resets, and immutable base affinities.

## D-021: Automatic free Apple lookup before list selection

Date: 2026-10-07
Status: implemented; bounded live lookup and zero-network replay checked

Choice: Use Apple's free iTunes search API in Germany (DE), with song-only results and explicit content included. Require a conservative artist/title/version/duration match and an explicit boolean isStreamable=true. Accept alternate album appearances and identified studio remasters, retaining other version distinctions. Reuse the existing two-second duration tolerance as a fixed conservative assumption. Unknown identities, missing metadata or flags, failed requests, and exhausted budgets are skipped automatically; routine manual confirmation is not required.

Collection: At most two distinct artist/title queries per candidate, 50 results per query, 60 HTTP attempts including one possible transient retry, and at least 3.1 seconds between requests. Cache exact responses, timestamps, hashes, rules, country, and dataset fingerprints; preserve partial outputs and support zero-network replay. Availability filtering happens before list allowances are consumed. Preserve iTunes track IDs separately from any future verified Apple Music catalog IDs.

Evidence and limitations: Live German Apple search responses contain isStreamable flags, including matching Sega Bodega and Sweet Baboo recordings. This is API-indicated availability, not guaranteed account-specific playback or audited recording identity. The public field is absent from Apple's documented response-key table and can change; missing fields fail closed. No search result does not establish catalog absence. This user-authorized provider lookup is a narrow exception to the original plan's extra-source restriction; it supplies availability, not credit evidence or preference scores.

Later work: Export an ordered playlist preparation file now. Account authorization, developer membership, dedicated Apple Music catalog verification, and creating a playlist in the user's library remain later milestones. Source: https://performance-partners.apple.com/search-api and https://developer.apple.com/documentation/applemusicapi/create-a-new-library-playlist.

How to check it: Test conservative matching, remaster suffixes, incompatible versions, true/false/missing flags, partial failures, country/dataset binding, deterministic release choice, and cached replay; then run one bounded check against the existing candidate graph.

Observed check: The first run used 60 requests and left one query unfinished. A second bounded run reused those responses and made one new request. Of 44 eligible candidates, 15 have qualifying API-indicated streaming matches, 26 have no confident metadata match, and three hit the search-result cap. The weighted method selects two songs with zero repeated musicians or explanatory contributors and one familiar collaboration; the equal-weight method selects three. Complete matching decisions and all four selected lists replay with zero network requests. These are coverage and constraint checks, not listening-quality measurements.

## D-022: Full supplied-list processing before further evaluation

Date: 2026-10-07
Status: scope accepted; collector implemented under D-023, API scale-up cancelled under D-024

Question: Why does a 1,316-song input produce only two suggestions, and how should the project move beyond its nine-recording scoring pilot?

Choice: Plan Milestone 4c to attempt every row in the supplied favorites file, consolidate every confidently accepted recording and its observed credits into one profile, and collect candidates across that full profile's contributor frontier. Add resumable checkpoints and persistent request budgets; reuse verified pilot/cache evidence instead of repeating completed collection. Preserve D-015's conservative acceptance criteria, D-016 scoring, D-018 unfamiliar-act/musician rules, and D-020/D-021 contributor/Apple constraints. Account for uncertain rows automatically; routine per-song confirmation is not required.

Authorization: The user's request to plan full-list implementation supersedes D-015's initial pilot-review gate as a requirement for starting scale-up. Independent human identity auditing remains an unfulfilled research-validation requirement, not a reason to conceal or block automatic full-list collection. The subsequent request to implement Milestone 4c authorizes implementation and the planned bounded collection.

Evidence: All 1,316 imported rows and 425 normalized credited-artist strings inform current familiar-act exclusions, but positive scoring uses only nine accepted favorite recordings from twenty processed rows. The bounded graph has 44 eligible candidates through twelve routes; fifteen have confident Apple streaming matches and the weighted selector returns two. The imbalance between full-input exclusions and pilot-only preference evidence is a material limitation, not evidence that the user's library offers only two discoveries.

Planned limits: Keep 120-attempt MusicBrainz and 60-attempt Apple tranches, with proposed cumulative stage ceilings of 16,000 matching, 6,000 discovery, and 2,000 Apple attempts including retries. Retain minimum intervals of 1.1 and 3.1 seconds. Seek an initial pool of 500 eligible candidates and 100 explored contributor routes where available; all accepted favorites participate in scoring even when discovery remains bounded. These are planned limits/targets, not measured results or guaranteed output counts.

Consequence: Full-list coverage and resumability become the next milestone before holdout evaluation. Publish processed/accepted/unresolved input counts, observed credit coverage, explored/unexplored contributor routes, Apple outcomes, and final batch size separately. Actual playlist creation and paid Apple integration stay later. A ten-song batch remains the target, with honest shortfalls when the unchanged rules cannot supply it.

How to check it: Follow [the implementation plan](reports/full_library_implementation_plan.md), including interruption/resume, pilot import, duplicate/conflicting snapshots, persistent budgets, full-profile scoring, broad discovery, country/dataset rebinding, all hard constraints, and deterministic zero-network replay. Do not label matching complete while rows remain operationally unattempted or deferred.

## D-023: Durable full-library workflow and bounded continuation

Date: 2026-10-07
Status: implemented and tested; live full-list API approach discontinued under D-024

Choice: Use `src.process_library` with an exclusive job lock, atomic durable row
checkpoints, immutable dataset generations, and job-owned raw HTTP envelopes.
Charge every transport attempt before sending, including retries and interrupted
sends. Keep cumulative counters across resumes and automatically advance through
120/120/60-attempt tranches within the 16,000/6,000/2,000 stage ceilings. Bind the
job to the full input, rules, country, overrides, verified import fingerprints,
and cache policy. Freeze input and rule files inside the private job.

Matching: Schedule rows round-robin across normalized credited-artist strings;
reuse verified pilot decisions. Run the existing conservative matcher per row and
publish a deduplicated profile preserving all accepted source lines. Operational
failures stay separate from ambiguous and no-confident-match decisions. Explicit
failure retry permits two additional persisted matching passes. All attempts remain
subject to the same cumulative ceiling. Conflicting recording snapshots are errors.

Discovery: Maintain the full balanced contributor queue, relationship/work routes,
page offsets, rejected candidates, and unique recording snapshots. Seek one eligible
candidate per scheduled route before its next candidate, up to the declared bounds.
Recheck historical candidates against the expanded registry. Preserve partial graphs
when the discovery budget ends; selection may publish a smaller explicitly incomplete
batch. Failure retries replay frozen successful operations and preserve prior graph
and export generations.

Apple and output: Check every eligible positive-score candidate in the frozen graph,
checkpoint each completed check, retain raw response timestamps, and rebind availability
to that graph. Apply the existing selector unchanged across all four comparisons.
Save aggregate coverage separately from private source-linked reviews and playlist
preparation. A complete job can run a fresh automatic offline replay comparing
matching decisions, profiles, snapshots, all scores, selected order, and playlist
bytes. An incomplete stage cannot claim that verification.

Evidence: 152 offline tests pass, including a synthetic end-to-end multi-tranche job,
transport/row/publication interruptions, cumulative retry accounting, pilot import
and tamper rejection, snapshot conflicts, discovery paging/refill/breadth, partial
budgets, availability rebinding/raw reuse, active-job status, and exact offline replay.
The first additional 100 live rows took about 435 seconds and 320 attempts; that is
an observed matching-runtime sample, not a precision or listening-quality estimate.

Consequence: Full-list API collection is executable and resumable, but its scale-up
was cancelled under D-024. Completion and the final live batch remain outstanding;
retained partial coverage is in [the cancellation report](reports/full_library_run.md).

## D-024: Discontinue public API full-library collection

Date: 2026-10-07
Status: adopted at the user's request; active run and queued continuation cancelled

Question: Is the public MusicBrainz API a practical collection backend for processing
the full supplied library, exploring a broad credit graph, and repeating experiments?

Choice: Treat the public-API approach as **not feasible for this project's intended
full-library matching, broad discovery, and iteration speed**. Stop both the active
matching process and the queued discovery/Apple/export/replay continuation. Preserve
completed checkpoints, frozen responses, cumulative counters, caches, and pilot
outputs. Do not automatically restart the cancelled job. API access remains useful
for bounded pilots and cached regression/replay work.

Evidence: The first additional 100 rows took about 435 seconds and 320 HTTP attempts.
At cancellation, 538 rows had saved outcomes: 187 accepted recordings, 342 unresolved
rows, and nine HTTP 503 operational failures. One more row was interrupted and 777
were unattempted. The job charged 1,663 new MusicBrainz attempts, with the imported
pilot's 56 attempts recorded separately. Expanded discovery and Apple collection
had not started. The earlier estimate of another 2–4 hours for the full pipeline
was a projection; a completed total runtime was not measured.

Reasoning: Public-API rate limits, multiple searches and detail lookups per row,
and requests needed for new contributor neighborhoods impose an impractical serial
collection cost. Caching and resumability prevent repeated completed requests and
lost work, but they cannot remove the cost of collecting previously unseen data.
This is a project feasibility decision; the API successfully supported small pilots.

Next direction: Evaluate downloaded MusicBrainz data and local indexes for matching
and contributor queries. Preserve the conservative identity criteria, recording/work
credit scope, provenance, scoring, and hard list constraints, and validate the adapter
against frozen evidence before scale-up. Local download/import, index construction,
backend implementation, and runtime benchmarking remain future work. Apple availability
is a separate stage; a MusicBrainz dump does not provide it or fill missing credits.

How to check it: Both collection processes have exited, the job manifest marks matching
cancelled, and [the coverage report](reports/full_library_run.md) separates saved
outcomes, failures, interrupted work, and unattempted rows. No full-library recommendation
result or complete live offline replay is claimed. Milestone 4c remains incomplete
until the revised backend completes the original coverage and validation requirements.

## D-025: Fresh bounded recommendations before availability checking

Date: 2026-10-08
Status: implemented; runtime and coverage verification recorded in the benchmark report

Question: Can the portfolio prototype return an explainable list quickly using
fresh public API evidence and support reproducible seed experiments?

Choice: Keep the cancelled full-library experiment and its evidence. Defer a local
MusicBrainz dump. Provide a callable engine and sequential experiment runner over
the existing parsed favorites JSON. Sample eight artist groups by default, using
weights 1/2/3 for 1/2–10/>10 distinct songs and one uniformly chosen song per group.
Use stable ordering and a supplied random-number seed. These weights affect sampling
only. Each run starts with an empty response store and gets 35 HTTP attempts, a
55-second budget, at most 100 admitted candidates, and up to 15 recommendations.

Matching: One 25-result search page and one detail lookup per seed. Only uncapped,
unambiguous search results reach lookup; supplied recording MBIDs bypass searching.
Keep D-015 identity checks and skip unsuccessful seeds without replacement.
Discovery: One balanced contributor expansion round, one artist-relationship lookup
and artist browse page per contributor, and at most one songwriting-work route.
Use supported batched recording/work credits; individual lookups are bounded fallback.
Deduplicate requests and recordings within each run; save evidence and unexplored
coverage rather than claiming exhaustive discovery.

Selection: Keep existing base credit scores, complete-input familiar-act exclusions,
favorite-recording exclusions, observed performer uniqueness, and the one familiar
collaboration allowance. In this prototype, replace D-020's explanatory-contributor
cap with the existing diminishing contribution multiplier
`1 / (1 + previous selected appearances)`. Both base and selection scores remain
visible. D-020 remains the default in all historical workflows.

Availability: The user explicitly chose recommendations before Apple checking.
The standalone checker accepts a finished recommendation run and annotates only
selected songs, preserving membership, order, and the original export. Unknown
matches mean no confident Apple match; they do not establish catalog absence.
This separate operation has its own budget and does not supply recommendation scores.

Runtime: Charge every attempt before transport, disable retries, enforce request
timeouts no longer than five seconds or remaining collection time, respect backoff,
and preserve 1.1-second pacing across runs. A process supervisor ends collection
five seconds before the overall deadline, terminating stalled transport and using
completed snapshots for scoring/export. Under-60-second behavior must be measured;
the deadline does not guarantee 15 recommendations or better listening quality.

How to check it: Offline tests exercise sampling, identity ambiguity/caps/IDs,
full-input exclusions, nested work-credit batching, bounded fallback/deduplication,
soft penalties and strict compatibility, request accounting and spacing, budget
exhaustion, empty results, separately ordered Apple checks, and genuinely stalled
transport. Benchmark sequential fresh runs and preserve their JSON/CSV summaries;
see [the measured report](reports/quick_recommendation_benchmark.md). Identical
sampling seeds reproduce input selection; live API changes and deadlines can change
the list. Website development, deployment, identity auditing, and preference-quality
evaluation remain later work.

## D-026: Choose one plausible seed recording instead of rejecting version alternatives

Date: 2026-10-08
Status: implemented in the quick prototype at the user's request

Question: Should several versions of a liked song prevent that song from supplying
recommendation evidence?

Choice: For the quick prototype, choose one recording from an uncapped set of
plausible candidates. Prefer exact album context, then a known/closest duration,
then recording ID as a deterministic tie-break. Save all alternative IDs, the chosen
ID, and the choice reason. Fetch only the chosen detail record, preserving the
one-search/one-lookup ceiling and the overall request/runtime budgets. Do not
refill a failed seed. Supplied recording IDs still bypass search.

Scope: This changes D-025's initial uniqueness requirement only. Existing detailed
artist/title/album/duration/version checks remain, and historical matching commands
keep their conservative ambiguity policy. This representative recording is a
practical input choice, not proof of the precise audio version originally liked.
Album edition suffixes, punctuation, remaster wording, and sparse contributor
credits remain distinct issues; see [the saved-run audit](reports/seed_matching_failures.md).

Evidence: Three of the six rejected seeds in the audited run had multiple plausible
recordings, two failed only exact album equality, and one search returned no results.
Returned candidates were not devoid of metadata. Some lacked duration; one fetched
recording had no contributor relationships beyond primary artist credit.

How to check it: Tests verify one chosen lookup for multiple alternatives,
album/duration preference, response-order independence, and continued rejection of
explicit artist/version/duration conflicts. The complete offline suite now passes
184 tests. Earlier snapshots and benchmark counts are preserved as historical evidence.
