# Full-library collection coverage

Status: **cancelled at the user's request**. Both the active collector and its queued continuation have stopped. The public API is not feasible for this project's full-library matching, broad contributor discovery, and repeated experiments. The captured coverage is incomplete; completed checkpoints and caches remain preserved. See D-024 in [the decision log](../DECISIONS.md).

Updated: 2026-10-07T18:53:16.681671+00:00.

These counts describe collection coverage. Independent identity precision and listening quality remain pending.

Supplied rows: 1316; processed: 529; accepted rows: 187; distinct accepted recordings: 187; accepted primary artists: 156.
Unresolved: 342; operational failures: 9; not attempted: 777; in progress: 0; interrupted: 1.

Stage states: matching: cancelled.

| Provider stage | Attempts | Remaining allowance | Tranches started |
|---|---:|---:|---:|
| apple | 0 | 2000 | 1 |
| discovery | 0 | 6000 | 1 |
| matching | 1663 | 14337 | 14 |

First additional 100 rows:

```json
{
  "elapsed_seconds": 434.9017717519964,
  "http_attempts": 320,
  "remaining_seconds_estimate": 5201.425190153877,
  "rows": 100
}
```

Matching, credit, discovery, availability, recommendations, and ordered playlist preparation remain in the ignored private job directory.

Cancellation recorded at 2026-10-07T18:53:16.515301+00:00, after about 46.8 minutes. Discovery, expanded Apple checks, full-profile recommendation exports, and complete live offline replay did not run. The existing recommendation list remains the historical pilot.
