"""Conservatively match private favorites to cached MusicBrainz recording evidence."""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import unicodedata

from .build_graph import ROOT
from .credits import credit_coverage, extract_credits
from .fetch_musicbrainz import (
    CACHE_VERSION, RECORDING_INCLUDES, FetchError, Limits, MusicBrainzClient,
    digest, json_bytes, mbid, save_json, utc_now,
)


MATCH_INCLUDES = RECORDING_INCLUDES + "+releases+isrcs"
VERSION_WORDS = {"live", "remix", "mono", "stereo", "clean", "explicit", "edit",
                 "mix", "atmos", "surround", "quadraphonic", "acoustic", "instrumental",
                 "demo", "karaoke", "remastered", "remaster"}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def quoted(text: str) -> str:
    # Quote a literal Lucene phrase; URL encoding is handled separately by the client.
    return '"' + re.sub(r'([+\-!(){}\[\]^"~*?:\\/|&])', r'\\\1', text) + '"'


def search_query(track: dict) -> str:
    return f"recording:{quoted(track['song_text'])} AND artist:{quoted(track['artist_text'])}"


def artist_names(recording: dict) -> set[str]:
    credits = recording.get("artist-credit", [])
    if not credits:
        return set()
    names = {normalize("".join(
        c.get("name", c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
        if isinstance(c, dict) else c for c in credits))}
    named = [c for c in credits if isinstance(c, dict)]
    if len(named) == 1:
        names.add(normalize(named[0]["artist"]["name"]))
    return names


def duration_ms(track: dict) -> int | None:
    value = track.get("duration_text", "")
    if not value:
        return None
    if not re.fullmatch(r"\d+:[0-5]\d", value):
        raise ValueError("Invalid favorite duration")
    minutes, seconds = map(int, value.split(":"))
    return (minutes * 60 + seconds) * 1000


@dataclass(frozen=True)
class MatchRules:
    search_page_size: int = 25
    max_search_pages: int = 2
    max_recordings_per_song: int = 4
    duration_tolerance_ms: int = 2000

    def __post_init__(self):
        for name in ("search_page_size", "max_search_pages", "max_recordings_per_song"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.search_page_size > 100:
            raise ValueError("Search pages cannot exceed 100 results")
        if type(self.duration_tolerance_ms) is not int or self.duration_tolerance_ms < 0:
            raise ValueError("Invalid duration tolerance")


def candidate_checks(track: dict, recording: dict, rules: MatchRules) -> dict:
    wanted_duration = duration_ms(track)
    length = recording.get("length")
    if length is not None and (type(length) is not int or length < 0):
        raise ValueError("Invalid recording duration")
    difference = length - wanted_duration if length is not None and wanted_duration is not None else None
    album = normalize(track.get("album_text", ""))
    album_releases = sorted({r["id"] for r in recording.get("releases", [])
                             if album and normalize(r.get("title", "")) == album})
    input_words = set(re.findall(r"\w+", normalize(track["song_text"] + " " + track.get("album_text", ""))))
    candidate_words = set(re.findall(r"\w+", normalize(recording["title"] + " " + recording.get("disambiguation", ""))))
    unresolved_versions = sorted((candidate_words & VERSION_WORDS) - input_words)
    missing_input_versions = sorted((set(re.findall(r"\w+", normalize(track["song_text"]))) & VERSION_WORDS) - candidate_words)
    return {"title_exact": normalize(track["song_text"]) == normalize(recording["title"]),
            "combined_artist_exact": normalize(track["artist_text"]) in artist_names(recording),
            "album_release_ids": album_releases, "album_observed": bool(album_releases),
            "album_absence_is_conclusive": False,
            "duration_difference_ms": difference,
            "duration_within_tolerance": difference is not None and abs(difference) <= rules.duration_tolerance_ms,
            "unresolved_version_markers": unresolved_versions + missing_input_versions,
            "audio_only": recording.get("video") is not True}


def qualifies(checks: dict) -> bool:
    return (checks["title_exact"] and checks["combined_artist_exact"]
            and checks["album_observed"] and checks["duration_within_tolerance"]
            and checks["audio_only"] and not checks["unresolved_version_markers"])


def load_input(path: Path, selection: Path | None = None, *, start: int = 0,
               count: int | None = None) -> tuple[list[dict], dict]:
    raw = path.read_bytes()
    data = json.loads(raw)
    if data.get("format_version") != 1 or not isinstance(data.get("tracks"), list):
        raise ValueError("Expected version-1 favorites JSON")
    tracks = data["tracks"]
    for track in tracks:
        if (type(track.get("line_number")) is not int or not track.get("artist_text")
                or not track.get("song_text")):
            raise ValueError("Favorite row lacks source line, artist, or title")
        duration_ms(track)
    if len({t["line_number"] for t in tracks}) != len(tracks):
        raise ValueError("Duplicate source line numbers")
    metadata = {"input_sha256": digest(raw), "input_rows": len(tracks),
                "format_review_rows": len(data.get("needs_review", []))}
    from .song_policy import submitted_artists
    metadata["submitted_artists"] = submitted_artists(tracks + data.get("needs_review", []))
    if selection:
        chosen = json.loads(selection.read_bytes())
        if chosen.get("favorite_source_sha256") != metadata["input_sha256"]:
            raise ValueError("Selection belongs to a different favorites input")
        numbers = chosen["selected_source_line_numbers"]
        by_line = {t["line_number"]: t for t in tracks}
        if (not numbers or len(set(numbers)) != len(numbers)
                or any(n not in by_line for n in numbers)):
            raise ValueError("Invalid selection line numbers")
        tracks = [by_line[n] for n in numbers]
        metadata["selection_sha256"] = digest(selection.read_bytes())
    elif start < 0 or (count is not None and count < 1):
        raise ValueError("Invalid row selection")
    else:
        tracks = tracks[start:] if count is None else tracks[start:start + count]
    if not tracks:
        raise ValueError("No favorite rows selected")
    return tracks, metadata


def load_reviews(path: Path | None, metadata: dict, tracks: list[dict]) -> dict:
    if path is None:
        return {}
    raw = path.read_bytes()
    data = json.loads(raw)
    if data.get("format_version") != 1 or data.get("input_sha256") != metadata["input_sha256"]:
        raise ValueError("Reviews belong to a different input or format")
    metadata["reviews_sha256"] = digest(raw)
    known_lines = {t["line_number"] for t in tracks}
    reviews = {}
    for decision in data["decisions"]:
        line = decision["line_number"]
        if line in reviews or line not in known_lines:
            raise ValueError("Review has duplicate or unselected source line")
        if decision["status"] not in {"pending", "accepted", "unresolved"}:
            raise ValueError("Unknown review status")
        if decision["status"] != "pending" and (not decision.get("reviewer", "").strip()
                                                 or not decision.get("evidence", "").strip()):
            raise ValueError("Reviewed decisions need reviewer and evidence")
        if decision["status"] == "accepted":
            mbid(decision["recording_id"])
        reviews[line] = decision
    return reviews


def match_batch(client: MusicBrainzClient, tracks: list[dict], metadata: dict,
                output: Path, rules: MatchRules, reviews: dict | None = None,
                progress=None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    (output / "recordings").mkdir()
    failures, rows, records, sources = [], [], {}, {}
    reviews = {} if reviews is None else reviews

    def fetch(endpoint, context, **params):
        try:
            return client.get(endpoint, **params)
        except FetchError as error:
            failures.append({"context": context, "endpoint": endpoint,
                             "params": params, "error": str(error)})
            return None

    def lookup(rid, line):
        if rid in records:
            return records[rid]
        recording = fetch(f"recording/{rid}", {"line_number": line, "stage": "lookup"}, inc=MATCH_INCLUDES)
        if recording is None:
            return None
        try:
            if (recording.get("id") != rid or not recording.get("title")
                    or not isinstance(recording.get("artist-credit"), list)
                    or not isinstance(recording.get("relations"), list)
                    or not isinstance(recording.get("releases"), list)):
                raise ValueError("Malformed recording lookup or missing requested fields")
            extract_credits(recording)
            candidate_checks(next(t for t in tracks if t["line_number"] == line), recording, rules)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"context": {"line_number": line, "recording_id": rid}, "error": str(error)})
            return None
        data = json_bytes(recording)
        relative = f"recordings/{rid}.json"
        (output / relative).write_bytes(data)
        event = client.events[-1]
        sources[rid] = {"recording_id": rid, "snapshot_file": relative, "sha256": digest(data),
                        "source_url": f"https://musicbrainz.org/recording/{rid}",
                        **{k: event[k] for k in ("query", "retrieved_at", "response_sha256", "cache_file")}}
        records[rid] = recording
        return recording

    for track_number, track in enumerate(tracks, 1):
        line = track["line_number"]
        query, search_rows, pages, complete = search_query(track), {}, [], False
        total, offset = None, 0
        for _ in range(rules.max_search_pages):
            result = fetch("recording", {"line_number": line, "stage": "search"},
                           query=query, limit=rules.search_page_size, offset=offset)
            if result is None:
                break
            try:
                returned = result["recordings"]
                total = result["count"]
                if (not isinstance(returned, list) or len(returned) > rules.search_page_size
                        or type(total) is not int or total < 0
                        or result.get("offset", offset) != offset
                        or total < offset + len(returned)):
                    raise ValueError("Malformed search page")
                for candidate in returned:
                    rid = mbid(candidate["id"])
                    if not candidate.get("title") or not isinstance(candidate.get("artist-credit"), list):
                        raise ValueError("Search candidate lacks title/artist credits")
                    artist_names(candidate)
                    if candidate.get("length") is not None and (type(candidate["length"]) is not int or candidate["length"] < 0):
                        raise ValueError("Invalid search candidate duration")
                    search_rows.setdefault(rid, candidate)
            except (KeyError, ValueError, TypeError) as error:
                failures.append({"context": {"line_number": line, "stage": "search"}, "error": str(error)})
                break
            pages.append({"offset": offset, "returned": len(returned), "reported_total": total,
                          "query": client.events[-1]["query"],
                          "response_sha256": client.events[-1]["response_sha256"]})
            offset += len(returned)
            if offset >= total:
                complete = True
                break
            if not returned:
                break
        wanted_duration = duration_ms(track)

        def priority(candidate):
            artist_exact = normalize(track["artist_text"]) in artist_names(candidate)
            title_exact = normalize(track["song_text"]) == normalize(candidate["title"])
            album_exact = any(normalize(r.get("title", "")) == normalize(track.get("album_text", ""))
                              for r in candidate.get("releases", []) if track.get("album_text"))
            length = candidate.get("length")
            gap = abs(length - wanted_duration) if type(length) is int and wanted_duration is not None else float("inf")
            return (not (title_exact and artist_exact), not album_exact, gap, candidate["id"])

        ordered = sorted(search_rows.values(), key=priority)
        chosen = ordered[:rules.max_recordings_per_song]
        omitted = [r["id"] for r in ordered[rules.max_recordings_per_song:]]
        omitted_exact = [r["id"] for r in ordered[rules.max_recordings_per_song:]
                         if normalize(r["title"]) == normalize(track["song_text"])
                         and normalize(track["artist_text"]) in artist_names(r)]
        candidates, lookup_complete = [], True
        for search_record in chosen:
            recording = lookup(search_record["id"], line)
            if recording is None:
                lookup_complete = False
                candidates.append({"recording_id": search_record["id"], "search_result": search_record,
                                   "lookup_status": "failed", "qualifies": False})
                continue
            checks = candidate_checks(track, recording, rules)
            candidates.append({"recording_id": recording["id"], "title": recording["title"],
                               "artist_credit": recording["artist-credit"],
                               "disambiguation": recording.get("disambiguation", ""),
                               "length_ms": recording.get("length"),
                               "releases": recording["releases"], "isrcs": recording.get("isrcs", []),
                               "search_score": search_record.get("score"), "lookup_status": "complete",
                               "checks": checks, "qualifies": qualifies(checks),
                               "source": sources[recording["id"]],
                               "credits": extract_credits(recording)})
        qualifying = [c for c in candidates if c["qualifies"]]
        reasons, accepted, basis = [], None, None
        if not complete:
            reasons.append("search incomplete: failure or declared page limit")
        if omitted_exact:
            reasons.append("exact title/artist alternatives not inspected: lookup limit")
        if not lookup_complete:
            reasons.append("candidate lookup failed")
        if len(qualifying) > 1:
            reasons.append("multiple recordings satisfy acceptance evidence")
        if len(qualifying) == 1 and complete and not omitted_exact and lookup_complete:
            status, accepted, basis = "accepted", qualifying[0]["recording_id"], "rule_based"
            reasons.append("unique exact artist/title, album release, duration, and version evidence")
        elif complete and not search_rows:
            status = "no_result"
            reasons.append("literal artist/title search returned no recordings")
        elif not search_rows and not pages:
            status = "not_searched"
        else:
            status = "needs_review"
            if not qualifying:
                reasons.append("no candidate has all required acceptance evidence")
        review = reviews.get(line)
        if review and review["status"] == "accepted":
            known = {c["recording_id"] for c in candidates if c["lookup_status"] == "complete"}
            if review["recording_id"] not in known:
                raise ValueError("Manual acceptance must identify a fetched candidate in this row")
            status, accepted, basis = "accepted", review["recording_id"], "human_review"
            reasons.append("explicit human identity decision with recorded evidence")
        elif review and review["status"] == "unresolved":
            status, accepted, basis = "needs_review", None, None
            reasons.append("human review left identity unresolved")
        rows.append({"source_row": track, "status": status, "accepted_recording_id": accepted,
                     "acceptance_basis": basis, "reasons": reasons, "human_review": review or {"status": "pending"},
                     "search": {"literal_query": query, "pages": pages, "complete": complete,
                                "reported_total": total, "returned_unique_ids": sorted(search_rows),
                                "omitted_lookup_ids": omitted, "omitted_exact_ids": omitted_exact},
                     "candidates": candidates})
        if progress:
            progress(track_number, len(tracks), status)

    favorite_rows = {}
    for row in rows:
        if row["accepted_recording_id"]:
            favorite_rows.setdefault(row["accepted_recording_id"], []).append(row["source_row"]["line_number"])
    profile = {"format_version": 1, "input_sha256": metadata["input_sha256"],
               "favorites": [{"recording_id": rid, "source_lines": sorted(lines),
                              "primary_artist_ids": sorted({c["artist"]["id"] for c in records[rid]["artist-credit"] if isinstance(c, dict)}),
                              "source_sha256": sources[rid]["sha256"]}
                             for rid, lines in sorted(favorite_rows.items())],
               "independent_human_audit": "pending", "unknown_cross_id_equivalence": True}
    accepted_records = [records[rid] for rid in favorite_rows]
    from .song_policy import build_registry, registry_digest
    profile["artist_registry"] = build_registry(accepted_records, list(favorite_rows),
                                               names=metadata.get("submitted_artists"),
                                               input_sha256=metadata["input_sha256"])
    stats = {"selected_rows": len(rows), "statuses": dict(Counter(r["status"] for r in rows)),
             "accepted_distinct_recordings": len(favorite_rows), "candidate_recordings_fetched": len(records),
             "human_reviewed_rows": sum(r["human_review"]["status"] != "pending" for r in rows)}
    fingerprint = digest(json_bytes({"metadata": metadata, "rules": asdict(rules), "matches": rows}))
    manifest = {"format_version": 1, "kind": "recording matching", "sample_id": fingerprint,
                "artist_registry_sha256": registry_digest(profile["artist_registry"]),
                "completed_at": utc_now(), **metadata, "rules": asdict(rules), "limits": asdict(client.limits),
                "cache_format_version": CACHE_VERSION, "sources": [sources[r] for r in sorted(sources)],
                "requests": client.events, "network_attempts": client.network_attempts,
                "offline": client.offline, "failures": failures,
                "collection_status": "partial" if failures else "complete_with_declared_limits",
                "stats": stats, "independent_human_audit": "pending",
                "limitations": ["Rule-based acceptance is not independently audited precision.",
                                "Limited search and linked releases do not certify database completeness.",
                                "No release-level credits, inferred band members, or cross-ID audio deduplication.",
                                "Unlisted favorites and credits are not negative preference labels."]}
    save_json(output / "manifest.json", manifest)
    save_json(output / "matches.json", rows)
    save_json(output / "profile.json", profile)
    save_json(output / "credit_audit.json", {"all_candidates": credit_coverage(list(records.values())),
                                             "accepted_recordings": credit_coverage(accepted_records)})
    save_json(output / "reviews_template.json", {"format_version": 1, "input_sha256": metadata["input_sha256"],
                                               "decisions": [{"line_number": r["source_row"]["line_number"],
                                                              "status": "pending", "recording_id": None,
                                                              "reviewer": "", "evidence": ""} for r in rows]})
    write_review(output, rows, stats)
    return manifest


def write_review(output: Path, rows: list[dict], stats: dict) -> None:
    lines = ["# Recording identity and credit review", "",
             "Automatic decisions use fixed evidence rules. Independent human audit is pending.",
             "Edit a copy of reviews_template.json with reviewer and evidence, then rerun with --reviews into a new directory.",
             "A limited-release list can establish album presence; album absence remains unknown.", "",
             f"Selected rows: {stats['selected_rows']}; distinct accepted recordings: {stats['accepted_distinct_recordings']}.", ""]
    for number, row in enumerate(rows, 1):
        source = row["source_row"]
        lines += [f"## {number}. {source['artist_text']} — {source['song_text']}", "",
                  f"Source line {source['line_number']}; album: {source.get('album_text', 'unknown')}; duration: {source.get('duration_text', 'unknown')}.",
                  f"Status: {row['status']}; accepted ID: {row['accepted_recording_id'] or 'none'}; basis: {row['acceptance_basis'] or 'none'}.",
                  "Reasons: " + "; ".join(row["reasons"]), ""]
        for candidate in row["candidates"]:
            rid = candidate["recording_id"]
            lines += [f"### Candidate [{rid}](https://musicbrainz.org/recording/{rid})", ""]
            if candidate["lookup_status"] != "complete":
                lines += ["Lookup failed; candidate cannot be accepted automatically.", ""]
                continue
            lines += [f"Version: {candidate['disambiguation'] or 'unspecified'}; duration: {candidate['length_ms']} ms.",
                      "Checks: " + json.dumps(candidate["checks"], ensure_ascii=False), ""]
            for credit in candidate["credits"]:
                work = f"; work {credit['work_id']}" if credit["work_id"] else ""
                attrs = "; attributes: " + ", ".join(credit["attributes"]) if credit["attributes"] else ""
                lines.append(f"- {credit['artist']['name']}: {credit['role']} ({credit['scope']}{work}); category: {credit['category'] or 'unmapped'}{attrs}")
            lines += [""]
        review = row["human_review"]
        if review["status"] == "pending":
            lines += ["Human identity/version evidence: pending."]
        else:
            lines += [f"Human review: {review['status']}; reviewer: {review['reviewer']}.",
                      f"Identity/version evidence: {review['evidence']}"]
        lines += ["Missing-credit / role-scope notes: pending.", ""]
    (output / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/private/favorites.json")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--selection", type=Path, help="Prepared audit manifest bound to this favorites file")
    selection.add_argument("--start-row", type=int, default=0, help="Zero-based start for a later matching batch")
    parser.add_argument("--row-limit", type=int)
    parser.add_argument("--rules", type=Path, default=ROOT / "config/matching_rules.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache/musicbrainz")
    parser.add_argument("--output", type=Path, required=True, help="New private output directory")
    parser.add_argument("--contact-file", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--reviews", type=Path)
    args = parser.parse_args()
    try:
        if args.selection and args.row_limit is not None:
            raise ValueError("Use a selection manifest or a row limit, not both")
        tracks, metadata = load_input(args.input, args.selection, start=args.start_row, count=args.row_limit)
        reviews = load_reviews(args.reviews, metadata, tracks)
        values = json.loads(args.rules.read_bytes())
        if values.pop("format_version") != 1:
            raise ValueError("Unsupported matching rules")
        rules = MatchRules(**{k: values[k] for k in MatchRules.__dataclass_fields__})
        limits = Limits(**{k: v for k, v in values.items() if k not in MatchRules.__dataclass_fields__})
        contact = args.contact_file.read_text().strip() if args.contact_file else None
        with MusicBrainzClient(args.cache, limits, contact=contact, offline=args.offline,
                              retry_failures=args.retry_failures) as client:
            manifest = match_batch(client, tracks, metadata, args.output, rules, reviews,
                                   progress=lambda i, n, status: print(f"Matched row {i}/{n}: {status}", flush=True))
    except (OSError, ValueError, TypeError, KeyError, FetchError) as error:
        parser.error(str(error))
    print(json.dumps({"output": str(args.output), "stats": manifest["stats"],
                      "http_attempts": manifest["network_attempts"], "collection_status": manifest["collection_status"]}, indent=2))
    if manifest["collection_status"] == "partial":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
