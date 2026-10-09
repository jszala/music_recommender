# Case study: music discovery through contributor credits

## Question and approach

Can the musicians, writers, producers, and engineers behind favorite songs help
find enjoyable music by other artists?

Contributor metadata offers a concrete reason to connect recordings: a producer
on one song may perform on another, or an engineer may connect otherwise unrelated
artists. This project explores that signal using MusicBrainz relationships.
It starts from a person's favorites, retrieves connected candidates, scores shared
credits, and selects recommendations with explicit diversity constraints.

The approach needs neither audio features nor a population of user interactions.
Its fixed weights make the calculation inspectable, but shared contributors alone
do not establish similar sound or listener preference. The current system is an
exploratory prototype with offline fixtures and bounded live collection tools.

## Data identity comes before ranking

Favorite-song metadata is not a unique recording identifier. Titles can contain
remaster notices, live versions, featured artists, and punctuation variants.
Several MusicBrainz recordings may represent plausible versions of the same song.

The fast matching policy first requires normalized base-title and main-artist
compatibility. It then uses version, album, and duration evidence to choose among
compatible recordings. It does not accept an otherwise incompatible identity just
because its duration or album matches. Ordinary parenthetical title text is
preserved; only recognized annotations are normalized.

This establishes a representative recording for credit exploration. It does not
verify the exact audio in the submitted library. Alternate titles, unknown artist
spellings, and bounded search pages can leave inputs unresolved.

The fixed audit of 100 sampled artist groups accepted **73/100**, with **18 HTTP
503 failures** and **9 no-compatible outcomes**. The denominator includes provider
failures because they affect whether the complete system can serve an input.
Acceptance is distinct from identity precision, which still needs independent
human review. See the [matching audit](../reports/mvp_matching_audit.md).

## Represent credits without inventing evidence

A recording describes a performance; a work describes a composition. The extractor
uses recording relationships for performance, production, and engineering, and
linked work relationships for songwriting. A shared work can identify a composition
across recordings when that evidence is present; equal titles cannot.

Credits retain their contributor identity, relationship type, scope, attributes,
work identity, and source URL. Eligible roles map to four categories:
musician, songwriter, producer, and staff. Several credits within one category
count once toward a contributor's weight, while distinct categories add together.
Unmapped evidence is retained for inspection.

Primary artist credits act as performance proxies. This permits some connections
when detailed credits are missing, but the proxy is not an observed instrument or
vocal credit. Group membership and missing participants are not inferred.

In the matching audit, only **31/73 accepted inputs** had additional eligible
credit evidence beyond the primary-artist proxy. That limits both coverage and
what a credit-based recommender can distinguish. An absent credit is missing
evidence, not proof that a contributor or role was absent. The audit alone does
not establish how missingness varies across genres, eras, or artists.

## Separate affinity from the final list

The current weights are musician **1**, songwriter **1**, producer **1**, and
engineering staff **0.25**. These are provisional choices, not learned importance.

For each favorite/candidate pair, the scorer multiplies the role weights of each
shared contributor and sums them to `x`. The bounded affinity `x / (1 + x)` reduces
the marginal influence of increasingly dense credits. It then averages affinities
within each favorite-artist group and applies `n / (n + 5)`, where `n` is the number
of distinct favorites in that group. More favorites increase influence with
diminishing returns. A collaboration can appear in multiple credited-artist groups.

In the illustrative fixture, Sega Bodega contributes producer, songwriter, and
engineering weights totaling **2.25** to TWELVE, and musician and producer weights
totaling **2** to Adulter8. The pair affinity is `4.5 / 5.5`; applying the
single-favorite influence of `1/6` yields **0.136364**. The
[worked example](method.md#worked-example) links to the frozen evidence.

The base score answers how strongly observed credits connect a candidate to the
favorites. List selection has a separate objective: distribute those connections
across a useful set of results. The demo and fast live path therefore use a
deterministic greedy selector that:

- Prefers feasible unrepresented source songs before second assignments, with at
  most two results assigned to each source group.
- Reduces a contributor's explanatory contribution by `1 / (1 + previous
  selected appearances)` when that contributor recurs.
- Applies familiar-act eligibility, excludes favorite recordings, avoids repeated
  observed performers and known works within the list, and permits at most one
  familiar collaboration.

Reports retain both base and selection scores, all supporting paths, and reasons
for skipped candidates. Balancing can select a lower-affinity candidate earlier.
Greedy selection is deterministic and inspectable, but it can miss a better
combination. Unknown work identities limit deduplication. None of these scores is
a probability of enjoyment.

## Retrieval sets the ceiling

Live exploration is bounded by request and runtime budgets. Matching consumes part
of the request budget; contributor discovery shares the remainder across source
groups. Failed transport attempts still consume capacity, and a supervisor can
terminate stalled collection while preserving partial results.

Three later ten-favorite cohorts returned **4/10, 3/10, and 4/10** recommendations.
All used the full **35-attempt** budget. Only three, two, and three source groups,
respectively, supplied eligible positive candidates. With at most two results per
source, those pools could supply at most six, four, and six results before other
conflicts. Ten results would require at least five productive source groups.

This makes retrieval coverage a prerequisite for filling the list. Changing the
scoring weights cannot supply candidates missing from the pool. The
[cohort report](../reports/different_seed_results.md) separates matching,
productive sources, representation, and final length.

The first later run also returned a livestream and a continuous mix. Both are valid
recording objects with credit connections, but they expose a mismatch between the
provider's recording universe and an individual-song discovery task. They remain
in the saved results. A format policy needs a declared treatment of mixes, live
recordings, long songs, and missing durations, followed by a separate comparison.

## What has been evaluated

The public 39-snapshot fixture was selected after inspecting readable paths. It
reproduces the complete scoring and selection process, returns five results, and
shows that equal and current weights can produce different lists: two results are
shared, giving Jaccard overlap `2/8 = 0.25`. It demonstrates behavior on that
fixture, without evidence of better recommendations.

On three historical frozen pools, equal and current weights produced identical
selected lists and order. All other policies were held fixed. Those experiments
show **no observed selection advantage** for the chosen weights on those pools;
they do not establish that role weighting never matters.

One listener reported **8/8 initial panel recordings enjoyable and 8/8 already
familiar**. That supports enjoyment for the reviewed panel while demonstrating
no unfamiliar-and-enjoyable discovery. Separate blinding was unverified, and
identical method lists prevented a preference comparison between weights.
The seven recordings from the first two later runs have **0/7 completed reviews**.

The repository also contains a declared-split evaluator that checks overlapping
recording identities, established equivalents, and primary artists. It reports
overall and reachable-target recall separately and can require training-bound
collection provenance. Its selection defaults differ from the demo's policy, so
those outputs need explicit policy labels before comparison. Evaluation machinery
and fixture checks are separate from validated preference results.

## Reproduction and the next experiments

Frozen snapshots and checksum manifests make the public calculation reproducible.
The offline demo uses the same scoring/selection functions as the fast live path.
The saved historical exports include enough context to recompute their base scores
and credit paths, but not the complete private pools and familiar-act registry
needed to replay historical selection. New live requests create new observations.

The most useful next experiments follow the observed limitations:

1. Independently review a fixed matching sample, separating wrong identities,
   unresolved versions, and provider failures.
2. Measure productive candidate coverage against request allocation and runtime on
   frozen cohorts, before changing relevance weights.
3. Declare and compare an individual-song format policy while retaining prior
   results and shortfalls.
4. Collect per-recording familiarity and enjoyment ratings, retaining pending
   denominators. Freeze candidate pools and selection policy for comparisons;
   isolate role weighting, proxy use, and reuse penalties in separate ablations.
5. Add a listening-behavior baseline when suitable data is available, and expand
   beyond one listener before making broader quality claims.

The current evidence makes metadata coverage and evaluation design the immediate
research priorities. See the [full results](results.md),
[architecture](architecture.md), and [roadmap](../ROADMAP.md).
