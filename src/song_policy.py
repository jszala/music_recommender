"""Source-bound discovery eligibility and observed performing identities (D-018)."""

import json
from pathlib import Path
import re
import unicodedata

from .credits import extract_credits
from .fetch_musicbrainz import digest, json_bytes, mbid


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def submitted_artists(tracks: list[dict]) -> list[dict]:
    names = {}
    for row in tracks:
        if not row.get("artist_text"):
            continue
        key = normalized_name(row["artist_text"])
        item = names.setdefault(key, {"name": row["artist_text"], "normalized_name": key, "source_lines": []})
        if row.get("line_number") is not None:
            item["source_lines"].append(row["line_number"])
    return [names[key] | {"source_lines": sorted(set(names[key]["source_lines"]))} for key in sorted(names)]


def build_registry(records: list[dict], favorite_ids: list[str], *, names: list[dict] | None = None,
                   input_sha256: str | None = None) -> dict:
    by_id = {r["id"]: r for r in records}
    if set(favorite_ids) - by_id.keys():
        raise ValueError("Unknown favorite recording IDs for artist registry")
    artists, derived_names = {}, []
    for rid in sorted(set(favorite_ids)):
        for credit in by_id[rid].get("artist-credit", []):
            if not isinstance(credit, dict):
                continue
            artist = credit["artist"]
            aid = artist["id"]
            item = artists.setdefault(aid, {"id": aid, "name": artist["name"], "recording_ids": []})
            item["recording_ids"].append(rid)
            derived_names.append({"artist_text": credit.get("name", artist["name"])})
    return {"format_version": 1, "policy": "D-018", "input_sha256": input_sha256,
            "scope": "full_input" if names is not None else "training_recordings",
            "submitted_names": submitted_artists(derived_names) if names is None else names,
            "submitted_artists": [artists[aid] | {"recording_ids": sorted(set(artists[aid]["recording_ids"]))} for aid in sorted(artists)],
            "related_performers": [], "group_members": [], "allowed_aliases": [],
            "verified_collaborations": []}


def validate_registry(registry: dict) -> None:
    if registry.get("format_version") != 1 or registry.get("policy") != "D-018":
        raise ValueError("Unsupported artist registry")
    for row in registry["submitted_names"]:
        if not row["name"] or row["normalized_name"] != normalized_name(row["name"]):
            raise ValueError("Invalid submitted artist name")
    for row in registry["submitted_artists"]:
        mbid(row["id"])
    for key in ("related_performers", "group_members", "allowed_aliases", "verified_collaborations"):
        for row in registry.get(key, []):
            if not isinstance(row.get("evidence"), str) or not row["evidence"].strip():
                raise ValueError(f"Artist-policy {key} needs evidence")
            fields = ({"related_performers": ("artist_id",), "group_members": ("group_id", "member_id"),
                       "allowed_aliases": ("artist_id",), "verified_collaborations": ("recording_id",)})[key]
            for field in fields:
                mbid(row[field])
            if key == "allowed_aliases":
                name = normalized_name(row["credited_name"])
                if not name or name in {r["normalized_name"] for r in registry["submitted_names"]}:
                    raise ValueError("Allowed alias must be a distinct, nonsubmitted credited name")


def registry_for(records: list[dict], favorite_ids: list[str], *, profile: dict | None = None,
                 input_path: Path | None = None, overrides_path: Path | None = None,
                 training_only: bool = False) -> dict:
    profile = {} if profile is None else profile
    expected = profile.get("input_sha256")
    if training_only:
        registry = build_registry(records, favorite_ids, input_sha256=expected)
    elif input_path is not None:
        raw = input_path.read_bytes()
        data = json.loads(raw)
        if data.get("format_version") != 1 or not isinstance(data.get("tracks"), list):
            raise ValueError("Expected version-1 favorites input")
        if expected is not None and digest(raw) != expected:
            raise ValueError("Artist exclusions belong to a different favorites input")
        registry = build_registry(records, favorite_ids,
                                  names=submitted_artists(data["tracks"] + data.get("needs_review", [])),
                                  input_sha256=digest(raw))
    elif profile.get("artist_registry") is not None:
        registry = json.loads(json.dumps(profile["artist_registry"]))
        if registry.get("input_sha256") != expected:
            raise ValueError("Artist registry belongs to a different favorites input")
    else:
        registry = build_registry(records, favorite_ids, input_sha256=expected)
    if overrides_path is not None:
        raw = overrides_path.read_bytes()
        overrides = json.loads(raw)
        if overrides.get("format_version") != 1 or overrides.get("input_sha256") != registry["input_sha256"]:
            raise ValueError("Artist-policy overrides belong to a different favorites input")
        for key in ("related_performers", "group_members", "allowed_aliases", "verified_collaborations"):
            registry[key] = overrides.get(key, registry.get(key, []))
        registry["overrides_sha256"] = digest(raw)
    validate_registry(registry)
    return registry


def registry_digest(registry: dict) -> str:
    return digest(json_bytes(registry))


def active_musicians(record: dict) -> list[dict]:
    artists = {}
    for credit in extract_credits(record):
        if credit["category"] != "musician":
            continue
        # Sampled performances are not active participation in this recording.
        if any("sample" in attr.casefold() for attr in credit["attributes"]):
            continue
        artist = credit["artist"]
        item = artists.setdefault(artist["id"], {"artist": artist, "primary_credit": False, "roles": set()})
        item["primary_credit"] |= credit["primary_artist"]
        item["roles"].add(credit["role"])
    return [artists[aid] | {"roles": sorted(artists[aid]["roles"])} for aid in sorted(artists)]


def candidate_eligibility(record: dict, registry: dict) -> dict:
    """Primary joint credits are collaboration evidence, except ambiguous/sample routes."""
    primary = [c for c in record.get("artist-credit", []) if isinstance(c, dict)]
    blocked_ids = {a["id"] for a in registry["submitted_artists"]}
    blocked_names = {a["normalized_name"] for a in registry["submitted_names"]}
    aliases = {(a["artist_id"], normalized_name(a["credited_name"])) for a in registry.get("allowed_aliases", [])}
    musicians = active_musicians(record)
    musician_ids = {a["artist"]["id"] for a in musicians}
    blocked, alias_ids = set(), set()
    for credit in primary:
        artist = credit["artist"]
        name = normalized_name(credit.get("name", artist["name"]))
        if (artist["id"], name) in aliases:
            alias_ids.add(artist["id"])
        elif artist["id"] in blocked_ids or name in blocked_names or normalized_name(artist["name"]) in blocked_names:
            blocked.add(artist["id"])
    # Combined submitted credits can be unresolved even if their components are new IDs.
    combined = normalized_name("".join(c.get("name", c["artist"]["name"]) + c.get("joinphrase", "")
                                       if isinstance(c, dict) else c for c in record.get("artist-credit", [])))
    if combined in blocked_names and not alias_ids:
        blocked.update(c["artist"]["id"] for c in primary)
    related = {r["artist_id"] for r in registry.get("related_performers", [])}
    for credit in extract_credits(record):
        if credit["artist"]["id"] in musician_ids and normalized_name(credit["artist"]["name"]) in blocked_names:
            related.add(credit["artist"]["id"])
    familiar = (musician_ids & (blocked_ids | related | blocked)) - alias_ids
    members = {(r["group_id"], r["member_id"]) for r in registry.get("group_members", [])}
    # An explicitly known member appearing within a permitted side project is not a guest collaboration.
    project_members = {member for group, member in members
                       if group not in blocked_ids and group in {c["artist"]["id"] for c in primary}}
    familiar -= project_members
    family = familiar | {member for group, member in members if group in familiar}
    unfamiliar_primary = {c["artist"]["id"] for c in primary} - family - blocked - alias_ids
    verified = record["id"] in {r["recording_id"] for r in registry.get("verified_collaborations", [])}
    detailed_familiar = any(c["category"] == "musician" and not c["primary_artist"]
                            and c["artist"]["id"] in familiar for c in extract_credits(record))
    description = record.get("title", "") + " " + record.get("disambiguation", "")
    ambiguous = bool(re.search(r"\b(mash[- ]?up|medley|DJ mix|collage)\b", description, re.I))
    ambiguous |= any("sample" in attr.casefold() for c in extract_credits(record) for attr in c["attributes"])
    result = {"eligible": True, "reason": "unfamiliar_act", "familiar_collaboration": False,
              "blocked_primary_artist_ids": sorted(blocked), "familiar_musician_ids": sorted(familiar),
              "musicians": musicians, "unfamiliar_primary_artist_ids": sorted(unfamiliar_primary)}
    if not primary:
        return result | {"eligible": False, "reason": "missing_primary_artist"}
    if blocked and not unfamiliar_primary:
        return result | {"eligible": False, "reason": "submitted_act_without_unfamiliar_collaborator"}
    if unfamiliar_primary and (familiar or blocked):
        if not verified and (ambiguous or not detailed_familiar):
            return result | {"eligible": False, "reason": "collaboration_needs_review"}
        return result | {"reason": "familiar_collaboration", "familiar_collaboration": True}
    if alias_ids:
        result["reason"] = "allowed_alias"
    return result
