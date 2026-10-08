# Music-credit recommendations

Discover unfamiliar songs through the people credited on favorites, with an explanation for every recommendation. The pipeline matches representative songs, retrieves contributor-connected recordings, scores shared credits, and selects a list balanced across source songs.

**Current result:** three fresh cohorts of different favorite songs returned **4/10, 3/10, and 4/10 recordings** in 38.2–38.8 seconds under unchanged scoring and constraints. None reached ten; two outputs were long-form recordings rather than individual songs. New listener ratings are pending. The offline example returns five songs from three source groups. A fixed 100-row matching audit accepted 73 rows, below its 90% target. Equal and current role weights selected identical lists on the three earlier live candidate pools. **The listener reported liking all eight earlier reviewed songs, but all eight were already familiar.** This is a single-listener portfolio case study with provisional heuristic scores; discovery usefulness remains unestablished. See [the different-seed experiment](reports/different_seed_results.md).

## Quick start

From a fresh checkout, use Python 3.12 or later. The demonstration needs no installation, private files, provider account, network access, or hosting.

```bash
python3 -B -m src.demo
python3 -B -m src.demo --method equal
python3 -B -m src.demo --format json
python3 -B -m unittest discover -s tests -v
```

The [public example](data/demo/README.md) contains 39 frozen, source-linked recording snapshots and three constructed favorites. It was chosen to show readable paths and multiple productive sources; it is not a random evaluation sample. Repeated offline runs produce identical output. JSON retains every connection, role, score transformation, and source assignment.

For an interview presentation, use the [five-minute walkthrough](reports/interview_walkthrough.md).

## One worked recommendation

Shygirl's **TWELVE** connects to Sega Bodega's **Adulter8** through Sega Bodega. The [favorite recording](https://musicbrainz.org/recording/08d4b15e-5945-45f6-9ed2-d5490c53de4c) has eligible production, songwriting, and staff credits for him; the [candidate recording](https://musicbrainz.org/recording/0927e3e5-0664-4a24-89de-b24c3c911b6a) has musician and production evidence.

His favorite weight is 1 + 1 + 0.25 = 2.25 and candidate weight is 1 + 1 = 2. Their product is 4.5. The bounded pair affinity is 4.5/(1+4.5), and single-favorite artist influence is 1/(1+5). The base score is **0.136364**. Selection preserves that base score and records separate diversity adjustments. This is a shared credit connection, rather than a probability of enjoyment. See [the complete public list](reports/mvp_demo.md).

## Data and method

```mermaid
flowchart LR
    A[Favorite songs] --> B[Representative song matching]
    B --> C[Observed contributor credits]
    C --> D[Candidate retrieval]
    D --> E[Credit-affinity scoring]
    E --> F[Source-balanced song list]
    F --> G[Explanations and review]
```

Recordings represent performances; works represent compositions. Performance, production, and engineering evidence comes from recording relationships; songwriting comes from linked works. Primary artist credit supplies a disclosed performance proxy. Group members and missing credits are never inferred.

Matching requires compatible normalized song title and main artist. Unicode, punctuation, and recognized trailing annotations are normalized. Album, duration, and observed version labels rank compatible representatives. Exact audio identity is unverified, and alternative versions are disclosed. Historical matching commands retain conservative rules.

The scorer adds one weight per distinct category on each recording: musician **1**, songwriter **1**, producer **1**, and staff **0.25**. Shared contributors' weight products sum to x; x/(1+x) bounds each pair affinity. Average within favorite-artist groups and multiply by n/(n+5) to give additional favorites diminishing influence. These are fixed provisional assumptions; equal weights set every category to 1. With one favorite per artist, the artist factor is 1/6 and does not differentiate those groups.

Selection excludes submitted familiar acts and favorite recording IDs, keeps observed performers unique, and allows at most one familiar collaboration. Repeated explanatory contributors receive 1/(1+previous appearances). Each result gets one supported source assignment. Feasible unrepresented sources precede second appearances; each group receives at most two results. Equal nonempty work sets group equivalent seeds; overlapping known work IDs exclude duplicate compositions. Unknown compositions remain unresolved. Greedy selection can miss a better combination.

## Measured evidence and failures

| Fresh run, random seed | Matches / 8 | Additional-credit seeds | Represented sources | Songs / 15 | Complete runtime | Requests |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 4 | 3 | 3 | 5 | 38.13 s | 35 |
| 4 | 4 | 0 | 3 | 3 | 38.79 s | 35 |
| 5 | 7 | 5 | 3 | 3 | 38.66 s | 35 |

All three hit the request ceiling. Known-work uniqueness excluded 4, 4, and 1 candidates. Matching, additional credits, useful retrieval, and selected coverage are separate quantities. A primary-artist proxy can connect to other roles even when a seed has no additional credits.

The [matching audit](reports/mvp_matching_audit.md) accepted 73/100 frozen rows: 18 HTTP 503 failures and nine no-compatible outcomes account for the rest. Codex inspected all accepted title/artist pairs and found no obvious unrelated song or main artist; independent human precision auditing and audio verification remain pending. For example, a `12-inch Version` annotation was not normalized by the bounded matcher. Literal alternate titles and capped search pages also leave unresolved songs.

The [MVP results](reports/mvp_results.md) compare equal and current weights on identical frozen pools and hard policies. All three live lists were identical between methods. The hand-selected public example yields different lists; that demonstrates behavior rather than evidence of better preferences.

A listening panel contains eight distinct recordings from the union of both methods' top five songs in the first two predetermined runs. The listener reported **8/8 enjoyable, 8/8 familiar, and 0/8 previously unfamiliar**. These ratings were supplied as one bulk assessment; a separately blinded session was not verified. Save intention was not collected. Because the methods selected identical songs, the ratings cannot distinguish their weights. Absence from the submitted favorites does not establish that a song is unfamiliar or disliked.

A follow-up excluded those eight recording IDs and replayed the first saved pool with unchanged scores and constraints. It returned **4/5 requested songs across three groups**, using no new provider requests. The inputs and stopping rule were saved before selection. Follow-up ratings are pending; a different recording may still be familiar.

The follow-up exposed a further limitation: three songs repeat an artist from the earlier review, and the fourth shares a known composition with an earlier suggestion. Exact recording exclusions alone do not provide discovery across artists or compositions. Album overlap is unresolved because the saved snapshots lack release metadata.

## Optional fresh recommendations

Live runs use a local version-1 favorites JSON with `line_number`, `artist_text`, and `song_text`; album and duration are optional. Keep it and the MusicBrainz contact email/URL file under ignored `data/private/`.

```bash
python3 -B -m src.quick_recommend --input data/private/favorites.json --random-seed 3 --contact-file data/private/musicbrainz_contact.txt --output data/private/new_run
```

Defaults are eight sampled artist groups, up to 15 songs, 35 charged attempts, and a 55-second budget. Sampling weights are 1/2/3 for 1/2–10/>10 distinct liked songs, with one uniformly chosen song per group. These weights affect sampling only. Matching can spend at most 20 requests by default; unused capacity transfers to discovery. Discovery advances source groups in request rounds.

Each live run starts with fresh responses. Within-run requests are deduplicated; consecutive runs share a 1.1-second pacing gate. Attempts are charged before transport, automatic retries/redirects are disabled, backoff is honored, and a process supervisor ends stalled collection before scoring/export. Short or empty lists preserve completed evidence and an explicit reason. Live collection uses POSIX process/locking support; CI uses Linux.

The callable `src.quick_recommend.recommend_from_likes` retains its existing required arguments. Results include JSON, readable `SONG_REVIEW.md`, frozen snapshots, and charged request evidence. The source-group target stays visible when few seeds contribute; it is not silently lowered to claim success.

Apple checking is separate and preserves the original list and order:

```bash
python3 -B -m src.check_apple_music --recommendations data/private/new_run/recommendations.json --country DE --output data/private/new_run_apple
```

No availability claim is made by recommendation generation. No confident Apple match does not prove catalog absence.

## Reproduce measurements and listener review

Use new output directories. Each fresh recommendation run has its own limits.

```bash
python3 -B -m src.benchmark_matching --contact-file data/private/musicbrainz_contact.txt --output data/private/new_matching_audit --sample-size 100 --random-seed 42
python3 -B -m src.benchmark_recommendations --random-seeds 3 4 5 --seed-counts 8 --repeats 1 --contact-file data/private/musicbrainz_contact.txt --output data/private/new_benchmark
python3 -B -m src.compare_methods --runs data/private/new_benchmark/run_001 data/private/new_benchmark/run_002 data/private/new_benchmark/run_003 --output data/private/new_comparison
```

For a new review, open `LISTENING_REVIEW.md` and fill `ratings.csv` before viewing method membership or scores. Record familiarity and enjoyment; `would_save` is optional and may remain blank. The summary retains rated and pending denominators and treats missing save intention as uncollected.

```bash
python3 -B -m src.compare_methods --review data/private/new_comparison --ratings data/private/new_comparison/ratings.csv
```

A public frozen comparison also runs with `--runs data/demo`. Listener judgments come from the reviewer; the tool never invents them.

To prepare a follow-up, declare one saved pool and a completed previous review containing explicitly familiar songs. The tool preserves the original review, freezes exclusions and scoring settings before selection, and creates blank ratings in a new directory:

```bash
python3 -B -m src.compare_methods --runs data/private/new_benchmark/run_001 --known-review data/private/new_comparison --output data/private/new_followup
```

This panel uses only the current-weight top five. Exclusions use exact recording IDs and carry forward known IDs from previous follow-ups; alternate versions remain unresolved. This is an adaptive follow-up to listener feedback, and is reported separately from the original experiment.

## Engineering and next steps

The repository includes source-bound snapshot checksums, deterministic pure matching and scoring helpers, bounded collection, partial-result handling, controlled transport tests, and CI that runs the public demo and offline suite. Historical matching and selection retain their behavior unless new policies are enabled.

The [different-seed experiment](reports/different_seed_results.md) retained all three declared outcomes and missed the ten-track goal. Under the current two-per-source cap, ten requires at least five productive groups; these pools supplied only three, two, and three. Next, evaluate individual-song format eligibility and retrieval capacity as separate declared changes; current listener ratings remain pending. Independent inspection of the fixed ten-identity sample and nine unresolved cases remains pending. Keep the original eight-song result visible. A local MusicBrainz database may improve collection speed; it will not create missing credits or establish listener novelty. Import and paid hosting remain later decisions. The cancelled full-library API job is not resumed.

See [interview notes](reports/interview_notes.md), [decisions](DECISIONS.md), [the project plan](plan.md), and [historical workflows](reports/historical_workflows.md). The implementation was developed with Codex assistance; listener ratings are self-reported, and independent human identity auditing remains pending.
