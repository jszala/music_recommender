# Full liked-list implementation plan

Date: 2026-10-07. Status: historical API implementation plan. The workflow was
implemented under D-023, but the full-list run and its queued continuation were
cancelled at the user's request under D-024. **The MusicBrainz public API approach
is not feasible for the intended full-library matching and broad-discovery workflow.**
See [the cancellation and partial-coverage report](full_library_run.md).
Project alignment: Milestone 4c, after the implemented Apple/diversity milestone
and before research evaluation. Scope decision: D-022; collection approach superseded
by D-024. Sections 1–6 below describe the discontinued API experiment, not an active run.

## Feasibility finding and next direction

The first additional 100 rows required 320 HTTP attempts and about 435 seconds.
The cancelled run retained 538 row outcomes, including the pilot: 187 accepted,
342 unresolved, and nine operational failures. One row was interrupted; 777 remain
unattempted. It charged 1,663 new MusicBrainz attempts and never reached expanded
discovery or Apple collection. The earlier 2–4-hour remaining-time estimate for
the full pipeline was projected, not observed to completion.

Public-API pacing, several lookups per input row, broader contributor expansion,
and transient HTTP 503 failures make the approach impractical for the intended
scale and repeated experimentation. Checkpoints solve interruption recovery, not
the collection throughput problem. API access remains appropriate for bounded pilots.

The next full-library design should evaluate a downloaded MusicBrainz database,
local indexes, and a retrieval adapter preserving recording/work relationships,
credit attributes, snapshot provenance, and the existing acceptance and scoring
rules. Validate it against frozen matches before collecting the full graph. The
download, import, indexes, adapter, and runtime comparison have not been implemented.
Missing credits and uncertain identities will still require honest coverage reporting;
a local database does not invent that evidence. Apple checks remain separate.

## Outcome and present limitation

Process every row in the supplied `data/private/favorites.json`, build one
consolidated preference profile from all confidently identified recordings, and
collect a much broader set of source-backed song candidates. Apply the existing
ranking, contributor/musician constraints, and automatic German Apple checks to
that profile. Deliver a requested ten-song batch, or a quantified shortfall.

The supplied file has 1,316 rows and 425 normalized credited-artist strings; those
strings are not 425 independently resolved artist identities. Before this cancelled
scale-up, the 20-row pilot had nine accepted recordings, four unresolved rows, and seven
literal searches with no result. Its discovery graph contains 44 eligible
candidates from twelve contributor routes. Fifteen candidates passed the Apple
check, and the current weighted selector returned two songs. These are pilot
results, not results from the full supplied list. The cancelled run's additional
matches remain preserved in row checkpoints and have not produced a full-profile batch.

Full-list processing means every supplied row is attempted and accounted for.
It does not mean every recording will be identifiable or have detailed credits.
Unknown rows remain visible and do not become invented preference evidence.
The source is the user's supplied file; connecting to a streaming account is a
separate feature.

## 1. Add a resumable collection job

- Introduce `src/process_library.py` and `config/full_library_limits.json` for a
  single workflow: match favorites, consolidate, discover candidates, check Apple,
  rank, and export. Keep the existing individual commands compatible.
- Bind each job to the input hash, matching/collection/Apple rules, country `DE`,
  and source-bound discovery overrides. Refuse to resume against changed inputs
  or rules; create a new job with explicit cache reuse instead.
- Maintain an atomic job manifest, completed row records, operation cursors, and
  cumulative request counters under one ignored private job directory. Use a
  job lock and the existing provider cache locks. Interrupted temporary writes
  must not be treated as completed work.
- Checkpoint at completed HTTP operations and rows. Stop a tranche when its
  request allowance is used; the next tranche continues unfinished work rather
  than restarting at row one. Keep not-attempted, interrupted, failed, and
  conclusively processed rows distinct.
- Persist the allowance debit before each transport attempt, including retries.
  Interrupted sends remain charged so a crash cannot reset or undercount the
  cumulative request budget. Completed responses remain replayable from cache.
- Reuse the frozen pilot responses and source decisions after verifying their
  input/rules/snapshot hashes. Avoid repeat requests for identical searches or
  recording IDs. Preserve old pilot outputs as historical snapshots.
- Support `--resume`, `--offline`, `--stage`, and `--status`. A normal invocation
  advances through successive bounded tranches until the stage ends or its
  total budget is reached. No confirmation between tranches is needed.

## 2. Match and account for all 1,316 rows

- Schedule all rows deterministically, spread across credited-artist groups so
  a temporary interruption does not leave only the first alphabetical artists
  represented. Original source-line numbers remain the row identities.
- Retain D-015's existing acceptance evidence: exact normalized title and credited
  artist, observed album context, known duration within two seconds, compatible
  version evidence, and a single qualifying recording after the declared search
  and alternative inspections. Search relevance alone cannot accept a match.
- Separate the terminal outcomes accepted, ambiguous, no confident match, and
  literal search with no result. Separate operational failures and budget
  deferrals, which remain eligible for a bounded resume/retry.
- Complete the full conservative first pass before changing retrieval or matching
  rules. Report failures by cause; do not extrapolate the pilot's acceptance rate
  to the full file. Broader query fallbacks, additional album evidence, or matching
  normalization changes require a separately recorded rule revision and regression
  cases. They are not prerequisites for completing the first full pass.
- Build one source-bound `matches.json`, `profile.json`, recording dataset,
  manifest, and credit-coverage report from the successful checkpoints. Preserve
  every source row even when several rows map to the same recording ID.
- Count each accepted recording once for preference influence. Keep distinct
  live/remix/edit recordings separate and expose unresolved cross-ID equivalence.
  Apple remaster acceptance does not merge favorite recording identities.
- Resolve duplicate snapshot conflicts explicitly. Never silently choose whichever
  chunk was merged last. Build all profile hashes against the published snapshots.
- Rebuild familiar-artist exclusions from the entire supplied input and all newly
  accepted primary-artist IDs, retaining existing bound alias/collaboration
  overrides. All accepted favorites contribute to scoring; no nine-song subset
  remains hidden behind the profile interface.
- Show credited performers, writers, producers, and staff separately. Primary
  artist identity is useful context; missing detailed credits remain missing.
  No inferred band membership or invented personnel is added.

Automatic matching continues past uncertain rows. Optional identity review can
improve coverage later; routine manual confirmation is not required to run this
workflow. Independent human precision auditing remains pending until performed.

## 3. Expand discovery across the full profile

- Build the eligible contributor frontier from every accepted favorite and all
  supported role categories. Replace the pilot's fixed twelve-contributor prefix
  with a persistent queue over that full frontier.
- Allocate routes across favorite-artist groups, and retrieve breadth before
  depth: seek an eligible candidate from each scheduled contributor before
  collecting additional songs through contributors already explored. Record
  shared routes by contributor ID once, regardless of roles or favorites.
- Aim for an initial pool of 500 distinct eligible candidates, with at least
  100 contributor routes explored when the observed frontier and budget permit.
  These are collection targets, not promised counts or statistical thresholds.
- Reuse verified eligible candidates from the old graph, but recheck their policy
  against the expanded familiar-artist registry. Deduplicate recording lookups and
  share returned snapshots across contributor routes.
- Preserve the recording/work relationship evidence and primary-credit browse
  routes. Paginate route discovery explicitly rather than repeatedly requesting
  the first pages. Proposed per-contributor bounds: up to six accepted candidates,
  eighteen detail lookups, four 50-result browse pages, and two songwriting-work
  lookups. Save page offsets and route exhaustion.
- Filter familiar acts and known favorite recording identities before expensive
  detail lookups wherever returned metadata permits; verify final eligibility
  against detailed credits. Replace excluded candidates from the remaining queue.
- Stop at the pool target, frontier exhaustion, or the total discovery budget.
  Report explored and unexplored contributors, artist-group coverage, route
  exhaustion, duplicate routes, and each exclusion reason. This remains bounded
  discovery, even though scoring uses the entire accepted favorite profile.
- Freeze the consolidated discovery dataset before Apple collection. A future
  evaluation job must construct its own training-only profile, exclusions, and
  frontier; this full-library discovery snapshot is not a holdout experiment.

## 4. Check Apple automatically, then select

- Check every eligible positive-score candidate in the frozen pool, using D-021
  unchanged: `DE`, song-only music search, explicit content included, at most two
  distinct queries, 50 results, conservative metadata/version matching, studio
  remasters allowed, and explicit boolean `isStreamable=true`.
- Persist each completed candidate check and resume across 60-attempt tranches.
  Keep request failures, budget deferrals, truncated search, unknown metadata,
  and false/missing streaming flags separate. Unsuccessful search is not proof
  of catalog absence.
- Reuse existing raw Apple responses when their queries, country, and snapshot
  policy agree. Recompute decisions and bind the final report to the new dataset
  fingerprint; never attach the old 44-candidate availability file unchanged.
  Retain the actual response timestamps and offer an explicit fresh-snapshot
  option without silently replacing frozen evidence.
- Run the existing weighted selector, equal-role comparison, no-saturation
  comparison, and compatibility diversity option on the same frozen data and
  Apple report. Keep scores, weights, saturation, and greedy selection unchanged.
- Apply availability before consuming allowances. Reserve every explanatory
  connector of a selected song, preserve musician uniqueness and the single
  familiar-collaboration allowance, and reset allowances per batch.
- Export the source-linked selected batch and ordered playlist preparation file.
  iTunes track IDs remain distinct from verified Apple Music catalog IDs.
  Account playlist creation and paid Apple integration remain later work.
- If the weighted list is still short, report whether coverage, contributor
  conflicts, musician conflicts, collaboration rules, or the greedy choice caused
  the shortfall. Expansion targets do not guarantee ten feasible selections.
  Any subsequent larger pool or alternative selector must be a separate,
  documented change; do not relax constraints to fill slots.

## 5. Request limits and expected duration

Proposed defaults are upper limits, including retries, not forecasts:

| Stage | HTTP attempts per tranche | Total attempts per job stage | Minimum request interval |
|---|---:|---:|---:|
| Favorite matching | 120 | 16,000 | 1.1 seconds |
| Candidate discovery | 120 | 6,000 | 1.1 seconds |
| German Apple checks | 60 | 2,000 | 3.1 seconds |

The matching ceiling covers 1,316 rows with the existing two search pages and
four lookups per row, each with at most one transient retry, before cache savings.
The Apple ceiling covers 500 candidates with two queries and one retry each.
Already attempted operations must count toward persistent totals after restarts.
Budget exhaustion leaves an explicitly incomplete stage and retained progress;
limits are never silently increased.

MusicBrainz calls share one serial provider limiter/cache across stages; use the
existing contact identification and bounded retry/backoff. Retain 1.1-second
pacing in accordance with the [MusicBrainz rate rules](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).
Apple documents approximately 20 calls per minute; keep the current 3.1-second
spacing and caching under its [search API guidance](https://performance-partners.apple.com/search-api).

This may take several hours of live collection. The first additional 100-row
segment, across as many request tranches as needed, provides an observed
requests-per-row and latency estimate; report the
remaining-time estimate from actual measurements. Avoid promising a runtime or
acceptance percentage from the small pilot. A status view must show total input
rows, processed rows, accepted recordings/artists, unresolved rows, eligible
candidates, Apple matches, completed stages, and remaining request allowances.

## 6. Implementation order and validation

1. Add persistent job state, counters, operation checkpoints, resume/offline
   behavior, and the profile consolidator. Refactor the matcher to checkpoint
   per row without changing current acceptance decisions.
2. Test interruption during search, alternative lookup, row commit, and snapshot
   publication. Validate pilot import, input/rule hash rejection, conflicting
   snapshots, duplicate source rows, cumulative retry budgets, and no repeated
   completed network requests on resume. Replay the existing pilot unchanged.
3. Implement persistent broad contributor discovery and paging. Test breadth
   across artist groups and roles, no repeated first-page bias, refill after
   exclusions, candidate deduplication, expanded familiar-artist exclusions,
   frontier exhaustion, and visible route omissions.
4. Add incremental Apple checkpoints and final snapshot rebinding. Test that an
   expanded dataset invalidates the old report, while compatible raw responses
   can be replayed; preserve country/version/streaming checks and failure reasons.
5. Verify full-profile scoring and every hard constraint. Measure local scoring
   time/output size; add a contributor-to-favorites index only if needed, with
   unchanged saturation denominators, contribution sums, and deterministic
   rankings checked against the existing implementation.
6. Run the regression suite and an end-to-end synthetic multi-tranche job,
   including interruption/resume and a final zero-network replay. Test that all
   input rows are accounted for and partial work cannot masquerade as complete.
7. Process the first additional 100 rows as an automatic smoke check, then
   continue through every remaining row and the declared discovery/Apple budgets.
   This segment is not another stopping point requiring manual confirmation.
8. Publish the final coverage report, selected batch, playlist preparation, and
   matching/discovery/availability snapshots; update README, plan, decision log,
   and results with observed counts and limitations.

## Completion criteria

- All 1,316 input rows have an attempted matching outcome; operationally deferred
  rows are zero before calling full-list matching complete. Unresolved identities
  are counted and explained, not forced into the profile.
- Every confidently accepted favorite and its available credits are included in
  the source-bound scoring profile. No unmatched row silently disappears from
  the coverage denominator or familiar-artist exclusions.
- The candidate pool is collected across the full profile's frontier with the
  declared breadth policy, targets, limits, and visible omissions. Every candidate
  admitted to the batch has a qualifying country-bound Apple match and valid
  source paths; unavailable/unknown candidates consume no list allowances.
- The requested size is ten. Return ten when the unchanged selection supplies
  them; otherwise show exact exclusion counts and remaining shortfall.
- A complete offline replay reproduces the profile, scores, matching decisions,
  selected order, and playlist preparation with zero HTTP attempts.
- The results report separates input coverage, matching/credit coverage,
  discovery breadth, Apple coverage, and final-list size. Independent identity
  accuracy and listening usefulness are not claimed from these collection counts.
