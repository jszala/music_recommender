"""Preserve contributor credits and their source scope without inferring importance."""

from collections import Counter
import json

from .build_graph import load_rules


SONGWRITING_IDS = {
    "a255bca1-b157-4518-9108-7b147dc3fc68": "writer",
    "d59d99ea-23d4-4a80-b066-edca32ee158f": "composer",
    "3e48faba-ec01-47fd-8e89-30e81161661c": "lyricist",
    "7474ab81-486f-40b5-8685-3a4f8ea624cb": "librettist",
}


def extract_credits(recording: dict) -> list[dict]:
    """One row per distinct observed credit; categories are not numerical weights."""
    roles = load_rules()["eligible_relationships"]
    rows = {}

    def add(artist, role, relation, scope, *, work=None, primary=False):
        if not artist.get("id") or not artist.get("name"):
            raise ValueError("Credit lacks an artist ID/name")
        attributes = sorted(set(relation.get("attributes", [])))
        category, reason = None, None
        type_id = relation.get("type-id")
        if primary:
            category = "musician"
        elif "executive" in {a.casefold() for a in attributes}:
            reason = "executive attribute"
        elif scope == "work" and type_id in SONGWRITING_IDS:
            category = "songwriter"
        elif scope == "recording" and type_id in roles:
            known_role = roles[type_id]
            category = ("musician" if known_role in {"performer", "instrument", "vocal"}
                        else "producer" if known_role == "producer" else "staff")
        else:
            reason = "unmapped relationship or scope; retained for review"
        credit = {
            "recording_id": recording["id"], "artist": {
                k: artist[k] for k in ("id", "name", "type") if k in artist},
            "role": role, "category": category, "scope": scope,
            "relationship_type_id": type_id, "attributes": attributes,
            "attribute_values": relation.get("attribute-values", {}),
            "attribute_credits": relation.get("attribute-credits", {}),
            "begin": relation.get("begin"), "end": relation.get("end"),
            "primary_artist": primary, "classification_note": reason,
            "work_id": work["id"] if work else None,
            "work_title": work.get("title") if work else None,
            "work_link": work.get("link") if work else None,
            "source_url": f"https://musicbrainz.org/{'work' if work else 'recording'}/{work['id'] if work else recording['id']}",
        }
        rows[json.dumps(credit, sort_keys=True)] = credit

    for primary in recording.get("artist-credit", []):
        if isinstance(primary, dict):
            add(primary["artist"], "primary artist", {}, "recording", primary=True)
    for relation in recording.get("relations", []):
        if relation.get("target-type") == "artist":
            add(relation["artist"], relation["type"], relation,
                relation.get("level", "recording"))
        elif relation.get("target-type") == "work":
            work = relation["work"]
            provenance = {"id": work["id"], "title": work.get("title"),
                          "link": {k: relation[k] for k in
                                   ("type", "type-id", "attributes") if k in relation}}
            for work_relation in work.get("relations", []):
                if work_relation.get("target-type") == "artist":
                    add(work_relation["artist"], work_relation["type"], work_relation,
                        "work", work=provenance)
    return [rows[key] for key in sorted(rows)]


def credit_coverage(records: list[dict]) -> dict:
    """Observed presence only: missing data is not proof that a role was absent."""
    records_by_id = {r["id"]: r for r in records}
    counts, unmapped, details = Counter(), Counter(), []
    for rid, record in sorted(records_by_id.items()):
        credits = extract_credits(record)
        categories = {c["category"] for c in credits if c["category"]}
        for category in categories:
            counts[category] += 1
        for credit in credits:
            if credit["category"] is None:
                unmapped[(credit["scope"], credit["role"], credit["classification_note"])] += 1
        by_artist = {}
        for credit in credits:
            by_artist.setdefault(credit["artist"]["id"], set()).add(credit["category"])
        details.append({"recording_id": rid, "title": record["title"],
                        "categories_observed": sorted(categories),
                        "distinct_credit_rows": len(credits),
                        "detailed_performance_credits_observed": any(
                            c["category"] == "musician" and not c["primary_artist"] for c in credits),
                        "musician_and_songwriter_entities": sorted(
                            aid for aid, cats in by_artist.items()
                            if {"musician", "songwriter"} <= cats)})
    return {"recordings_inspected": len(records_by_id),
            "recordings_with_category": {c: counts[c] for c in
                                         ("musician", "songwriter", "producer", "staff")},
            "unmapped_credits": [{"scope": scope, "role": role, "reason": reason, "count": count}
                                 for (scope, role, reason), count in sorted(unmapped.items())],
            "recordings": details,
            "interpretation": "Observed credit presence, not completeness; release credits were not queried."}
