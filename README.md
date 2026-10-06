# Music-credit recommendations

Can recording-credit relationships recover artists hidden from one person's
selected favorites? **Research result: pending.** Milestone 1 provides a small,
public, source-backed fixture to verify the graph and ranking arithmetic. It does
not measure recommendation quality. The approved study input is copied favorites
rather than the delayed Spotify export; see [DECISIONS.md](DECISIONS.md).

## Worked example

With The Beatles as the fixture seed, Nathan East receives **one two-hop point**:

1. The Beatles (primary recording artist) and Eric Clapton (guest electric guitar)
   are both credited on
   [While My Guitar Gently Weeps, original mono studio mix](https://musicbrainz.org/recording/863288d1-0fb0-410f-ac45-98e0bd62eac1).
2. Eric Clapton (primary artist, guitar, resonator guitar, vocals) and Nathan East
   (bass) are both credited on
   [Tears in Heaven](https://musicbrainz.org/recording/21ddde6c-90f4-469e-bdd0-1f438d011917).

That pair of recordings contributes +1. East shares no fixture recording directly
with The Beatles, so his direct score is 0 and total is 1. These co-credits do not
establish that The Beatles and East met or worked directly together.

## Data flow

The current demo starts at the frozen recording snapshots. Personal-text
conversion is available; matching, sampling, and evaluation are future milestones.

```mermaid
flowchart LR
    A[Private favorites text] --> B[Private JSON]
    B -. Future matching .-> C[Accepted recordings and primary artist seeds]
    F[Public frozen fixture] --> D[Recording-credit graph]
    C -. Future .-> D
    D --> E[Rankings and source-backed score contributions]
    E -. Future .-> G[Artist-holdout evaluation]
```

## What an edge means

Two distinct MusicBrainz artist entities have eligible credits on one recording.
The graph is undirected. Each edge retains its source recordings and each artist's
roles, attributes, and credit dates. Group entities remain separate from members;
a member needs their own eligible credit to appear on that recording.

Eligible roles are primary recording artists plus explicit recording-level
performer, instrument, vocal, producer, mixer, general engineer, audio engineer,
sound engineer, and recording engineer relationships. The ID allowlist is in
[config/graph_rules.yml](config/graph_rules.yml), using the
[MusicBrainz relationship definitions](https://musicbrainz.org/relationships/artist-recording).
The config uses the JSON subset of YAML 1.2, so the demo needs no YAML dependency.

Work-level writing, release-only credits, executive attributes, and relationships
outside the allowlist are excluded and audited. Multiple roles or credit dates
preserve evidence detail but do not create extra edge contributions for the same
pair and recording. Density is reported; no size cutoff is applied.

## Ranking methods

**Direct:** one point per distinct seed–candidate–recording combination.

**Two-hop:** direct score plus one point per seed–candidate–unordered pair of
different recordings connected through an intermediary. All three artists must
be distinct, and intermediaries cannot be seeds. Several intermediary paths or
both recording orientations still count as one recording-pair contribution; all
valid paths remain in the output. Separate seeds supply separate contributions.

For example, Billy Preston has 2 direct points plus 3 recording-pair points,
total **5**. Nathan East has 0 direct plus 1 recording-pair point, total **1**.
These are evidence counts, not probabilities or preference estimates.

Both methods use the same nonseed graph artists as candidates, including artists
with score zero in the direct baseline. Sort by descending score, case-insensitive
artist name, then MusicBrainz ID. All role weights are equal. A degree penalty is
a proposed later comparison and has not been implemented or tuned.

## Evaluation

No holdout evaluation has run. Future evaluation must hold out complete artists
and all their input tracks, use shared fixed splits for every method, and report
Recall@10/20 with overall and reachable counts. Final test splits must remain
untouched during rule selection. A small-data evaluation without independent
validation/test splits must be labeled exploratory.

The [milestone report](reports/results.md) contains fixture counts and the full
ranking; its table is an arithmetic verification, not an evaluation result.

## Failure analysis

- Eric Clapton has 17 fixture neighbors and connects The Beatles to ten artists
  on a single dense recording. Those suggestions are plausible graph paths,
  not evidence that this listener will like those artists.
- Tears in Heaven has 11 eligible artists and creates 55 edges. Capping repeated
  recording-pair evidence limits amplification but does not remove clique bias.
- Will Jennings is a work-level writer on Tears in Heaven and is excluded. This
  accurately follows the rule but leaves songwriting associations unrepresented.
- Missing recording credits cannot be repaired by promoting album credits or
  expanding a band's membership. This fixture cannot quantify that coverage loss.

## How to run it

From the repository root, with Python 3.12 or later, no installation or network is
needed:

```bash
python3 -m src.recommend --method direct
python3 -m src.recommend --method two-hop
python3 -m src.recommend --method two-hop --format json
python3 -m unittest discover -s tests -v
```

Text output shows every recommendation and its score contributions. JSON also
includes complete paths, roles, dates, source URLs, exclusions, recording density,
and artist degrees. Repeat `--seed MBID` to override the fixed fixture seed, or use
`--fixture DIRECTORY` for a directory with the same manifest/snapshot format.
An empty seed list in the Python API returns no recommendations; unknown IDs are
rejected.

### Private favorites conversion

```bash
python3 -m src.parse_library copied_favorite_songs.txt --output data/private/favorites.json
```

The converter accepts `Artist — Song` lines and the observed eight-column tabular
layout (title, unlabeled, duration, artist, album, genre, unlabeled, unlabeled).
It retains original lines and all tabular columns, preserves repeated songs,
and puts malformed or ambiguous rows in `needs_review`. It does not infer artist
identities, interpret unlabeled columns, or match recordings. It refuses to
overwrite an existing output; keep reviewed files and choose a new output path
when reconverting. Private text, JSON, exports, and caches are ignored by Git.

### Real-data process

The four public snapshots are frozen in [data/fixture](data/fixture), with source
queries, retrieval timestamps, hashes, and inspection notes. A broader API
sample, cache-aware retrieval, and personal recording matching remain unimplemented.
Do not start a full MusicBrainz dump or add other data sources for this milestone.

## Limitations and next steps

This hand-selected fixture validates code behavior only. MusicBrainz credits can
be incomplete and version-specific. The eventual favorites list is selected by
one listener; absent artists are not negative preference labels. No conclusions
generalize to other listeners. Continue with a bounded real-data sample and
conservative matching only in later milestones.

## Contribution and tools

The user selected the study input, verified-credit fixture, milestone boundary,
and recording-pair counting rule. Codex implemented the Python code, inspected
the source snapshots, checked the arithmetic, and documented the choices. An
independent human credit audit and the user's interpretation of real results
remain pending; neither is claimed as completed here.
