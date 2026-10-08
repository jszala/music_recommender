"""Observed composition identities for balancing; equal titles imply nothing."""


def known_work_ids(record: dict) -> set[str]:
    return {relation["work"]["id"] for relation in record.get("relations", [])
            if relation.get("target-type") == "work" and relation.get("work", {}).get("id")}


def source_song_groups(records: list[dict], favorite_ids) -> tuple[dict, dict]:
    by_id = {r["id"]: r for r in records}
    mapping, groups = {}, {}
    for rid in sorted(set(favorite_ids)):
        record = by_id[rid]
        works = sorted(known_work_ids(record))
        key = "work:" + "+".join(works) if works else "recording:" + rid
        mapping[rid] = key
        group = groups.setdefault(key, {"source_group_id": key, "favorite_recording_ids": [],
                                       "titles": [], "known_work_ids": works,
                                       "composition_identity_known": bool(works)})
        group["favorite_recording_ids"].append(rid)
        group["titles"].append(record["title"])
    return mapping, groups


def assignment_evidence(row: dict, mapping: dict) -> dict:
    evidence = {}
    for contribution in row["contributions"]:
        if contribution["value"] > 0:
            group = mapping[contribution["favorite_recording_id"]]
            evidence[group] = evidence.get(group, 0.0) + contribution["value"]
    return evidence
