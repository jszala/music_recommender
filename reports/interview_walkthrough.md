# Five-minute interview walkthrough

This is a local portfolio demonstration. Start at the repository root with
`python3 -B -m src.demo`. Use the public example for the screen demonstration;
keep private favorites, contact details, and listening sheets off screen.
The public favorites were deliberately chosen to make the connections readable.

Latest evidence: [three different-favorite-song cohorts](different_seed_results.md)
returned 4/10, 3/10, and 4/10 recordings under the fixed model. No list reached ten;
two outputs were a livestream/continuous mix. New listening ratings are pending.
Use this as an additional failure example: correct credit connections and fast
execution do not guarantee individual-song suitability, coverage, or novelty.

## 0:00–0:40 — The question

“I wanted to test whether the people credited on songs I enjoy can help me find
other music I might enjoy. A producer, songwriter, musician, or engineer can
connect songs whose main artists are different. Each recommendation should
explain which favorite led to it and which observed credits support that path.

“This is a small case study for one listener. My goals were a reproducible demo,
bounded live collection, and an evaluation that separates matching, coverage,
enjoyment, and novelty.”

## 0:40–1:40 — Show one connection

Run the offline demo and show the five songs and three represented source groups.
Open [the worked list](mvp_demo.md) for the Shygirl connection.

“Shygirl's TWELVE connects to Sega Bodega's Adulter8 through Sega Bodega's
observed credits. On the favorite, eligible credits fall into production,
songwriting, and staff categories. On the recommendation, the observed
categories are musician and production. The saved metadata supports both sides
of that connection, and the output includes the recording and person links.

“The data model distinguishes recordings, which are performances, from works,
which are compositions. Songwriting comes from linked works; other roles come
from recording relationships. Primary artist credit is a disclosed performance
proxy. I do not infer missing credits or membership of a band.

“This public example is illustrative. It shows how the method behaves, and
its hand-picked inputs are disclosed. The evaluation uses separate live pools.”

## 1:40–2:40 — Explain scoring and selection

“The current weights are one for musician, songwriter, and producer, and
0.25 for staff. A role category contributes once per person on each recording.
For a shared person, I multiply the two recordings' role totals. Here that is
2.25 times 2, or 4.5. I transform the summed value x with x/(1+x), then average
within favorite-artist groups and apply diminishing influence n/(n+5).
Here the final base affinity is about 0.136.

“These are provisional assumptions, not learned parameters or probabilities
of enjoyment. Equal role weights are the baseline.

“List selection has a separate purpose. It first represents feasible source
songs before giving one source another slot, caps each source at two results,
penalizes repeated explanatory people, keeps observed performers unique, and
deduplicates known compositions. Each result receives one supported source
assignment while retaining every credit connection. The selector is deterministic
and greedy; it can miss a better combination.”

## 2:40–3:40 — Explain the evidence

“I froze 100 sampled input rows before measuring matching. Seventy-three were
accepted. Eighteen failed because the provider returned HTTP 503, and nine had
no compatible result. The 90% acceptance target was missed. Among accepted
rows, 31 had additional eligible contributor credits, so matching and credit
coverage are separate quantities. Independent human precision review is pending.

“Three fresh recommendation runs used fixed sampling seeds and the same request
and time limits. They returned five, three, and three songs, each across three
source groups, in approximately 38 seconds with 35 attempts per run. Those
results establish bounded operation and the behavior of the selection policy.

“Equal and current weights selected identical lists on the same frozen live
pools. The listener reported all eight reviewed songs enjoyable and familiar.
That is eight out of eight liked, but zero new-to-listener discoveries. The
feedback was one bulk report, without verified blinding. It cannot establish
that the current weights are better or that this generalizes to other listeners.”

## 3:40–4:25 — Show a failure and the follow-up

“The submitted favorites are incomplete evidence of what a listener knows.
Excluding artists and songs found in that input did not make these suggestions
unfamiliar. I kept that failure visible and prepared a follow-up using the first
saved candidate pool, with the eight explicitly known recordings excluded.
Scores and selection constraints stayed fixed. The protocol was saved before
selection; the pool supplied four of five requested songs across three groups,
without new requests. Their familiarity and enjoyment ratings are pending.

“That follow-up also exposed why recording IDs alone are insufficient: three
results repeat an earlier primary artist, and the fourth repeats a known
composition with a different artist. The next policy choice is whether discovery
should require different artists as well as different compositions.”

“Matching also has concrete limits: a saved input with a `12-inch Version`
annotation was not reduced to its base title. Broader literal searches retained
that wording. I would investigate a bounded normalization change and its false
matches, rather than use unrestricted fuzzy matching to reach the target.”

## 4:25–5:00 — Engineering and next investment

“The public demo uses source-linked snapshots with checksums and the same scoring
and selection functions as live recommendations. Live collection charges attempts
before transport, respects pacing and backoff, has no automatic retry, and uses
a supervisor to stop stalled transport while preserving partial evidence.
Offline tests cover identity, scheduling, selection, provenance, and failure modes;
the CI checks need no private input or provider access.

“My next investment is to review novelty and identity correctness, then determine
whether retrieval coverage is the remaining obstacle. A database import and
hosting are deferred. The current local demo already answers the engineering
question; the research claim stays limited to the evidence.”

## Answers to likely follow-ups

- **Why these weights?** They encode an explicit hypothesis about shared creative
  roles. The live comparison provides no evidence favoring them over equal weights.
- **Why can a familiar artist appear?** Full-input artist exclusions allow one
  observed familiar collaboration. Artists absent from the favorites may also be
  familiar to the listener; the eight-song review exposed that gap.
- **Why not always return fifteen songs?** With three productive source groups,
  the two-per-group cap permits at most six. Other constraints can reduce that
  further. The system reports the shortfall.
- **What does a failed search mean?** It records the bounded provider response;
  it does not prove that a recording is absent from the catalog.
- **What would you measure next?** Familiarity and enjoyment on the frozen follow-up,
  human identity judgments on the fixed inspection sample, and coverage separately.
  An artist holdout would be a later experiment with retrieval and exclusions
  restricted to training inputs and composition leakage controlled.
