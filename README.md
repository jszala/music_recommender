# Music-credit recommendations

An offline music recommender based on shared production, songwriting, performance,
and engineering credits. Work in progress.

## Recommendation example

All 11 recordings from three saved runs, in their original run order. The method
returned 4/10, 3/10, and 4/10; the first run includes a livestream and a continuous
mix. Track titles link to MusicBrainz. Apple links are searches, not verified matches.

<!-- recommendations:start -->

### Run 1 · 4/10 recordings

1. [Birthday Boy](https://musicbrainz.org/recording/e9af0d52-e19a-427b-b53a-7007bb5ad781) — Young Thug feat. Mariah the Scientist · [Apple search](https://music.apple.com/de/search?term=Young+Thug+feat.+Mariah+the+Scientist+Birthday+Boy)<br>
   Mariah the Scientist: musician on [Is It a Crime](https://musicbrainz.org/recording/d9661ab5-af54-438d-92fe-bb0fa7b9e7db) → musician here.

2. [Happy Friday! Playing 80's Music !sl for requests New Ham Merch in the !shop](https://musicbrainz.org/recording/31eaf598-a413-4757-8f48-55082acda828) — Nalani Proctor · [Apple search](https://music.apple.com/de/search?term=Nalani+Proctor+Happy+Friday%21+Playing+80%27s+Music+%21sl+for+requests+New+Ham+Merch+in+the+%21shop)<br>
   Tim Friese‐Greene: producer/songwriter on [Inheritance](https://musicbrainz.org/recording/1fd93309-5bcc-4732-9d0a-cf1ce484989c) → songwriter here.

3. [2017-09-09: BBC Radio 1 Essential Mix](https://musicbrainz.org/recording/8aa783a8-0931-47b8-a143-3e6f63ea0faf) — Fatima Yamaha · [Apple search](https://music.apple.com/de/search?term=Fatima+Yamaha+2017-09-09%3A+BBC+Radio+1+Essential+Mix)<br>
   Fatima Yamaha: songwriter on [What's A Girl To Do](https://musicbrainz.org/recording/2aa6d715-53ad-42dc-994b-825638d1b3b6) → musician here.

4. [\[untitled\]](https://musicbrainz.org/recording/4197143f-fb93-4181-8da9-c9db202fdc9d) — Tim Friese-Greene · [Apple search](https://music.apple.com/de/search?term=Tim+Friese-Greene+%5Buntitled%5D)<br>
   Tim Friese‐Greene: producer/songwriter on [Inheritance](https://musicbrainz.org/recording/1fd93309-5bcc-4732-9d0a-cf1ce484989c) → musician here.

### Run 2 · 3/10 recordings

1. [Temperature Check](https://musicbrainz.org/recording/6f59ac75-dce7-4172-8198-928630e47f0e) — Big Hit, Hit‐Boy &amp; The Alchemist · [Apple search](https://music.apple.com/de/search?term=Big+Hit%2C+Hit%E2%80%90Boy+%26+The+Alchemist+Temperature+Check)<br>
   The Alchemist: musician/producer on [Mac Deuce](https://musicbrainz.org/recording/82d91ef9-7eca-4bbc-a0e2-676b7931a8cf) → musician/producer/songwriter here.

2. [THUG IT OUT](https://musicbrainz.org/recording/042b44d5-b25e-407f-b4e0-eec83b1d9484) — NLE Choppa · [Apple search](https://music.apple.com/de/search?term=NLE+Choppa+THUG+IT+OUT)<br>
   Rachel Blum: engineering on [Seek &amp; Destroy](https://musicbrainz.org/recording/17894247-e585-4c97-83ea-de7047df7639) → engineering here.

3. [Tantor](https://musicbrainz.org/recording/00f49f38-1b90-477d-8369-a676c7f7a3db) — Danny Brown · [Apple search](https://music.apple.com/de/search?term=Danny+Brown+Tantor)<br>
   The Alchemist: musician/producer on [Mac Deuce](https://musicbrainz.org/recording/82d91ef9-7eca-4bbc-a0e2-676b7931a8cf) → producer/songwriter here.

### Run 3 · 4/10 recordings

1. [(I'm) The End of the Family Line](https://musicbrainz.org/recording/cf3292eb-b0d0-47c5-95b7-acad6f7b3f8c) — Morrissey · [Apple search](https://music.apple.com/de/search?term=Morrissey+%28I%27m%29+The+End+of+the+Family+Line)<br>
   Morrissey: musician/songwriter on [Nowhere Fast](https://musicbrainz.org/recording/70b5e517-72e2-400d-9e68-c7ac7139c66c) → musician/songwriter here.

2. [A carta](https://musicbrainz.org/recording/41a427df-2608-46a7-886f-55fb4244ab45) — Renato Russo &amp; Erasmo Carlos · [Apple search](https://music.apple.com/de/search?term=Renato+Russo+%26+Erasmo+Carlos+A+carta)<br>
   Erasmo Carlos: musician on [Sorriso dela](https://musicbrainz.org/recording/51acd96b-3b6e-48f3-a6db-1f857e708546) → musician here.

3. [Computer Power](https://musicbrainz.org/recording/22b0cc2d-2f57-4ef1-bd49-0f7b367bbf59) — Jamie Jupitor · [Apple search](https://music.apple.com/de/search?term=Jamie+Jupitor+Computer+Power)<br>
   The Egyptian Lover: musician on [I Cry (Night After Night)](https://musicbrainz.org/recording/68c4be84-238a-4864-b4c9-78bcc9615b2c) → songwriter here.

4. [Eu sou terrível](https://musicbrainz.org/recording/03d27835-ee02-40f9-8daa-aa732b03dd81) — Wanderléa · [Apple search](https://music.apple.com/de/search?term=Wanderl%C3%A9a+Eu+sou+terr%C3%ADvel)<br>
   Erasmo Carlos: musician on [Sorriso dela](https://musicbrainz.org/recording/51acd96b-3b6e-48f3-a6db-1f857e708546) → songwriter here.

<!-- recommendations:end -->

Primary artist credits are treated as performance proxies. Full paths, durations,
versions, and scores are in [the recording evidence](docs/recommendations.md).

## Method and results

The method scores shared credits, then selects a list with source and performer
constraints. Weights are provisional. A listening-behavior baseline is future work.

[Method](docs/method.md) · [Results](docs/results.md) · [Roadmap](ROADMAP.md)

## Reproduce

Python 3.12 or later; no installation, account, credentials, or network required.

```bash
python3 -B -m src.readme_demo
python3 -B -m unittest discover -s tests -v
```

The README shows frozen outputs. The [constructed fixture](data/demo/README.md)
separately runs scoring and selection offline. [Live collection](docs/research_tools.md)
is optional research tooling.

MusicBrainz metadata: CC0. [Sources and license status](DATA_LICENSE.md).
Developed with Codex assistance.
