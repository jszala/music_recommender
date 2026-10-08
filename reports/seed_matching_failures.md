# Why six sampled favorites were skipped

Audit of the saved run at
`data/private/quick_final_verification_2026-10-08/run_001/`, collected on 2026-10-08.
This describes the original outcomes before the D-026 representative-version change.
It uses saved responses and makes no new matching or credit-completeness claims.

| Favorite | Original failure | What the response actually contained |
|---|---|---|
| Dean Blunt — 100 | Three plausible recordings; ambiguity caused rejection before detail lookup | All had the same artist/title. Two had duration 3:20 and appeared on Black Metal; the input duration was 3:21. The third lacked duration. |
| Kevin Morby — I Have Been to the Mountain | Two plausible recordings; ambiguity caused rejection before detail lookup | Durations were 3:14 and 3:14.440, against input 3:14. One appeared on Singing Saw, the input album; the other on a compilation. A separate live result was excluded by the version check. |
| The Style Council — It Didn't Matter | Two plausible recordings survived the literal-title and duration checks; ambiguity caused rejection | One survivor lacked duration, and another was 5:43.133 against input 5:44. Other returned versions included single edits and a 5:46 album recording titled It Didn’t Matter with a curly apostrophe, which failed literal title equality. |
| Talk Talk — Life's What You Make It (1997 - Remaster) | Zero search results | The one search used the entire title including `(1997 - Remaster)`. This run did not search the shorter base title. Zero results do not establish that the song is absent from MusicBrainz. |
| The Replacements — Swingin Party | Only the exact album check failed | Artist/title matched, duration differed by 0.427 seconds, and audio/version checks passed. Input album: Tim (Expanded Edition). The selected recording listed Essential New Wave. |
| Addison Rae & Arca — Aquamarine / Arcamarine | Only the exact album check failed | Artist/title and duration matched exactly. Input album: Aquamarine / Arcamarine - Single. Returned releases included Aquamarine / Arcamarine and Aquamarine. Recording and work contributor credits were present. |

## Was metadata entirely missing?

No returned candidate in these six cases was entirely without metadata. Every
returned candidate had a title and credited artist. Some search results lacked
duration, which the search-stage filter treated as uncertain rather than incorrect.
The Talk Talk search had no results, so no candidate metadata was available from
that particular query.

There is a separate example of sparse **contributor evidence**: the fetched
Swingin Party recording had `relations: []`. Its artist/title/duration/release
metadata were present, but no additional performer, producer, engineer, or work
relationships were observed. Primary artist credit was still present. An empty
relationship list does not establish that no other people contributed.

## User-directed version-selection change

D-026 replaces the quick prototype's automatic rejection of multiple plausible
recordings. It now chooses one representative recording, preferring exact album
context, then a known/closest duration, then a stable recording ID. It still uses
one search page and at most one detail lookup, preserving the candidate alternatives
and choice reason. Supplied recording IDs bypass searching as before.

This change does not remove the remaining exact title/album and version checks.
In particular, it does not normalize album edition suffixes, curly apostrophes, or
remaster labels, and it does not search a different title after an empty result.
Those issues must be distinguished from missing metadata and from multiple versions.
The original saved run and its evidence remain unchanged.
