# Optional research tooling

The default experience is the offline [demo](../README.md). These optional tools collect bounded live evidence or inspect saved pools; they do not run a deployed service. Keep inputs, contact files, caches, snapshots, and ratings under ignored `data/private/`. Use new output directories; preserve old observations.

Version-1 favorites JSON uses `line_number`, `artist_text`, `song_text`, with optional album/duration. A MusicBrainz contact email/URL file is required for provider access.

```bash
python3 -B -m src.quick_recommend --input data/private/favorites.json --random-seed 3 --contact-file data/private/musicbrainz_contact.txt --output data/private/new_run
python3 -B -m src.check_apple_music --recommendations data/private/new_run/recommendations.json --country DE --output data/private/new_run_apple
```

Defaults: eight sampled groups, up to 15 recordings, 35 charged attempts, 55-second engine budget. Sampling weights 1/2/3 for 1/2–10/>10 distinct likes affect sampling only, followed by one uniformly selected song per group. Matching gets at most 20 attempts; remaining capacity goes to discovery in source-group rounds. Full-input exclusions remain active.

Calls use fresh responses, within-run deduplication, shared 1.1-second pacing, attempts charged before transport including failures, disabled retries/redirects, and observed backoff. A supervisor ends stalled collection. Partial evidence, shortfall, source target, and stopping reasons remain visible. Live tooling requires POSIX processes/locking. Separate Apple checks preserve membership/order; no confident match does not prove catalog absence. Historical catalog-filtering workflows remain available to existing callers but are not used by offline rendering.

```bash
python3 -B -m src.compare_methods --runs data/demo --output /tmp/music-credit-comparison
python3 -B -m src.compare_methods --runs data/private/new_run --output data/private/new_comparison
python3 -B -m src.compare_methods --review data/private/new_comparison --ratings data/private/new_comparison/ratings.csv
```

Fill `LISTENING_REVIEW.md`/blank ratings before viewing labels/scores. Familiarity and enjoyment complete a rating; save intention is optional. Tools never invent ratings and keep pending denominators. `prepare_export_review` includes all recordings from actual exports without reranking; historical five-result comparisons stay separate.

```bash
python3 -B -m src.compare_methods --runs data/private/new_run --known-review data/private/new_comparison --output data/private/new_followup
python3 -B -m src.benchmark_matching --contact-file data/private/musicbrainz_contact.txt --output data/private/new_matching_audit --sample-size 100 --random-seed 42
python3 -B -m src.benchmark_recommendations --random-seeds 3 4 5 --seed-counts 8 --repeats 1 --contact-file data/private/musicbrainz_contact.txt --output data/private/new_benchmark
python3 -B -m src.different_seed_experiment --help
```

A follow-up uses one pool and a completed prior review, freezes exact-ID exclusions before selection, and preserves the original review. Such exclusions do not guarantee unfamiliar artists/compositions. Cohort preparation binds input/reference/implementation hashes before running, verifies samples, and refuses existing directories. No live recommendation calls were made for this visual release. [Results](results.md) retain past observations; [the roadmap](../ROADMAP.md) names separate next experiments.
