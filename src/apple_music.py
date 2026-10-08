"""Free, conservative Apple song matching; reported streamability is not playback proof."""

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from .build_graph import ROOT
from .fetch_musicbrainz import FetchError, Limits, MusicBrainzClient, digest, json_bytes, save_json
from .match_recordings import VERSION_WORDS, artist_names, normalize


@dataclass(frozen=True)
class AppleRules:
    search_limit: int = 50
    max_queries_per_candidate: int = 2
    duration_tolerance_ms: int = 2000
    max_requests: int = 60
    min_interval_seconds: float = 3.1
    timeout_seconds: float = 20
    max_response_bytes: int = 16 * 1024 * 1024
    retries: int = 1

    def __post_init__(self):
        if type(self.search_limit) is not int or not 1 <= self.search_limit <= 200:
            raise ValueError("Apple search limit must be between 1 and 200")
        if type(self.max_queries_per_candidate) is not int or not 1 <= self.max_queries_per_candidate <= 2:
            raise ValueError("Allow at most two Apple queries per candidate")
        if type(self.duration_tolerance_ms) is not int or self.duration_tolerance_ms < 0:
            raise ValueError("Invalid Apple duration tolerance")
        self.client_limits()
        if self.min_interval_seconds < 3.1:
            raise ValueError("Apple lookups require at least 3.1 seconds between requests")

    def client_limits(self) -> Limits:
        return Limits(max_requests=self.max_requests, min_interval_seconds=self.min_interval_seconds,
                      timeout_seconds=self.timeout_seconds, max_response_bytes=self.max_response_bytes,
                      retries=self.retries)


def load_apple_rules(path: Path = ROOT / "config/apple_lookup_rules.json") -> AppleRules:
    raw = json.loads(path.read_bytes())
    if raw.pop("format_version", None) != 1:
        raise ValueError("Unsupported Apple lookup rules")
    return AppleRules(**raw)


def country_code(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2}", value):
        raise ValueError("Apple country must be a two-letter country code")
    return value.upper()


class AppleClient(MusicBrainzClient):
    api = "https://itunes.apple.com/"
    query_defaults = {}
    requires_contact = False

    def __init__(self, cache_dir: Path, rules: AppleRules, **kwargs):
        super().__init__(cache_dir, rules.client_limits(), **kwargs)

    def search(self, term: str, country: str, rules: AppleRules) -> dict:
        response = self.get("search", term=term, country=country_code(country), media="music",
                            entity="song", explicit="Yes", limit=rules.search_limit)
        if (not isinstance(response.get("results"), list) or type(response.get("resultCount")) is not int
                or response["resultCount"] != len(response["results"])):
            raise FetchError("Malformed Apple search response")
        return response


def dataset_fingerprint(records: list[dict]) -> str:
    by_id = {}
    for record in records:
        if record["id"] in by_id and record != by_id[record["id"]]:
            raise ValueError("Conflicting duplicate recording snapshots")
        by_id[record["id"]] = record
    return digest(json_bytes([by_id[rid] for rid in sorted(by_id)]))


# Strip decorated suffixes, never the word 'remaster' from the middle of a song title.
REMASTER_SUFFIX = re.compile(
    r"\s*(?:[\(\[]\s*(?:\d{4}\s+)?remaster(?:ed)?(?:\s+(?:in\s+)?\d{4})?\s*[\)\]]|"
    r"\s+[-–—]\s*(?:\d{4}\s+)?remaster(?:ed)?(?:\s+(?:in\s+)?\d{4})?)\s*$", re.I)
NON_REMASTER_VERSIONS = (VERSION_WORDS - {"remaster", "remastered"}) | {"cover", "rerecorded"}


def title_identity(title: str) -> tuple[str, bool]:
    stripped = REMASTER_SUFFIX.sub("", title)
    return normalize(stripped), stripped != title


def version_markers(text: str) -> list[str]:
    return sorted(set(re.findall(r"\w+", normalize(text))) & NON_REMASTER_VERSIONS)


def search_terms(record: dict, rules: AppleRules) -> list[str]:
    credits = record.get("artist-credit", [])
    joined = "".join(c.get("name", c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
                     if isinstance(c, dict) else c for c in credits)
    first = next((c.get("name", c.get("artist", {}).get("name", ""))
                  for c in credits if isinstance(c, dict)), "")
    title, _ = title_identity(record["title"])
    return list(dict.fromkeys(" ".join((artist + " " + title).split())
                             for artist in (joined, first) if artist))[:rules.max_queries_per_candidate]


def match_checks(record: dict, track: dict, rules: AppleRules) -> dict:
    title, remaster = title_identity(track.get("trackName", ""))
    wanted_title, source_remaster = title_identity(record["title"])
    length, duration = record.get("length"), track.get("trackTimeMillis")
    difference = (duration - length if type(duration) is int and duration > 0
                  and type(length) is int and length > 0 else None)
    wanted_versions = version_markers(record["title"] + " " + record.get("disambiguation", ""))
    found_versions = version_markers(track.get("trackName", "") + " " + track.get("collectionName", ""))
    remaster = remaster or bool(re.search(r"\bremaster(?:ed)?\b", track.get("collectionName", ""), re.I))
    source_remaster = source_remaster or bool(re.search(r"\bremaster(?:ed)?\b", record.get("disambiguation", ""), re.I))
    nonstudio = bool({"live", "remix", "demo", "cover", "karaoke", "rerecorded"}
                     & set(wanted_versions + found_versions))
    album_names = {normalize(r.get("title", "")) for r in record.get("releases", [])}
    valid_id = type(track.get("trackId")) is int and track["trackId"] > 0
    return {"song_resource": track.get("wrapperType") == "track" and track.get("kind") == "song" and valid_id,
            "artist_exact": normalize(track.get("artistName", "")) in artist_names(record),
            "title_exact": title == wanted_title,
            "source_versions": wanted_versions, "matched_versions": found_versions,
            "version_compatible": wanted_versions == found_versions and not ((remaster or source_remaster) and nonstudio),
            "duration_difference_ms": difference,
            "duration_within_tolerance": difference is not None and abs(difference) <= rules.duration_tolerance_ms,
            "studio_remaster": remaster and not nonstudio,
            "album_context_match": normalize(track.get("collectionName", "")) in album_names}


def qualifies(checks: dict) -> bool:
    return all(checks[k] for k in ("song_resource", "artist_exact", "title_exact",
                                  "version_compatible", "duration_within_tolerance"))


TRACK_FIELDS = ("wrapperType", "kind", "trackId", "collectionId", "artistName", "trackName",
                "collectionName", "trackTimeMillis", "trackExplicitness", "isStreamable", "trackViewUrl")


def match_recording(record: dict, tracks: list[dict], rules: AppleRules) -> dict:
    inspected = []
    for track in tracks:
        if not isinstance(track, dict):
            continue
        if any(not isinstance(track.get(key, ""), str) for key in
               ("trackName", "artistName", "collectionName", "trackViewUrl", "trackExplicitness")):
            continue
        # Preserve enough exact response metadata to recheck the selected match later.
        track = {key: track[key] for key in TRACK_FIELDS if key in track}
        checks = match_checks(record, track, rules)
        inspected.append({"track": track, "checks": checks})
    matching = [item for item in inspected if qualifies(item["checks"])]
    if not matching:
        return {"reason": "no_confident_match", "match": None, "inspected_tracks": inspected}
    # Different clean/explicit renditions with the same title are unresolved identities.
    ratings = {item["track"].get("trackExplicitness") for item in matching} - {None, "notExplicit"}
    if {"explicit", "cleaned"} <= ratings:
        return {"reason": "ambiguous_match", "match": None, "inspected_tracks": inspected}
    streamable = [item for item in matching if item["track"].get("isStreamable") is True]
    if not streamable:
        reason = "not_streamable" if all(item["track"].get("isStreamable") is False for item in matching) else "missing_streaming_flag"
        return {"reason": reason, "match": None, "inspected_tracks": inspected}
    streamable.sort(key=lambda item: (item["checks"]["studio_remaster"],
                                     not item["checks"]["album_context_match"],
                                     abs(item["checks"]["duration_difference_ms"]), item["track"]["trackId"]))
    chosen = streamable[0]
    return {"reason": "available", "match": chosen["track"], "checks": chosen["checks"],
            "inspected_tracks": inspected}


def validate_availability(data: dict, records: list[dict], *, country: str = "DE") -> dict[str, dict]:
    if data.get("format_version") != 1 or data.get("provider") != "apple_itunes_search":
        raise ValueError("Unsupported Apple availability report")
    if data.get("country") != country_code(country):
        raise ValueError("Apple availability report belongs to a different country")
    if data.get("dataset_sha256") != dataset_fingerprint(records):
        raise ValueError("Apple availability report does not match recording snapshots")
    rules = AppleRules(**data["rules"])
    if data.get("rules_sha256") != digest(json_bytes(asdict(rules))):
        raise ValueError("Apple availability rules fingerprint mismatch")
    by_id = {record["id"]: record for record in records}
    index = {}
    for item in data["recordings"]:
        rid = item["recording_id"]
        if rid not in by_id or rid in index:
            raise ValueError("Unknown or duplicate Apple availability recording")
        if item["reason"] == "available":
            if not isinstance(item.get("match"), dict):
                raise ValueError("Apple availability lacks a qualifying streamable match")
            rechecked = match_recording(by_id[rid], [item["match"]], rules)
            if rechecked["reason"] != "available":
                raise ValueError("Apple availability lacks a qualifying streamable match")
            url = item["match"].get("trackViewUrl", "")
            if not re.match(r"https://music\.apple\.com/" + country.lower() + r"/", url):
                raise ValueError("Apple song link does not match the report country")
            item = item | {"checks": rechecked["checks"]}
        index[rid] = item
    return index


def collect_availability(client: AppleClient, records: list[dict], candidate_ids: list[str], *,
                         rules: AppleRules, output: Path, country: str = "DE",
                         favorite_ids: list[str] | None = None) -> dict:
    country = country_code(country)
    if client.limits != rules.client_limits():
        raise ValueError("Apple client limits do not match lookup rules")
    fingerprint = dataset_fingerprint(records)
    by_id = {record["id"]: record for record in records}
    if len(candidate_ids) != len(set(candidate_ids)) or set(candidate_ids) - by_id.keys():
        raise ValueError("Apple candidates must be known distinct recording IDs")
    output.mkdir(parents=True, exist_ok=False)
    responses = output / "responses"
    responses.mkdir()
    rows = []
    for rid in candidate_ids:
        record = by_id[rid]
        tracks, queries, errors = {}, [], []
        truncated = False
        terms = search_terms(record, rules)
        for term in terms:
            start = len(client.events)
            try:
                body = client.search(term, country, rules)
                truncated |= len(body["results"]) >= rules.search_limit
                for track in body["results"]:
                    if isinstance(track, dict):
                        tracks[digest(json_bytes(track))] = track
            except FetchError as error:
                errors.append("budget_exhausted" if "budget exhausted" in str(error).lower() else "request_failure")
            events = client.events[start:]
            for event in events:
                if event.get("cache_file"):
                    cache_path = client.cache_dir / event["cache_file"]
                    (responses / cache_path.name).write_bytes(cache_path.read_bytes())
                queries.append(event)
            match = match_recording(record, list(tracks.values()), rules)
            if match["reason"] == "available" and not truncated and not errors:
                break
        match = match_recording(record, list(tracks.values()), rules)
        if errors or truncated:
            match = match | {"reason": errors[0] if errors else "search_limit_reached", "match": None}
        if not terms:
            match = match | {"reason": "no_artist_context", "match": None}
        if match["reason"] == "available" and not re.match(
                r"https://music\.apple\.com/" + country.lower() + r"/", match["match"].get("trackViewUrl", "")):
            match = match | {"reason": "invalid_country_link", "match": None}
        rows.append({"recording_id": rid, "title": record["title"], **match, "queries": queries,
                     "checked_at": max((q["retrieved_at"] for q in queries if q.get("retrieved_at")), default=None),
                     "errors": errors, "search_truncated": truncated})
    report = {"format_version": 1, "provider": "apple_itunes_search", "country": country,
              "dataset_sha256": fingerprint, "favorite_recording_ids": sorted(set(favorite_ids or [])),
              "rules": asdict(rules), "rules_sha256": digest(json_bytes(asdict(rules))),
              "recordings": rows, "summary": {"candidates": len(rows), "network_attempts": client.network_attempts,
              "reason_counts": dict(sorted(Counter(row["reason"] for row in rows).items()))},
              "limitations": ["API-indicated streamability does not guarantee account-specific playback.",
                               "Conservative metadata matches are not audio-identity proofs.",
                               "No search result does not establish catalog absence; the public streaming flag can change."]}
    validate_availability(report, records, country=country)
    save_json(output / "availability.json", report)
    return report
