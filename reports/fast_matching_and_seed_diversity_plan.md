# Handoff plan: simpler matching and recommendations across seed songs

Date: 2026-10-08

Status: planned. This document records the requested follow-up; its changes have
not been implemented or benchmarked. Start with matching, measure it, then change
discovery and selection. Do not describe the targets below as achieved results.

## 1. Objective and user priorities

Improve the existing fast, live MusicBrainz prototype so that most sampled liked
songs can contribute to discovery and the final list draws on different songs.

The user's priorities, in order, are:

1. Simplify matching substantially. Target at least 90% of sampled songs matched
   to a compatible MusicBrainz recording. Choosing a representative recording is
   acceptable; exact album, duration, and release-version identity are unnecessary.
2. Accept that some correctly matched recordings have sparse contributor data.
   Report this honestly rather than treating it as a matching failure.
3. Explore accepted seeds fairly before spending more requests on one seed.
4. Balance the selected list across seed songs and avoid several covers of the
   same composition filling the list.

Here, **random seed** is the integer controlling sampling. **Seed song** is a
sampled liked song that has been matched. Keep those meanings distinct in code,
exports, and documentation.

The 90% figure is a measured acceptance target, not proof that all input songs
exist in MusicBrainz or a reason to accept an unrelated result. Matching identity,
useful credit coverage, and recommendation quality are separate measurements.

## 2. Starting point and evidence

Repository: `/home/jan/Projects/music_recommender`.

The working tree already contains uncommitted implementation from earlier work,
including untracked Python modules and tests. Inspect and preserve it. Do not
reset the repository or assume the Git HEAD contains the current prototype.
No agent delegation is required by this plan.

Read these files first:

| File | Relevant responsibility |
|---|---|
| `src/quick_recommend.py` | Sampling, fresh HTTP client, seed matching, discovery, worker supervision, exports |
| `src/match_recordings.py` | Existing conservative query/check helpers; historical matching workflow |
| `src/recommend_songs.py` | Credit scores, contribution evidence, contributor penalties, list selection |
| `src/song_policy.py` | Full-input familiar-artist exclusions and performer/collaboration eligibility |
| `src/credits.py` | Observed recording/work credits; primary artist is a performance proxy |
| `src/benchmark_recommendations.py` | Sequential fresh runs and CSV/JSON summaries |
| `src/check_apple_music.py` | Separate checker for an exported recommendation list |
| `tests/test_quick_recommend.py` | Fast prototype, transport, selection, and export tests |
| `tests/test_match_recordings.py`, `tests/test_song_ranking.py` | Historical workflow compatibility |
| `README.md`, `plan.md`, `DECISIONS.md` | Current workflow and D-025/D-026 decisions |
| `reports/seed_matching_failures.md` | Saved examples of avoidable matching rejection |
| `reports/quick_recommendation_benchmark.md` | Previous measured runtime results |

Private input: `data/private/favorites.json`. Contact file:
`data/private/musicbrainz_contact.txt`. Read contact only when executing an
authorized live run; do not copy its contents into documentation or public files.
Private data may be absent in another checkout. Offline fixtures must remain
sufficient to run the tests without these files or network access.

The latest three comparable fresh runs are preserved under
`data/private/quick_lists_2026-10-08_094257/`:

| Run | Random seed | Sampled | Accepted recordings | Candidates admitted | Recommendations | Represented favorite songs | Complete call time | Attempts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `run_001` | 3 | 8 | 2 | 5 | 5 | 1 | 15.971 s | 15 |
| `run_002` | 4 | 8 | 1 | 7 | 2 | 1 | 35.360 s | 32 |
| `run_003` | 5 | 8 | 4 | 29 | 4 | 2 | 38.670 s | 35 |

Seven of 24 sampled songs matched across these runs. The first list consists of
five versions of one composition connected through Ted Lucas. The second list
uses Chris Cohen only. The third has three recommendations through Warpaint and
one through Kelela. Inspect complete JSON `contributions`, not only the three
connections shown by the readable renderer.

Jon Bap's `Let It Happen` and Palatine's `Ecchymose` matched but their returned
snapshots contained no additional direct/work contributor credits. Batsumi's
`Anishilabi` did have additional credits; it simply contributed no selected
recommendation within that run. Do not label all three as having no credits.

Other useful immutable evidence:

- `data/private/quick_final_verification_2026-10-08/run_001/`: original strict
  matching audit, before D-026.
- `data/private/quick_representative_versions_2026-10-08/run_001/`: D-026 run.
- `reports/full_library_run.md` and the cancelled full-library run evidence:
  preserve these and do not restart the cancelled job.

The last reported offline baseline was 184 passing tests. Re-run the suite to
establish the actual baseline in the checkout you receive.

## 3. Constraints to preserve

- Keep the callable `recommend_from_likes` and its existing required arguments.
  Defaults remain 8 sampled artist groups, up to 15 recommendations, 35 charged
  HTTP attempts, and a 55-second runtime budget per recommendation run.
- Keep weighted sampling: artist weights 1/2/3 for 1/2–10/>10 distinct liked
  songs; one uniformly chosen song per sampled artist; stable ordering and the
  supplied random seed. Weights affect sampling only, not credit scores.
- Keep full-input familiar-artist exclusions, accepted/supplied favorite-ID
  exclusions, observed performer uniqueness, and at most one familiar
  collaboration. Do not build exclusions from only the matched sample.
- Keep unchanged base credit scoring and the fast mode's repeated-contributor
  multiplier `1 / (1 + previous selected appearances)`.
- Keep historical matching and strict contributor selection conservative by
  default. New relaxed matching and seed balancing apply to the fast prototype.
- Keep fresh responses for every live run. Saved evidence may support audits and
  offline tests but must not become a cross-run response cache.
- Keep within-run request/recording deduplication, 1.1-second spacing across
  consecutive runs, charging before transport, no automatic retries, and
  provider backoff. Count search fallbacks as normal attempts.
- Keep at most five seconds per request or remaining collection time, the
  process supervisor that terminates genuinely stalled transport, and the
  collection cutoff before final scoring/export. The current reserve is
  `min(5 seconds, runtime_limit_seconds / 4)`; do not silently extend runtime.
- Keep at most 100 admitted candidates, one browse page per route, and at most
  one songwriting-work route per contributor.
- Keep Apple checking separate, checking selected songs only and preserving the
  original recommendations and order. Recommendation generation makes no Apple
  requests and makes no availability claim.
- Do not add a database download, local MusicBrainz server, website, deployment,
  paid provider, or a full-library API crawl as part of this fix.

## 4. Phase A: relaxed representative-song matching

### 4.1 Separate identity from release preferences

Add fast-mode matching helpers, preferably in a small dedicated module so that
historical `candidate_checks`/`qualifies` behavior is not accidentally relaxed.
Helpers should be pure where possible and shared by live and offline verification.

Retain raw input and response values. Generate separate normalized comparison
keys and record which normalization made a match possible:

- Unicode normalization and case folding.
- Standardized curly/straight apostrophes, quotation marks, dashes, and whitespace.
- Recognized trailing remaster/year annotations and featured-artist annotations
  removed from the base song-title key. Preserve the extracted version/guest
  information separately. Do not strip every parenthetical phrase from a title.
- Named live/remix/edit versions can have a base-title key, but keep their labels
  for version preference and disclosure when selecting an alternative version.
- Compare individual credited artist names and canonical names in the returned
  `artist-credit`, as well as combined display text. A matching main artist can
  qualify despite a guest omission or a different credit join phrase.

Do not blindly split every `&`, comma, or slash in artist names. Prefer a full
artist-name match first; use explicit feature annotations and candidate credit
structure to interpret collaboration strings. Add tests for names whose own
spelling includes those separators. If the main artist cannot be established,
retain a specific unresolved outcome rather than matching by a guest alone.

The acceptance anchor is a compatible normalized base song title and main
credited artist. Album, duration, missing release metadata, and version labels
are preferences, not mandatory exact-equality checks. Explicitly unrelated titles
or artists, video-only responses, invalid IDs, and malformed core metadata still
fail. Do not introduce unrestricted fuzzy matching or automatically accept the
first result solely to raise the reported percentage.

When choosing among compatible candidates, use this deterministic priority:

1. Exact normalized full title/credit and the requested version, where observed.
2. Matching base title/main artist; prefer a studio version for unmarked inputs.
3. Matching normalized album context, where observed.
4. Known/closest duration, where observed. Duration is not a rejection threshold.
5. Stable recording MBID as the final tie-break.

Document and test the precise ordering. Live result order must not affect the
winner when the same candidate metadata is supplied in a different order.
An alternative live/remix/edit version may qualify when no preferred version was
returned, but export a representative-version notice. Do not claim exact audio
identity or independent verification of the originally liked recording.

Separate core identity validation from credit-field completeness. The current
`valid_record(..., releases=True)` and detailed `qualifies` gate cannot remain the
acceptance gate for this mode. Missing releases or relationship fields should
produce release/credit-coverage diagnostics, rather than erase an otherwise valid
identity match. Distinguish missing fields from malformed supplied field types;
preserve raw snapshots and do not manufacture empty relationship lists to hide
missing evidence. Ensure downstream credit parsing/export can handle the accepted
partial snapshots safely.

### 4.2 Search and lookup flow

For the existing deterministic sample:

1. A supplied `recording_mbid` bypasses search. Fetch its details and apply the new
   core identity/response checks. Keep the original ID and any discrepancy visible.
2. Otherwise search using the normalized base title and artist rather than a
   remaster or feature annotation copied verbatim into the entire query.
3. Inspect the first page of at most 25 results. A reported total greater than
   the returned count is coverage metadata, not automatic rejection. Choose the
   best compatible candidate from the page and mark `search_truncated`.
4. Fetch details for at most one chosen recording. Details should confirm core
   identity and ingest available credits. Exact album equality or a two-second
   duration difference must no longer reject the seed.
5. If a successful initial search contains no compatible candidate, defer one
   broader, distinct query to a fallback pass. For example, relax restrictive
   artist-display formatting while retaining artist checks against results.
6. Finish every seed's initial search/lookup opportunity before executing these
   fallbacks. No pagination, automatic retries, repeated identical queries, or
   replacement artists within the sample. An HTTP failure is a provider failure,
   not evidence that the song is missing; it does not trigger an automatic retry.

Allow at most two distinct search queries and one detail lookup per seed, subject
to the shared stage/global limits. Preserve all alternatives observed within the
run, and keep evidence for capped pages and fallback choices.

### 4.3 Request allocation

At the default 35-attempt budget, matching can use at most 20 attempts; the unused
remainder is available to discovery, reserving at least 15 if matching uses its
full allowance. This includes supplied-ID lookups and all search/detail attempts.
Do not consume the entire budget trying to reach 90%.

For nondefault budgets, define and export a deterministic allocation rather than
hard-coding 20 unconditionally. A proposed default formula is:

```python
discovery_request_reserve = (3 * max_requests) // 7
matching_attempt_limit = min(20, max_requests - discovery_request_reserve)
```

This yields 20/15 at 35 attempts and permits matching when the global budget is
one or two. Tests must cover small budgets and larger requested sample sizes.
Unused matching capacity transfers to discovery; reserved requests do not
guarantee enough remaining wall time when the provider is slow.

A matching-stage limit stops matching and transitions to discovery; it must not
raise the same exception that stops the entire run for a global budget/deadline.
Report unattempted and fallback-not-attempted seeds with the actual reason. All
request timeouts and attempts remain subject to the existing overall deadline.

### 4.4 Matching outputs and measurement

Keep existing export fields where practical and add:

- Policy/version identifier and matching attempt allocation.
- Raw/normalized title and artist, chosen MBID, candidate alternatives, query
  count, fallback use, truncated-search flag, choice reason, and version notice.
- A terminal outcome for each sampled row: accepted, no compatible candidate,
  provider failure, invalid response, stage budget, global budget, or interruption.
- Accepted source-row count separately from distinct accepted recording count.
  Two source rows resolving to one MBID are two matched rows but one discovery
  seed identity; do not inflate diversity or score duplicate recordings twice.
- `match_rate = accepted_sampled_rows / sampled_rows`, including provider errors,
  not-attempted rows, and interruptions in the denominator.
- Additional conditional diagnostics, clearly labeled, for completed successful
  searches. They do not replace the primary match rate or satisfy its target.

**Phase A acceptance:** meaningful offline cases pass, and a fresh fixed sample
of at least 100 distinct liked rows reaches at least 90% accepted rows. Inspect
accepted results for obvious wrong-artist/song mistakes and report that inspection
separately from the rate. If the target is missed, report the exact failures and
remaining causes; do not declare this acceptance check complete or accept
unrelated candidates to make it pass. Record this checkpoint before implementing
the discovery/selection changes. Document unresolved obstacles if they cannot be
removed within the stated budget, then continue independently useful later work.

## 5. Phase B: separate matches from contributor coverage

An accepted recording remains accepted even with `relations: []`. It can count
toward the match rate without yielding a productive discovery route.

Use at least these separate credit diagnostics:

- Primary artist credits observed.
- Additional eligible direct recording credits observed, by role/category.
- Eligible work-level credits observed, by role/category.
- Contributor routes potentially available.
- Compatible candidates actually found and selected through those credits.

Do not assume a primary artist proxy necessarily supplies useful unfamiliar-act
recommendations, and do not drop existing eligible relationships arbitrarily.
Use wording such as "matched; no additional contributor credits observed" when
appropriate. An empty relationship list describes this response only.

Matched MBIDs are deduplicated for discovery. For source diversity, recordings
with the same nonempty set of known work MBIDs count as one source-song group;
otherwise use recording MBID. Preserve all original favorite IDs and explanations.
This grouping affects balancing only, not the base scoring formula. Report
unknown composition identity rather than inventing equivalence from titles.

## 6. Phase C: discovery balanced by seed song

Current `balanced_frontier` balances contributor order across accepted primary
artists, but `QuickCollection.discover` then runs artist lookup, browse, work
browse, and a fallback before moving to another contributor. Replace that
scheduling in the fast mode.

Build a deterministic queue of source-song groups, each referencing its eligible
contributors and route state. Route state still limits each contributor to one
artist-relationship lookup, one artist browse page, one work browse route, and
bounded individual candidate fallbacks.

Scheduling rules:

1. Advance each active seed by at most one outgoing HTTP attempt per round.
2. Within a seed, advance one contributor route toward a usable batch before
   initializing all of that seed's contributors. A large frontier must not spend
   every request on relationship lookups without fetching candidates.
3. Shared contributor/request state is global within the run. Fetch once and
   propagate its completed evidence/state to every connected seed. Do not charge
   an HTTP attempt for a within-run reuse or lose a later seed's attribution.
4. Credit-free/exhausted seeds leave the active queue, with a recorded reason.
5. Prefer seeds with no compatible candidate over seeds that already have one.
   Pause a seed once the current pool can supply two mutually compatible assigned
   recommendations for it while other seeds are still underserved. Re-evaluate
   pauses as candidates and performer conflicts change; a pause is not exhaustion.
6. Supported browse responses are ingested directly. Missing required credit
   fields use individual fallback lookups; each fallback is a scheduled turn and
   remains deduplicated and charged within the same budget.
7. Validate each admitted candidate's positive connection using observed credits.
   Route provenance alone is insufficient evidence for a recommendation.

Export per-seed attempts sponsored, operations, contributors explored,
candidates connected, candidates eligible, candidates selected, paused/exhausted
status, and unexplored route counts. Shared evidence/candidates may appear under
several seeds; label counts as overlapping and keep global unique totals.
For attempts shared by several seeds, identify one scheduling sponsor and all
beneficiaries so global accounting sums correctly.

Update `should_stop` to evaluate the final seed-balanced selector rather than the
old unbalanced list size. `target_reached` requires the requested recommendation
count and the configured coverage target. Budget/deadline/candidate-limit or
exhaustion may return fewer songs. Selection shortfall and coverage shortfall are
separate from the collection stopping reason.

If every remaining route belongs to a seed whose selection capacity is already
filled, and the other seeds are credit-free or exhausted, finish with an explicit
selection-capacity stopping reason. Do not repeatedly cycle paused queues or spend
the remaining budget solely to try to bypass the per-seed cap. Preserve those
unexplored routes and state that discovery was not exhaustive.

## 7. Phase D: selection across source songs and composition deduplication

Add an opt-in seed-balancing policy to the shared selector/report API and enable
it in `recommend_from_likes`. Existing callers retain current behavior unless
they choose the new policy. Prefer independent selection options rather than
changing the meaning of `contributor_policy="strict"` or `"penalized"`.

Fast-mode policy defaults:

- Minimum represented source-song groups: 3, with an effective target capped by
  the requested list size. Do not silently lower it because few seeds matched or
  had usable credits; that is a reported shortfall.
- Maximum recommendations assigned to a source-song group: 2.
- Coverage rounds: give feasible unrepresented seeds one result before assigning
  a second to an already represented seed.
- At most one selected recording containing a particular known work MBID.

For each candidate, construct its possible source-song assignments from existing
positive `contributions`, grouped by the source identities described in Phase B.
Sum repeated per-artist contribution rows for the same favorite/source group;
they do not represent additional seed songs.

Each selected recommendation receives exactly one `primary_seed_song` assignment
for balancing. Retain its full contributions and all other observed connections.
A candidate connected to three seeds is still one selected song and one primary
assignment; do not claim three list slots or invent unsupported assignments.

Evaluate feasible candidate/assignment pairs using this order:

1. Existing performer, familiar-artist/favorite, collaboration, and new known-work
   uniqueness constraints must all pass.
2. Prefer a primary seed with the fewest prior assigned recommendations, below
   the cap of two. This places unrepresented seeds before second appearances.
3. Within that coverage round, prefer the existing contributor-adjusted selection
   score, then unchanged base score, then stronger evidence for the assigned seed,
   then stable title/recording/source IDs.

When several assignments are possible, prefer an unrepresented connected seed
rather than assigning every result to its strongest already represented seed.
Assignment remains evidence-backed; export its rationale. The selection score
continues to use all observed contributions, not only the balancing assignment.

Performer conflicts can make greedy choices block another seed. Include a focused
test and a bounded reassignment/look-ahead step where useful. Do not claim an
exact global maximum unless an exact solver is actually implemented and bounded
within the runtime reserve. Report the algorithm's limits.

Read composition/work IDs from recording-to-work relationships in raw snapshots,
including works with no songwriter relationship rows. `extract_credits` alone
can omit such work IDs. Reject a candidate when any of its known work IDs overlaps
the selected set; this also covers partial overlap in multi-work recordings.
Do not equate unrelated songs merely because titles match. Unknown work IDs are
allowed, and the report must state that composition deduplication covers observed
work identities only. This rule deduplicates recommendations; it does not add a
new exclusion against every composition in the user's favorites.

Examples to enforce:

- Five different performers covering the same known work produce at most one
  recommendation, even when performer uniqueness would allow all five.
- Seed A's ten high-scoring candidates cannot displace the first compatible
  candidate from B or C solely because their scores are lower.
- Only one productive source group produces at most two recommendations, possibly
  fewer under other constraints, and a visible coverage shortfall.
- With only three productive source groups, the cap permits at most six results.
  Do not bypass the cap merely to fill the requested 15 slots.

## 8. Exports, experiments, and compatibility

Preserve JSON and readable exports, manifest/profile/recording bindings, source
hashes, sampling reproducibility, completed checkpoints, and optional Apple input
compatibility. Add diagnostics instead of mutating preserved historical outputs.

Extend selection summaries with configured/effective source target, distinct
primary seeds represented, recommendations per seed, source-coverage shortfall,
known-work conflicts, and unknown-work coverage. Keep primary-assignment coverage
separate from the number of seeds mentioned anywhere in explanations.

Extend experiment CSV/JSON summaries with:

- Accepted sampled rows, sampled rows, match rate, and distinct accepted MBIDs.
- Seeds with additional eligible contributor credits.
- Distinct source-song groups represented and the largest assigned seed share.
- Per-seed discovery coverage and known-composition duplicate exclusions.
- Existing runtime, requests by operation, candidate/recommendation counts,
  stopping reasons, repeats, and list overlap.

Keep recording-ID Jaccard as the existing overlap metric. A separate known-work
overlap may be added but must not silently replace it. Missing new fields in
historical reports/test runners need an explicit compatible handling strategy.

Export policy configuration with every result. Add optional settings only where
needed; keep existing callable signatures and CLI arguments usable. Any format
version change must be deliberate and covered by the standalone Apple tests.

## 9. Verification checklist

### Matching

- Curly/straight apostrophes, Unicode/dash/spacing variants, remaster/year labels,
  featured-artist title formatting, guest omission, and credit join phrases.
- Correct main artist with multiple individual credits; an unrelated main artist
  sharing only a guest does not qualify.
- Artist names containing `&`, slash, or commas and real parenthetical song titles.
- Album edition/compilation differences, missing album/duration, and duration
  differences beyond two seconds do not reject an otherwise compatible song.
- Requested live/remix version preferred; alternative version explicitly labeled.
- Multiple plausible recordings and truncated search pages choose deterministically.
- Successful empty/no-compatible initial search gets at most one distinct fallback;
  fallbacks occur only after first-pass opportunities and fit the stage limit.
- Supplied IDs bypass search; wrong core identity and malformed responses fail.
- Duplicate source rows/accepted MBIDs do not inflate distinct seed coverage.
- Rate denominator includes failures, not-attempted rows, and interruptions.
- Historical conservative matching tests still pass.

### Discovery and selection

- Three seeds receive turns before one seed receives another outgoing request.
- A seed with many contributors advances a batch route instead of initializing
  its entire frontier; later seeds retain a fair opportunity.
- Shared contributors, requests, recordings, and results are deduplicated without
  dropping another seed's positive evidence or double-counting global attempts.
- Missing additional credits remain successful matches with separate coverage.
- Batched recording/work credits and bounded individual fallback still work.
- Seeds with no candidates are distinguished from unattempted/unexplored routes.
- Lower-scoring B/C candidates receive first appearances before A gets its second.
- At most two assignments per source group; duplicate favorite MBIDs or known-work
  equivalents count as one source identity for balancing.
- Multi-source candidates get exactly one supported primary assignment and retain
  every original contribution in explanations.
- Known-work duplicates are excluded even when performers differ; equal titles
  with different work IDs remain distinct; unknown works stay visible.
- Performer uniqueness and familiar-collaboration limits remain enforced, including
  a conflict case that requires reassignment/look-ahead for better source coverage.
- Base scores are unchanged and repeated-contributor penalties still apply.
- Existing strict/penalized callers without new options retain previous behavior.

### Budgets, transport, and exports

- Default matching ceiling is 20 of 35; stage exhaustion transitions to discovery.
- Small/global-zero-remaining budgets, no accepted seeds, no productive seeds,
  candidate cap, provider backoff, and malformed responses produce valid reports.
- Every attempt is charged before sending; no hidden redirects/retries or additional
  artist/alias lookups outside the budget; cross-run 1.1-second spacing is retained.
- Requests honor remaining time; a transport ignoring timeout is actually killed
  by the supervisor and completed snapshots survive.
- Live runs do not reuse previous run responses. Offline fixture replay does not
  access the network or pretend to be a fresh live benchmark.
- JSON and readable outputs agree with returned results and attribution counts.
- No Apple calls during recommendation generation. A separate Apple check retains
  every selected song/order and leaves the source run unchanged.

Run the complete suite after relevant changes:

```bash
python3 -B -m unittest discover -s tests -v
```

Add tests for the new behavior and revise obsolete *fast-mode* assertions that
require capped-search or album-only rejection. Do not remove historical
conservative assertions or weaken unrelated transport/eligibility coverage.

## 10. Benchmark protocol and implementation order

1. Inspect instructions and working-tree state; run the offline baseline. Do not
   discard earlier edits or preserved private evidence.
2. Implement Phase A helpers, budget/fallback behavior, and matching diagnostics.
   Build focused offline regressions from the saved failure cases or sanitized
   public response excerpts without changing the original run directories.
3. Measure matching first using at least 100 distinct deterministic sampled rows
   from the full liked list. Select and freeze the sample manifest before examining
   its new outcomes: input hash, random seed, source row IDs, and sampling rules.
   A suitable selection uses existing weighted sampling with `seed_count=100`,
   then partitions those fixed rows into batches of at most eight.
4. Add a small matching-only benchmark helper/entry point if necessary. It must use
   the same new matcher, fresh client, stage allocation, worker supervision, and
   cross-run pacing as the prototype. Attempt each fixed row once as a seed in
   its assigned batch; do not re-sample subsets and accidentally omit rows.
   Each batch uses the per-run 55-second limit; the whole 100-row experiment may
   take several minutes. Publish primary/conditional rates, failures, chosen
   identities, and a documented inspection of accepted matches. A repeat is a
   new observation, not an opportunity to replace failed results selectively.
5. Record Phase A's measured result against 90%, including any shortfall. Do not
   use a conditional metric or increased time/request budget to claim it passed.
6. Implement credit diagnostics, balanced discovery, source assignments, composition
   deduplication, and coverage-aware stopping. Run focused and complete tests.
7. Repeat the three recommendation experiments with random seeds 3, 4, and 5,
   `seed_count=8`, default limits, and a new output directory. Example:

   ```bash
   python3 -B -m src.benchmark_recommendations --random-seeds 3 4 5 --seed-counts 8 --repeats 1 --contact-file data/private/musicbrainz_contact.txt --output data/private/quick_matching_diversity_2026-10-08
   ```

   Choose another unique directory if that name already exists. Every run must
   fetch fresh responses. Compare the saved baseline's sampled source rows,
   matching outcomes, requests, source coverage, and runtime. Response changes
   make this an operational comparison, not a controlled quality experiment.
8. Report complete callable/experiment-measured wall time, including sampling,
   worker startup, scoring, and exports. Every recommendation run should remain
   under 60 seconds. Explain short lists or coverage failures from evidence.
9. Update README, the project plan, decision log, and results/benchmark report for
   the implemented behavior. Preserve original run evidence and historical counts.
   Describe missed acceptance targets honestly; do not claim listening-quality
   improvement from runtime, matching, or diversity measurements.

## 11. Deliverables and completion report

Deliver implementation, offline tests, fresh matching and recommendation reports,
extended experiment summaries, and documentation reflecting the final policy.

The completion report must state:

- The actual matching rate and its denominator, including provider/budget failures.
- What was inspected for matching correctness and what remains unverified.
- Accepted recordings versus seeds with usable credits versus represented seeds.
- Recommendation counts, per-source assignments, known-work exclusions, and any
  remaining concentration/coverage shortfall.
- Complete runtime and charged requests for every new recommendation benchmark.
- Offline test results, compatibility checks, and any acceptance target not met.
- Clickable links to the new readable lists, benchmark summary, and audit report.

No confirmation round is needed for routine implementation decisions within an
instruction to implement this plan. Follow the user's current authorization and
the environment's actual execution/approval requirements. Saving this plan alone
does not require live requests, restarting jobs, or changing recommendation code.
