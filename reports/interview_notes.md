# Explaining the project in an interview

Use the [five-minute walkthrough](interview_walkthrough.md) to rehearse the public
demo, one recommendation, the measured results, and the discovery failure.

## The question and approach

Can the people credited on songs I enjoy help me discover unfamiliar acts?
This is an explainable graph recommender over recording-to-contributor relationships.
It explores one listener's favorites; the observations do not represent all listeners.

The four steps are representative song matching, contributor-based retrieval,
credit-affinity scoring, and diverse list selection. Retrieval and ranking are
separate: a strong scoring method cannot recover a recording absent from its pool.

## What the data means

A recording is an audio performance; a work is its composition. Musicians,
producers, and engineers come from observed recording relationships. Songwriters
come from linked works. A primary credited artist supplies a separately disclosed
performance proxy. Group membership and unobserved credits are never inferred.

Song matching checks normalized title and main artist. Release editions and
duration help choose a representative recording. This supports discovery without
claiming verification of the exact audio originally liked. A successful match
can still have no additional contributor credits in the returned response.

## How the score works

Each contributor receives one weight per distinct role category: musician 1,
songwriter 1, producer 1, staff 0.25. Repeated instrument rows do not add units.
For a favorite/candidate pair, multiply each shared contributor's two weights,
sum those products as x, and use x/(1+x). This bounds a dense credit connection.

Average pair affinities within each favorite artist and multiply by n/(n+5),
where n is its distinct favorite recordings. This gives additional favorites
diminishing influence. With one favorite per artist this factor is 1/6; it does
not differentiate single-song artist groups. Multi-primary credits can create
overlapping artist groups, which are preserved in explanations.

These weights and the constant 5 are provisional fixed assumptions. Staff's
lower weight expresses a hypothesis about preference relevance; credits do not
prove creative importance. Equal category weights are the baseline. Scores are
credit affinities, rather than calibrated probabilities of enjoyment.

## Why list selection is separate

Every submitted artist informs familiar-act exclusions, even when its songs
cannot be matched. Selection retains observed performer uniqueness and allows
at most one familiar collaboration. Reusing an explanatory contributor reduces
its selection contribution by 1/(1+previous appearances).

The source-balancing policy first gives feasible unrepresented source songs an
appearance and permits at most two assignments per source group. Each result
gets exactly one supported assignment while retaining every observed connection.
Known shared work IDs prevent multiple covers of a composition filling the list.
Unknown work identities remain unresolved. Deterministic greedy choices can
block a better combination; optimal assignment and adaptive scheduling are later work.

## What the evaluation can establish

Matching acceptance, credit coverage, source coverage, list length, and runtime
are separate diagnostics. They cannot demonstrate enjoyment. Compare baseline
and current weights on identical frozen candidates and selection constraints.
For a new review, assess the predetermined union of their suggestions without
seeing method names or scores. Report familiarity and enjoyment with denominators
as a small single-listener case study; save intention is optional.

For the current panel, the listener reported all eight songs familiar and enjoyable
in one bulk assessment. A separately blinded session was not verified. This gives
8/8 liked and 0/8 previously unfamiliar; it supports enjoyment of this panel but
does not demonstrate discovery novelty. Both methods selected identical songs,
so these ratings provide no evidence favoring either set of weights. A song absent
from the submitted favorites can still be known to the listener. The next focused
experiment now excludes the eight known recording IDs from the first saved pool,
with its protocol fixed before selection. Four of five requested songs were
feasible, across three groups; their ratings are pending. Scores stayed fixed.
Exact recording exclusions do not establish that another version is unfamiliar.
Keep the original result visible when reporting the follow-up.

An artist holdout would require training-only candidate retrieval and exclusions,
with compositions kept together across splits. An item absent from favorites
is not a negative preference label. This experiment remains later work.

## Engineering choices and next investment

Offline snapshots make the demonstration deterministic and source-auditable.
Live runs obtain fresh responses, charge requests before sending, share only a
pacing gate between runs, and terminate stalled transport using a process supervisor.
Partial lists explain what stopped collection. Unit and integration tests cover
the policies and failure modes; CI needs neither private inputs nor provider access.

A database import is a potential next investment if measured retrieval limits
justify it. It could speed local lookup but would not add missing credits or
establish listener usefulness. Paid hosting is separate from a local research demo.
