"""Representative song identity for the fast prototype; no fuzzy matching.

Release metadata ranks compatible recordings. It never establishes song identity.
Historical matching rules deliberately remain separate.
"""

import math
import re
import unicodedata

from .credits import extract_credits
from .fetch_musicbrainz import mbid
from .match_recordings import duration_ms, quoted


POLICY = "representative_song_v1"
_PUNCTUATION = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", "‐": "-", "‑": "-"})
_FEATURE = re.compile(r"\s*[\[(]?\b(?:feat\.?|ft\.?|featuring)\s+(.+?)[\])]?$", re.I)
_SUFFIX = re.compile(r"\s*(?:\(([^()]*)\)|\[([^\[\]]*)\]|\s-\s(.+))$")
_VERSION = re.compile(r"\b(?:live|remix|edit|mix|acoustic|instrumental|demo|mono|stereo|karaoke)\b")
_REMASTER = re.compile(r"\bremaster(?:ed)?\b")


def comparison_key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(_PUNCTUATION).casefold().split())


def title_keys(text: str) -> dict:
    full = comparison_key(text)
    base, annotations, versions, guests = full, [], [], []
    while True:
        feature = _FEATURE.search(base)
        if feature:
            guests.append(feature[1])
            annotations.append(feature[0].strip())
            base = base[:feature.start()].strip()
            continue
        suffix = _SUFFIX.search(base)
        if not suffix:
            break
        label = next(g for g in suffix.groups() if g is not None).strip()
        # Keep ordinary parenthetical titles (including words such as "live").
        is_version = bool(_VERSION.search(label) and (
            re.match(r"^(?:live|acoustic|instrumental|demo|mono|stereo|karaoke)\b", label)
            or re.search(r"\b(?:remix|edit|mix)$", label)))
        if not (_REMASTER.search(label) or re.fullmatch(r"(?:19|20)\d{2}", label) or is_version):
            break
        annotations.append(label)
        if is_version:
            versions.append(label)
        base = base[:suffix.start()].strip()
    return {"full": full, "base": base, "annotations": annotations,
            "versions": versions, "featured_artists": guests}


def main_artist_key(text: str) -> str:
    key = comparison_key(text)
    feature = _FEATURE.search(key)
    return key[:feature.start()].strip() if feature else key


def core_response_valid(record: dict) -> bool:
    """Accept missing optional evidence, but reject malformed supplied fields."""
    try:
        if not isinstance(record, dict) or not isinstance(record.get("title"), str) or not record["title"].strip():
            return False
        mbid(record["id"])
        credits = record.get("artist-credit")
        if not isinstance(credits, list) or not credits or not isinstance(credits[0], dict):
            return False
        for credit in credits:
            if isinstance(credit, str):
                continue
            if not isinstance(credit, dict):
                return False
            artist = credit["artist"]
            mbid(artist["id"])
            if not isinstance(artist.get("name"), str) or not artist["name"].strip():
                return False
            if any(k in credit and not isinstance(credit[k], str) for k in ("name", "joinphrase")):
                return False
        if "length" in record and record["length"] is not None and (type(record["length"]) is not int or record["length"] < 0):
            return False
        if "video" in record and record["video"] is not None and type(record["video"]) is not bool:
            return False
        if "disambiguation" in record and not isinstance(record["disambiguation"], str):
            return False
        for field in ("releases", "relations"):
            if field in record and not isinstance(record[field], list):
                return False
        for release in record.get("releases", []):
            if not isinstance(release, dict) or not isinstance(release.get("title", ""), str):
                return False
        for relation in record.get("relations", []):
            if not isinstance(relation, dict):
                return False
            attrs = relation.get("attributes", [])
            if not isinstance(attrs, list) or any(not isinstance(a, str) for a in attrs):
                return False
            if relation.get("target-type") == "work":
                work = relation["work"]
                mbid(work["id"])
                if "relations" in work and not isinstance(work["relations"], list):
                    return False
        for credit in extract_credits(record):
            mbid(credit["artist"]["id"])
            if not isinstance(credit["artist"]["name"], str) or not credit["artist"]["name"].strip():
                return False
            if not isinstance(credit["role"], str) or not isinstance(credit["scope"], str):
                return False
        return True
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _artist_checks(wanted: str, credits: list) -> tuple[bool, bool]:
    named = [c for c in credits if isinstance(c, dict)]
    display = "".join(c.get("name", c["artist"]["name"]) + c.get("joinphrase", "")
                      if isinstance(c, dict) else c for c in credits)
    exact = comparison_key(wanted) == comparison_key(display)
    first = named[0]
    first_names = {comparison_key(first.get("name", first["artist"]["name"])),
                   comparison_key(first["artist"]["name"])}
    main = main_artist_key(wanted)
    if exact or main in first_names:
        return True, exact
    # Interpret a collaboration only against returned individual credit structure.
    # This never splits a band's own name or accepts a match through a guest alone.
    for name in first_names:
        if main.startswith(name):
            rest = main[len(name):]
            for credit in named[1:]:
                separators = r"^\s*(?:&|and|with|feat\.?|ft\.?|featuring|,|/|x|×)\s*"
                rest = re.sub(separators, "", rest)
                names = sorted({comparison_key(credit.get("name", credit["artist"]["name"])),
                                comparison_key(credit["artist"]["name"])}, key=len, reverse=True)
                match = next((n for n in names if rest.startswith(n)), None)
                if match is None:
                    break
                rest = rest[len(match):]
            else:
                if not rest.strip():
                    return True, False
    return False, exact


def identity_checks(track: dict, record: dict) -> dict:
    wanted, actual = title_keys(track["song_text"]), title_keys(record["title"])
    artist_ok, artist_exact = _artist_checks(track["artist_text"], record["artist-credit"])
    return {"base_title_compatible": bool(wanted["base"] and wanted["base"] == actual["base"]),
            "main_artist_compatible": artist_ok, "title_exact": wanted["full"] == actual["full"],
            "combined_artist_exact": artist_exact, "audio_only": record.get("video") is not True,
            "input_title": wanted, "candidate_title": actual,
            "normalized_artist": main_artist_key(track["artist_text"])}


def compatible(track: dict, record: dict) -> bool:
    if not core_response_valid(record):
        return False
    checks = identity_checks(track, record)
    return all(checks[k] for k in ("base_title_compatible", "main_artist_compatible", "audio_only"))


def candidate_priority(track: dict, record: dict) -> tuple:
    checks = identity_checks(track, record)
    wanted = checks["input_title"]["versions"]
    actual = checks["candidate_title"]["versions"]
    description = comparison_key(record.get("disambiguation", ""))
    observed = actual or ([description] if _VERSION.search(description) else [])
    requested = (not observed if not wanted else any(v in " ".join(observed) for v in wanted))
    album = title_keys(track.get("album_text", ""))["base"]
    album_match = bool(album and any(title_keys(r.get("title", ""))["base"] == album
                                    for r in record.get("releases", [])))
    duration = duration_ms(track)
    gap = abs(record["length"] - duration) if record.get("length") is not None and duration is not None else math.inf
    return (not (checks["title_exact"] and checks["combined_artist_exact"] and requested),
            not requested, not album_match, gap, record["id"])


def choose_candidate(track: dict, candidates) -> dict:
    return min(candidates, key=lambda record: candidate_priority(track, record))


def version_notice(track: dict, record: dict) -> str | None:
    wanted = title_keys(track["song_text"])["versions"]
    actual = title_keys(record["title"])["versions"]
    description = comparison_key(record.get("disambiguation", ""))
    observed = actual or ([description] if _VERSION.search(description) else [])
    if (wanted and not any(v in " ".join(observed) for v in wanted)) or (observed and not wanted):
        return "Representative alternative version; exact originally liked audio identity is unverified."
    return None


def seed_query(track: dict, *, fallback: bool = False) -> str:
    title = title_keys(track["song_text"])["base"]
    query = f"recording:{quoted(title)}"
    return query if fallback else f"{query} AND artist:{quoted(main_artist_key(track['artist_text']))}"


def matching_allocation(max_requests: int) -> dict:
    reserve = (3 * max_requests) // 7
    return {"matching_attempt_limit": min(20, max_requests - reserve),
            "discovery_request_reserve": reserve}


def credit_diagnostics(record: dict) -> dict:
    credits = extract_credits(record)
    direct = [c for c in credits if c["category"] and not c["primary_artist"] and c["scope"] == "recording"]
    work = [c for c in credits if c["category"] and c["scope"] == "work"]
    return {"primary_artist_credits": sum(c["primary_artist"] for c in credits),
            "additional_direct_categories": sorted({c["category"] for c in direct}),
            "work_categories": sorted({c["category"] for c in work}),
            "additional_contributor_credits_observed": bool(direct or work),
            "contributor_routes": len({c["artist"]["id"] for c in credits if c["category"]}),
            "relations_field_present": "relations" in record,
            "releases_field_present": "releases" in record,
            "note": "matched; no additional contributor credits observed" if not direct and not work else "additional credits observed"}
