# Representative matching checkpoint, 2026-10-08

**73 of 100 frozen sampled rows were accepted (73%). The 90% target was missed.**
This checkpoint was recorded before implementing the new discovery and selection
policies. The previous prototype's three comparison runs accepted 7/24 sampled rows;
those used different samples and provider conditions, so this is not a controlled
estimate of improvement.

## Protocol and outcomes

Weighted sampling selected 100 distinct artist groups, one song per group, with
random seed 42. The complete input hash, ordered source rows, and sampling rules
were saved before collection in the private sample manifest. Thirteen fixed
batches of at most eight used the production matcher, fresh response stores,
shared pacing, the 20-of-35 matching allocation, and the normal 55-second worker
budget. There was no discovery, re-sampling, automatic retry, or replacement of failures.

| Outcome | Sampled rows |
|---|---:|
| Accepted | 73 |
| Provider failure, HTTP 503 | 18 |
| No compatible candidate | 9 |
| Invalid response / budget / interruption | 0 |
| Total denominator | 100 |

There were 73 distinct accepted recording IDs. Thirty-one accepted rows had
additional eligible direct or work-level contributor credits; 42 had no such
credits observed. This does not establish complete credits or guarantee useful
candidate routes. The primary artist remains a disclosed performance proxy.

The experiment charged 187 attempts and took 205.90 seconds across complete calls.
The conditional acceptance fraction among rows without provider failure was
73/82 (89.0%); it does not replace the primary 73/100 rate. Provider failures alone
prevented reaching 90% in this observation.

## Inspection and limits

Codex inspected the input and chosen title/artist table for all 73 accepted rows.
No obvious unrelated song or main artist was found in that metadata inspection.
It covered Unicode/apostrophe normalization, omitted feature annotations,
structured multi-artist credits, remasters, and requested remix wording.
One alternative version received an explicit notice: a requested Tom Moulton
mix resolved to a representative unmarked recording. Exact audio identity and
independent human precision auditing remain unverified.

The nine unresolved rows include alternate artist spelling/identity, unrecognized
version wording, abbreviated multi-part titles, literal censored titles, and
compatible candidates absent from the bounded first search page. These are
remaining causes to investigate, rather than justification for unrestricted
fuzzy matching or accepting a guest-only identity. The retained responses
describe what was observed; a missing search result does not prove catalog absence.

## Prepared independent inspection

A uniform sample of ten accepted rows was drawn without replacement from the
73 accepted rows in their frozen order, using random seed 42. Its source hashes
and one-based sample positions are saved under
`data/private/mvp_identity_review_2026-10-08/`. `accepted_identities.csv` includes
input and chosen title/artist metadata, source links, version notices, and blank
human judgment fields. `failure_cases.csv` contains all nine no-compatible cases,
with original diagnostic rows in `failure_evidence.json`.

Human inspection is pending: **0/10 judgments recorded**. This preparation does
not change the 73/100 acceptance result or certify exact audio identity. Report
verified, incorrect, unsure, and pending identities out of ten separately from
matching acceptance; provider failures stay in the original denominator.

## Reproduce and inspect privately

```bash
python3 -B -m src.benchmark_matching --contact-file data/private/musicbrainz_contact.txt --output data/private/new_matching_audit --sample-size 100 --random-seed 42
```

Original evidence is under `data/private/mvp_matching_2026-10-08/`:
`sample_manifest.json`, `identities.csv`, `summary.json`, and per-batch immutable
request/response/recording evidence. A repeat is a new observation, never a
replacement for selected failed rows. Private source rows and contact information
are not distributed with the public demonstration.
