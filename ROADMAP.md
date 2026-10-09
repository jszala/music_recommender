# From the offline demo to a live application

The current release is an offline demonstration and work in progress. Bounded collection exists as research tooling; there is no deployed service.

1. Declare an individual-song format policy for continuous mixes, livestreams, long songs, alternate versions, and missing duration evidence. Preserve current outputs and evaluate this policy separately.
2. Measure retrieval coverage against request/runtime tradeoffs on frozen cohorts, keeping weights and hard constraints fixed. Retain failures and shortfalls.
3. Collect explicit familiarity/enjoyment reviews for every delivered recording, retaining pending items. Evaluate a real listening-behavior recommender as a separate experiment with shared inputs/pools where feasible.
4. Serve the same report through a small API. Keep collection/enrichment, matching, scoring/selection, and rendering separate. Add provider pacing/caching, partial-result and error states, and deliberate private-input handling.
5. Consider hosting, authentication, a local metadata database, and multi-user evaluation when measured needs justify them. A database cannot create missing credits or prove listening usefulness.

Do not retune weights or weaken constraints while polishing the demo. Each methodological change needs its own question, controlled comparison, and retained prior result.
