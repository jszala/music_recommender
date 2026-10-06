"""Project recording credits into undirected, recording-backed artist edges."""

from dataclasses import dataclass
from itertools import combinations
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "data" / "fixture"


def load_rules(path: Path = ROOT / "config" / "graph_rules.yml") -> dict:
    # JSON is a YAML 1.2 subset. Keeping this config in that subset avoids a dependency.
    rules = json.loads(path.read_text(encoding="utf-8"))
    if rules["format_version"] != 1:
        raise ValueError("Unsupported graph-rule version")
    return rules


def load_fixture(directory: Path = DEFAULT_FIXTURE) -> tuple[list[dict], dict]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported fixture version")
    records = [json.loads((directory / s["snapshot_file"]).read_text(encoding="utf-8"))
               for s in manifest["sources"]]
    return records, manifest


@dataclass
class Graph:
    artists: dict[str, dict]
    recordings: dict[str, dict]
    credits: dict[str, dict[str, list[dict]]]
    adjacency: dict[str, dict[str, list[dict]]]
    exclusions: list[dict]

    def evidence(self, left: str, right: str) -> list[dict]:
        return self.adjacency.get(left, {}).get(right, [])

    def stats(self) -> dict:
        edges = sum(len(neighbors) for neighbors in self.adjacency.values()) // 2
        evidence_count = sum(len(e) for n in self.adjacency.values() for e in n.values()) // 2
        return {
            "artists": len(self.artists), "recordings": len(self.recordings),
            "edges": edges, "edge_contributions": evidence_count,
            "exclusions": len(self.exclusions),
            "artist_degrees": {a: len(self.adjacency[a]) for a in sorted(self.artists)},
            "recording_density": [
                {"recording_id": r, "title": self.recordings[r]["title"],
                 "eligible_artists": len(self.credits[r]),
                 "edges": len(self.credits[r]) * (len(self.credits[r]) - 1) // 2}
                for r in sorted(self.recordings)
            ],
        }


def build_graph(records: list[dict], rules: dict | None = None) -> Graph:
    rules = load_rules() if rules is None else rules
    artists, recordings, credits, excluded = {}, {}, {}, {}

    def add_credit(recording: dict, artist: dict, role: str, relation: dict,
                   level: str = "recording", work_id: str | None = None,
                   primary: bool = False) -> None:
        rid, aid = recording["id"], artist["id"]
        attributes = sorted(set(relation.get("attributes", [])))
        credit = {
            "artist_id": aid, "role": role,
            "relationship_type_id": relation.get("type-id"),
            "attributes": attributes,
            "attribute_values": relation.get("attribute-values", {}),
            "begin": relation.get("begin"), "end": relation.get("end"),
        }
        reason = None
        if level != "recording":
            reason = f"{level}-level credit"
        elif set(a.casefold() for a in attributes) & set(rules["excluded_attributes"]):
            reason = "excluded executive attribute"
        elif not primary and relation.get("type-id") not in rules["eligible_relationships"]:
            reason = "relationship type outside allowlist"
        if reason:
            exclusion = {"recording_id": rid, "artist": artist, "credit": credit,
                         "level": level, "work_id": work_id, "reason": reason,
                         "source_url": f"https://musicbrainz.org/recording/{rid}"}
            excluded[json.dumps(exclusion, sort_keys=True)] = exclusion
            return
        artists.setdefault(aid, {"id": aid, "name": artist["name"],
                                 "type": artist.get("type", "Unknown")})
        artist_credits = credits[rid].setdefault(aid, {})
        artist_credits[json.dumps(credit, sort_keys=True)] = credit

    for record in records:
        rid = record["id"]
        metadata = {"id": rid, "title": record["title"],
                    "disambiguation": record.get("disambiguation", ""),
                    "source_url": f"https://musicbrainz.org/recording/{rid}"}
        if rid in recordings and recordings[rid] != metadata:
            raise ValueError(f"Conflicting metadata for recording {rid}")
        recordings[rid] = metadata
        credits.setdefault(rid, {})
        if rules["include_primary_recording_artists"]:
            for primary in record.get("artist-credit", []):
                if isinstance(primary, dict):
                    add_credit(record, primary["artist"], "primary artist", {}, primary=True)
        for relation in record.get("relations", []):
            if relation["target-type"] == "artist":
                role = rules["eligible_relationships"].get(relation.get("type-id"), relation["type"])
                add_credit(record, relation["artist"], role, relation,
                           level=relation.get("level", "recording"))
            elif relation["target-type"] == "work":
                for work_relation in relation["work"].get("relations", []):
                    if work_relation["target-type"] == "artist":
                        add_credit(record, work_relation["artist"], work_relation["type"],
                                   work_relation, "work", relation["work"]["id"])

    normalized = {r: {a: [c[k] for k in sorted(c)] for a, c in sorted(by_artist.items())}
                  for r, by_artist in sorted(credits.items())}
    adjacency = {a: {} for a in sorted(artists)}
    for rid, by_artist in normalized.items():
        for left, right in combinations(by_artist, 2):
            evidence = {"recording": recordings[rid],
                        "credits": {left: by_artist[left], right: by_artist[right]}}
            adjacency[left].setdefault(right, []).append(evidence)
            adjacency[right].setdefault(left, []).append(evidence)
    return Graph(artists, recordings, normalized, adjacency,
                 [excluded[k] for k in sorted(excluded)])
