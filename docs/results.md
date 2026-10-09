# Results and interpretation

This is an offline production-credit demo and work in progress. Public fixtures demonstrate behavior; private research runs supply the aggregates below. Personal inputs/ratings are excluded. Historical live observations cannot be exactly reproduced without private frozen responses; new provider calls are new observations.

## Main findings

The research question is whether contributor credits support useful music
discovery. The current evidence establishes reproducible score explanations and
documents retrieval limitations, while leaving recommendation-quality improvement
unproven.

| Question | Observation | Consequence |
|---|---|---|
| Can submitted songs be matched reliably enough for discovery? | 73/100 accepted in the fixed audit; 18 provider failures; 9 no-compatible outcomes | The 90% acceptance target was missed; independent identity precision remains unmeasured. |
| Is additional credit evidence available? | 31/73 accepted audit inputs had eligible evidence beyond the primary-artist proxy | Many inputs offer little observed contributor context. |
| Do the current weights improve selection? | Equal/current lists and order were identical on three historical frozen pools | No selection advantage was observed on those pools; preference superiority is unestablished. |
| Are reviewed suggestions useful discoveries? | One listener reported 8/8 enjoyable but 8/8 familiar | The reviewed panel showed enjoyment without unfamiliar-and-enjoyable discovery. |
| Can later runs fill a ten-result list? | 4/10, 3/10, and 4/10 delivered; all hit the 35-attempt ceiling | Matching, productive-source coverage, and selection conflicts constrain delivery. |

The constructed offline fixture demonstrates different behavior under equal and
current weights, but was selected for exposition. It is separate from the
historical pool comparisons and listener evidence. The [case study](case_study.md)
connects these findings to design decisions and the next experiments.

## Metric definitions

| Metric | Definition | Boundary |
|---|---|---|
| Matching acceptance | Accepted / all sampled rows, including provider failures | Not independently audited identity precision or exact-audio accuracy. |
| Additional-credit coverage | Accepted rows with eligible credits beyond the primary-artist proxy / accepted rows | Missing evidence does not prove missing contributors. |
| Delivered length | Returned / requested recordings | Retain shortfalls; a recording may be a mix or livestream. |
| Productive groups | Matched groups with an eligible positive candidate / matched groups | Does not guarantee feasible selection; some historical exports retain only the numerator. |
| Represented groups | Groups assigned a selected result / matched groups | Separate from configured target; coverage is not listening quality. |
| Structural overlap | Selected recordings sharing recording, credited-artist, or observed-work IDs / selected recordings, against a declared reference | Report dimensions separately; unknown works limit composition claims. Different IDs do not prove unfamiliarity. |
| Complete-call runtime | Sampling, collection, scoring, export, and return time | State budget/stopping reason; not production latency. |
| Charged requests | Every transport attempt, including failures | Stage allocation is separate; provider conditions matter. |
| Listener usefulness | Familiar, enjoyable, unfamiliar-and-enjoyable counts / explicitly reviewed recordings | Pending items stay visible; one listener does not establish generalization. |

## Public illustration and matching

The 39-snapshot, three-favorite illustration returns **5/5 across three assigned groups** (2/2/1). Both methods return five and share two recordings: Jaccard 2/8 = 0.25. This demonstrates weight sensitivity in a selected fixture, without preference evidence. One weighted result has unknown work identity. This is the runnable `src.demo` example introduced in the [README](../README.md). The [saved historical results](../data/recommendations/README.md) retain all 11 outputs from three later runs.

The [fixed audit](../reports/mvp_matching_audit.md) froze 100 sampled artist groups (one song each, integer 42) before thirteen bounded fresh batches: **73/100 accepted, 18/100 HTTP 503 failures, 9/100 no-compatible outcomes**. The 90% acceptance target was missed. Additional-credit coverage was **31/73 accepted rows**; 42/73 had no additional evidence. Total complete calls took 205.90 seconds and 187 attempts. Conditional 73/82 among non-failure rows does not replace 73/100.

Codex inspected accepted title/main-artist metadata; exact audio and independent human precision remain unverified. The fixed ten-identity human sample has **0/10 judged, 10/10 pending**. Unrecognized version wording, literal alternate titles/artist spellings, and bounded search pages remain failure sources.

## Earlier live runs and within-method baseline

Integers 3/4/5, eight sampled artist groups, 35 attempts, and a 55-second engine budget were fixed before collection. All stopped at the request ceiling; times cover complete calls.

| Integer | Accepted / sampled | Additional credits / accepted | Delivered / requested | Represented / matched | Runtime | Attempts |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 4/8 | 3/4 | 5/15 | 3/4 | 38.132 s | 35/35 |
| 4 | 4/8 | 0/4 | 3/15 | 3/4 | 38.787 s | 35/35 |
| 5 | 7/8 | 5/7 | 3/15 | 3/7 | 38.663 s | 35/35 |

All met the three-source target with zero repeated observed performers. Matching/discovery attempts were 12/23, 14/21, 16/19. Known-work exclusions were 4/4/1; unknown selected works were 2/5, 0/3, 1/3. Primary-artist proxies can supply routes despite no additional observed seed credits. [The aggregate report](../reports/mvp_results.md) retains assignments and protocol.

Equal/current weights shared frozen pools, top-five limit, and all other policies. **Lists and order were identical on all three pools**, Jaccard 1.0 each. No selection advantage was observed. This is a within-credit comparison; a listening-behavior baseline is not implemented.

The first two declared pools supplied eight panel recordings. One bulk listener report gave **8/8 enjoyable, 8/8 familiar, 0/8 unfamiliar**, hence 0/8 unfamiliar-and-enjoyable. Separate blinding was unverified; save intention was uncollected. Identical method lists prevent distinguishing weights. The result supports enjoyment for this listener/panel without demonstrated discovery.

A separately frozen adaptive follow-up excluded those eight IDs and replayed the first pool without new requests/changed base scores: **4/5 delivered, 0/4 rated, 4/4 pending**. Three of four repeated a credited artist; the fourth shared an observed composition with an original suggestion. Exact-ID exclusions were too narrow for structural discovery across reviews. Missing releases left album overlap unresolved.

## Different favorite-song cohorts

Before collection, integers 6–35 were considered in ascending order; the first three ten-favorite cohorts disjoint in normalized main-artist/base-title identity against earlier samples and each other were frozen: **6, 9, 10**. All 30 seed identities differ. Credits/provider outcomes did not influence cohort selection. Full-input exclusions, weights, caps, and stopping rules stayed fixed. Eight versus ten seeds and different provider responses make cross-run observations descriptive, rather than causal improvements.

| Integer | Accepted / sampled | Additional credits / accepted | Productive / matched | Represented / matched | Delivered / requested | Runtime | Attempts |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6 | 7/10 | 4/7 | 3/7 | 3/7 | 4/10 | 38.620 s | 35/35 |
| 9 | 5/10 | 5/5 | 2/5 | 2/5 | 3/10 | 38.166 s | 35/35 |
| 10 | 6/10 | 2/6 | 3/6 | 3/6 | 4/10 | 38.783 s | 35/35 |

All hit the ceiling. Matching was 18/30, with eight HTTP 503 failures and four no-compatible outcomes. Matching/discovery attempts were 18/17, 18/17, 17/18. Productive counts bound list length at six/four/six under the source cap before other conflicts; ten requires at least five productive groups. Run 2 missed the three-source target by one. Run 1 retained a 149.45-minute livestream and 120-minute continuous mix. No replacement or retrospective format filter was applied.

Reference: union of all three original lists and the four-recording follow-up.

| New integer | Recording overlap | Credited-artist overlap | Observed-work overlap | Unknown selected works |
|---|---:|---:|---:|---:|
| 6 | 1/4 | 1/4 | 0/4 | 3/4 |
| 9 | 0/3 | 0/3 | 0/3 | 0/3 |
| 10 | 0/4 | 0/4 | 0/4 | 1/4 |

New lists share no observed recording, credited-artist, or work IDs with each other. Unknown works prevent complete composition claims; different IDs do not prove listener unfamiliarity. Missing releases affect 4/4, 1/3, 4/4 results, leaving album overlap unresolved.

The first two new runs were declared for listening in advance. All seven delivered recordings are in the review: **0/7 reviewed, 7/7 pending**. The latest “good list” comment is qualitative feedback, without seven completed per-track ratings, verified unfamiliarity, or baseline superiority. [The cohort report](../reports/different_seed_results.md) retains the protocol and full-export checks.

## Reproducibility boundary

The preceding checkpoint passed **222 offline tests**, including a clean copy without private data. Both public methods ran and repeated weighted JSON was byte-identical. Remote CI was configured but not reported as run. Earlier counts/times (24, 211, 212, 215) remain in historical aggregate reports. Tests verify implementation, rather than recommendation quality.

[Current release verification](verification.md) records new checks separately. Public commands reproduce the illustration, arithmetic, checksums, determinism, and review tooling. Historical personal live pools/ratings are summarized here, without being bundled. New listener reviews and a real listening-behavior baseline remain separate experiments.
