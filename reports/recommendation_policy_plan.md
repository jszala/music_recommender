# Discovery and recommendation-list design

Date: 2026-10-07. Policy: D-018, implementation: D-019.
Status: historical D-018/D-019 design, superseded in part by D-020/D-021 in
Milestone 4b. Shared explanatory contributors now have a hard one-song-per-batch
cap, and optional automatic Apple availability filtering precedes selection.
The soft-diversity discussion below records the earlier experiment. Independent
identity and listening review remain pending.

## Diagnosis from the saved sample

Before D-018, the scorer excluded favorite recording IDs, not favorite artists. Artist
saturation bounds each input artist's influence on one candidate; it places no
restriction on the complete recommendation list. All ten highest-ranked songs
have an input artist's primary credit, with nine belonging to one input act.

Of 36 candidates, 22 have a matched favorite artist's primary credit. The same 22
also match artist names somewhere in the full original input. An exploratory
greedy pass excluding these candidates and prohibiting repeated observed musicians
selects nine songs. This pass does not establish alias identities or audit the
collaboration exceptions. It demonstrates why filtering the existing sample alone
will not reliably supply the requested list length.

The original collection had a separate concentration problem: its six contributor slots were
allocated by raw counts of favorite recordings, and each contributor supplies only
six new recording IDs. Saturation is not used in these collection decisions.

## 1. Represent submitted acts and allowed exceptions

Add an artist registry bound to the original input hash. Preserve every submitted
artist name, verified artist IDs where available, original rows, and evidence for
identity decisions. Do not limit exclusions to the small accepted-recording batch.
For recording-ID-only use, derive the minimum registry from those favorite records.
Compare normalized submitted names as well as verified IDs; hold ambiguous identity
collisions for review rather than implicitly treating them as unfamiliar acts.

Represent permitted distinct aliases and side projects explicitly. A true alias
may share a canonical artist ID while being an allowed credited-act exception;
it still consumes the same musician identity in list selection. Case changes and
spelling variants do not independently qualify. Do not merge all projects through
group membership or infer that every group member played on a particular song.
Record explicitly identified related performers separately for the collaboration
allowance, without turning every contributor to a favorite into an excluded act.

## 2. Apply candidate eligibility independently of scores

Continue excluding favorite recordings and established equivalent appearances.
Ordinary recordings by a submitted act are ineligible regardless of their score.
Allow distinct aliases and side projects under the registry policy.

Classify verified collaborations separately: they must involve an unfamiliar
performing act, not only a familiar group's own member or a new engineer or writer.
Do not treat samples, covers, or ambiguous combined artist credits as sufficient
proof of a collaboration. Familiar artists appearing only as producers or other
nonperforming contributors do not invoke the collaboration allowance.

Keep a structured eligibility result with evidence and a rejection reason. Mark
eligible collaborations as sharing one global selection allowance, including the
explicitly identified related performers. Eligibility does not itself select them.

## 3. Select the complete list under hard constraints

Extract a set of observed active-musician IDs for each eligible recording: primary
artist, performer, instrument, and vocal credits. Deduplicate identities within
each recording. Production, engineering, writing, and artwork alone do not reserve
musician appearances. Preserve the distinction between primary-credit proxies and
detailed performance evidence in the coverage report.

Start with deterministic greedy selection from positive-score eligible candidates.
Reject a candidate if any musician is already in the selected list, or if it would
consume a second familiar-artist collaboration. Selecting a collaboration reserves
all of its musicians. Retain skipped-candidate reasons and return fewer than the
requested number when necessary; never relax either constraint to fill the list.
Greedy selection is a simple baseline, not a claim to maximize total list score or
find every possible full-length list.

## 4. Address concentration during collection and selection

Balance contributor exploration across favorite-artist groups rather than sorting
all contributors by raw song counts. Use deterministic round-robin allocation
across groups as the first baseline, deduplicating contributors chosen through
multiple groups. Keep musician, songwriter, producer, and staff routes eligible.
Document omissions when the budget cannot cover all groups or contributors.

Reject obvious familiar-act recordings from browse metadata before spending detail
lookups. Recheck eligibility after full credit retrieval. Continue through the
available pool and further permitted pages when candidates are rejected, until an
eligible-candidate target or the explicit request/page budget is reached. Preserve
snapshots and exclusion evidence so offline replay reproduces the result. Record
performer conflicts as a reason that a pool may need further expansion.

Keep the existing per-input-artist saturation; changing its half-saturation value
alone cannot satisfy the new policy. Compare the hard-constraint baseline with a
separate soft reduction for repeatedly using the same explanatory contributors
across picks. A proposed initial rule divides each contributor's candidate evidence
by one plus the number of already selected songs explained by that contributor.
Apportion each pair's score among contributors in proportion to their raw credit
products, so the apportioned evidence still sums to the original score.

Recompute this selection score after each pick. Contributors remain positive
evidence, including recurring engineers and producers; only repeated performers
face a hard prohibition. Retain both base affinity and selection adjustments in
the output. This numerical diversity rule is an implemented opt-in comparison,
not a tuned or preference-validated choice; the default applies the hard rules without it.

## 5. Update evaluation, tests, and review output

Use complete-primary-artist holdouts for ordinary discovery evaluation. Keep
multi-artist recording overlaps and established recording equivalents out of both
training and held-out sides; report any exclusions needed to achieve this split.
Build exclusion registries from training rows only, never from held-out membership.
Use the same eligibility and list-selection policy for every scoring comparator.

Report overall and reachable recall, in-graph and policy-eligible targets, selected
list length, repeated musicians, familiar collaborations, and concentration of
explanatory contributor evidence. Distinguish candidates that are eligible from
those omitted because they conflict with an already selected musician. Retain old
diagnostics with an explicit historical policy label rather than comparing unlike
objectives.

Required regression cases:

- Familiar-act tracks are excluded even when their score is highest or their input
  recording was not accepted by the matcher.
- Allowed aliases and side projects remain eligible; canonical aliases share one
  musician appearance. Case changes do not evade exclusion.
- One verified familiar collaboration is allowed across the whole list; a second
  is rejected, including when it uses an explicitly related performer instead of
  the original group. Group/member credits alone do not qualify.
- A repeated vocalist, instrumentalist, featured performer, or primary artist
  cannot occur on a second pick. Multiple roles on one recording count once.
- A shared producer or engineer may connect multiple selected tracks when they do
  not perform on those tracks. A producer who also performs consumes an appearance.
- An exhausted pool produces a documented shortfall and deterministic replay.
- Duplicating favorite rows or credits does not increase influence. Additional
  distinct favorites have bounded impact; collection allocation and soft list
  diversity are measured separately from that mathematical bound.
- Evaluation registries do not leak held-out artists, and all comparison methods
  obey the same hard policies.

Finish by regenerating the private source-review list with exclusion counts,
observed-musician sets, the collaboration allowance, and selection explanations.
Review identities and credits before interpreting any change as better listening
quality. No new live collection is needed to establish the first regression tests.

## Verified implementation results

The old graph now selects eight compliant songs, with an explicit shortfall of two.
Balanced collection around the same nine favorites produces 44 eligible candidates
in 117 paced requests without failures. A new weighted list selects ten songs with
one familiar collaboration and 31 distinct observed musicians. All four methods
obey the hard constraints; contributor diversity changes two positions but retains
the weighted list's membership. Offline replay reproduces collection and ranking
with zero network requests. Source-linked review files are in the ignored private
discovery-graph directory. Full-input name coverage includes all 425 submitted
artist names; only six primary-artist IDs are recording-backed so far.
