"""Collect bounded song candidates from accepted training recordings and their credits."""

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .build_graph import ROOT, load_dataset, load_rules
from .credits import SONGWRITING_IDS, credit_coverage, extract_credits
from .fetch_musicbrainz import FetchError, Limits, MusicBrainzClient, digest, json_bytes, mbid, save_json
from .match_recordings import MATCH_INCLUDES
from .recommend_songs import profile_favorites
from .song_policy import candidate_eligibility, registry_digest, registry_for


@dataclass(frozen=True)
class CollectionRules:
    contributors: int = 12
    recordings_per_contributor: int = 6
    browse_page_size: int = 25
    max_browse_pages: int = 2
    works_per_contributor: int = 2
    candidate_lookups_per_contributor: int = 18

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()) or self.browse_page_size > 100:
            raise ValueError("Collection limits must be positive integers; browse pages cannot exceed 100")


def balanced_frontier(frontier: dict, records: dict, training: set[str]) -> list[str]:
    """Round-robin favorite acts, preferring routes beyond that act's own discography."""
    groups = {}
    for rid in sorted(training):
        for credit in records[rid].get("artist-credit", []):
            if isinstance(credit, dict):
                groups.setdefault(credit["artist"]["id"], set()).add(rid)
    queues = {gid: sorted((aid for aid, item in frontier.items() if item["recording_ids"] & rids),
                          key=lambda aid: (aid in groups, aid)) for gid, rids in groups.items()}
    ordered, seen = [], set()
    while any(queues.values()):
        for gid in sorted(queues):
            while queues[gid] and queues[gid][0] in seen:
                queues[gid].pop(0)
            if queues[gid]:
                aid = queues[gid].pop(0)
                ordered.append(aid)
                seen.add(aid)
    return ordered


def collect_song_graph(client: MusicBrainzClient, matched_dir: Path, profile_path: Path,
                       output: Path, rules: CollectionRules, favorite_ids: list[str] | None = None,
                       progress=None, input_path: Path | None = None,
                       overrides_path: Path | None = None) -> dict:
    originals, original_manifest = load_dataset(matched_dir)
    accepted = set(profile_favorites(profile_path, original_manifest))
    training = accepted if favorite_ids is None else set(favorite_ids)
    if not training or training - accepted:
        raise ValueError("Collection needs a nonempty subset of accepted favorite recordings")
    by_id = {r["id"]: r for r in originals}
    original_sources = {s["recording_id"]: s for s in original_manifest["sources"]}
    profile = json.loads(profile_path.read_bytes())
    registry = registry_for(originals, sorted(training), profile=profile, input_path=input_path,
                            overrides_path=overrides_path, training_only=favorite_ids is not None)
    if favorite_ids is None and profile.get("input_sha256") and registry["scope"] != "full_input":
        raise ValueError("Older profile lacks full-input artist exclusions; supply --input")
    output.mkdir(parents=True, exist_ok=False)
    (output / "recordings").mkdir()
    records, sources, failures, selections = {}, {}, [], []

    def freeze(record, source, origin):
        rid = record["id"]
        if rid in records:
            sources[rid]["origins"].append(origin)
            return
        relative = f"recordings/{rid}.json"
        data = json_bytes(record)
        (output / relative).write_bytes(data)
        records[rid] = record
        sources[rid] = source | {"recording_id": rid, "snapshot_file": relative, "sha256": digest(data),
                                 "source_url": f"https://musicbrainz.org/recording/{rid}", "origins": [origin]}

    for rid in sorted(training):
        freeze(by_id[rid], original_sources[rid], {"stage": "training_favorite"})
    frontier = {}
    for rid in sorted(training):
        for credit in extract_credits(by_id[rid]):
            if credit["category"]:
                aid = credit["artist"]["id"]
                item = frontier.setdefault(aid, {"artist": credit["artist"], "recording_ids": set(), "categories": set()})
                item["recording_ids"].add(rid)
                item["categories"].add(credit["category"])
    ordered = balanced_frontier(frontier, by_id, training)
    selected = ordered[:rules.contributors]

    def fetch(endpoint, context, **params):
        try:
            return client.get(endpoint, **params)
        except FetchError as error:
            failures.append({"context": context, "endpoint": endpoint, "params": params, "error": str(error)})
            return None

    def related_id(relation, target):
        try:
            return mbid(relation[target]["id"])
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            failures.append({"context": {"stage": "relationship", "target": target}, "error": str(error)})
            return None

    eligible_recording_relationships = set(load_rules()["eligible_relationships"])
    states = []
    for contributor_number, aid in enumerate(selected, 1):
        if progress:
            progress(contributor_number, len(selected))
        pool, works, pages, browse_metadata = {}, set(), [], {}
        artist = fetch(f"artist/{aid}", {"stage": "artist", "artist_id": aid}, inc="recording-rels+work-rels")
        artist_valid = (artist is not None and artist.get("id") == aid and isinstance(artist.get("relations"), list))
        if artist is not None and not artist_valid:
            failures.append({"context": {"stage": "artist", "artist_id": aid}, "error": "Malformed artist relationships"})
        if artist_valid:
            for relation in artist["relations"]:
                target = relation.get("target-type")
                if "executive" in {a.casefold() for a in relation.get("attributes", [])}:
                    continue
                if target == "recording" and relation.get("type-id") in eligible_recording_relationships:
                    # Keep recording relationships as discovery routes, not inferred credit facts.
                    rid = related_id(relation, "recording")
                    if rid:
                        pool.setdefault(rid, []).append("artist recording relationship")
                elif target == "work" and relation.get("type-id") in SONGWRITING_IDS:
                    wid = related_id(relation, "work")
                    if wid:
                        works.add(wid)
        offset, browse_complete, reported_total = 0, False, None
        for _ in range(rules.max_browse_pages):
            result = fetch("recording", {"stage": "browse", "artist_id": aid}, artist=aid,
                           inc="artist-credits", limit=rules.browse_page_size, offset=offset)
            if result is None:
                break
            returned, total = result.get("recordings"), result.get("recording-count")
            if (not isinstance(returned, list) or len(returned) > rules.browse_page_size
                    or type(total) is not int or total < offset + len(returned)
                    or result.get("recording-offset", offset) != offset):
                failures.append({"context": {"stage": "browse", "artist_id": aid}, "error": "Malformed browse page"})
                break
            ids = []
            for record in returned:
                rid = related_id({"recording": record}, "recording")
                if rid:
                    ids.append(rid)
                    pool.setdefault(rid, []).append("primary-credit browse")
                    browse_metadata[rid] = record
            reported_total = total
            pages.append({"offset": offset, "returned_ids": ids, "reported_total": total,
                          "query": client.events[-1]["query"]})
            offset += len(returned)
            if offset >= total:
                browse_complete = True
                break
            if not returned:
                break
        selected_works = sorted(works)[:rules.works_per_contributor]
        for wid in selected_works:
            work = fetch(f"work/{wid}", {"stage": "songwriter_work", "work_id": wid, "artist_id": aid}, inc="recording-rels")
            if work is None:
                continue
            if work.get("id") != wid or not isinstance(work.get("relations"), list):
                failures.append({"context": {"stage": "work", "work_id": wid}, "error": "Malformed work relationships"})
                continue
            for relation in work["relations"]:
                if relation.get("target-type") == "recording":
                    rid = related_id(relation, "recording")
                    if rid:
                        pool.setdefault(rid, []).append(f"songwriting work {wid}")
        available = sorted(set(pool) - records.keys())
        selection = {"artist_id": aid, "favorite_recording_ids": sorted(frontier[aid]["recording_ids"]),
                           "categories": sorted(frontier[aid]["categories"]),
                           "artist_relationships_returned": len(artist["relations"]) if artist_valid else None,
                           "relationship_completeness": "not certified; no relationship paging interface",
                           "browse_pages": pages, "browse_complete": browse_complete,
                           "browse_reported_total": reported_total,
                           "browse_unfetched_count": reported_total - offset if reported_total is not None else None,
                           "selected_work_ids": selected_works, "omitted_work_ids": sorted(works - set(selected_works)),
                           "selected_recording_ids": [], "omitted_recording_ids": [],
                           "excluded_recordings": [], "candidate_lookups": 0,
                           "allocation": "round_robin_favorite_artists"}
        candidates = []
        for rid in available:
            metadata = browse_metadata.get(rid)
            if metadata and metadata.get("artist-credit"):
                policy = candidate_eligibility(metadata, registry)
                if policy["reason"] == "submitted_act_without_unfamiliar_collaborator":
                    selection["excluded_recordings"].append({"recording_id": rid, "stage": "browse", "reason": policy["reason"]})
                    continue
            candidates.append(rid)
        selections.append(selection)
        states.append({"artist_id": aid, "pool": pool, "queue": candidates, "selection": selection})

    # Alternate detail lookups so a long rejected discography cannot consume the entire budget first.
    while any(state["queue"] and len(state["selection"]["selected_recording_ids"]) < rules.recordings_per_contributor
              and state["selection"]["candidate_lookups"] < rules.candidate_lookups_per_contributor for state in states):
        for state in states:
            selection, aid, pool = state["selection"], state["artist_id"], state["pool"]
            if (not state["queue"] or len(selection["selected_recording_ids"]) >= rules.recordings_per_contributor
                    or selection["candidate_lookups"] >= rules.candidate_lookups_per_contributor):
                continue
            rid = state["queue"].pop(0)
            if rid in records:
                if rid not in training:
                    selection["selected_recording_ids"].append(rid)
                    sources[rid]["origins"].append({"stage": "candidate", "artist_id": aid, "routes": sorted(set(pool[rid]))})
                continue
            selection["candidate_lookups"] += 1
            record = fetch(f"recording/{rid}", {"stage": "candidate", "recording_id": rid, "artist_id": aid}, inc=MATCH_INCLUDES)
            if record is None:
                continue
            policy = candidate_eligibility(record, registry)
            if not policy["eligible"]:
                selection["excluded_recordings"].append({"recording_id": rid, "stage": "lookup", "reason": policy["reason"],
                                                         "eligibility": policy, "source": {key: client.events[-1].get(key) for key in
                                                                                              ("query", "retrieved_at", "response_sha256", "cache_file")}})
                continue
            try:
                if (record.get("id") != rid or not record.get("title")
                        or not isinstance(record.get("artist-credit"), list)
                        or not isinstance(record.get("relations"), list)):
                    raise ValueError("Malformed candidate recording")
                extract_credits(record)
            except (KeyError, ValueError, TypeError) as error:
                failures.append({"context": {"stage": "candidate", "recording_id": rid}, "error": str(error)})
                continue
            event = client.events[-1]
            freeze(record, {k: event[k] for k in ("query", "retrieved_at", "response_sha256", "cache_file")},
                   {"stage": "candidate", "artist_id": aid, "routes": sorted(set(pool[rid]))})
            selection["selected_recording_ids"].append(rid)

    for state in states:
        state["selection"]["omitted_recording_ids"] = state["queue"]
        state["selection"]["eligible_candidate_shortfall"] = max(0, rules.recordings_per_contributor - len(state["selection"]["selected_recording_ids"]))

    profile["artist_registry"] = registry
    profile["favorites"] = [f for f in profile["favorites"] if f["recording_id"] in training]
    for favorite in profile["favorites"]:
        favorite["source_sha256"] = sources[favorite["recording_id"]]["sha256"]
    manifest = {"format_version": 1, "kind": "bounded contributor song graph",
                "input_sha256": profile.get("input_sha256"),
                "candidate_collection_training_recording_ids": sorted(training),
                "profile_source_sha256": digest(profile_path.read_bytes()),
                "artist_registry_sha256": registry_digest(registry), "collection_policy": "D-018",
                "rules": asdict(rules), "limits": asdict(client.limits),
                "sources": [sources[rid] for rid in sorted(sources)],
                "selected_contributor_ids": selected, "omitted_contributor_ids": ordered[len(selected):],
                "selections": selections, "failures": failures, "requests": client.events,
                "network_attempts": client.network_attempts, "offline": client.offline,
                "collection_status": "partial" if failures else "complete_with_declared_limits",
                "stats": {"favorite_recordings": len(training), "candidate_recordings": len(records) - len(training)},
                "independent_human_audit": "pending"}
    manifest["sample_id"] = digest(json_bytes({k: manifest[k] for k in
                                               ("candidate_collection_training_recording_ids", "rules", "sources", "artist_registry_sha256", "selections")}))
    save_json(output / "manifest.json", manifest)
    save_json(output / "profile.json", profile)
    save_json(output / "credit_audit.json", credit_coverage(list(records.values())))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=Path, required=True)
    parser.add_argument("--profile", type=Path, help="Defaults to the matched directory's profile.json")
    parser.add_argument("--favorite", action="append", help="Select accepted training recording IDs only")
    parser.add_argument("--input", type=Path, help="Full favorites input for profiles without a registry")
    parser.add_argument("--policy-overrides", type=Path, help="Source-bound alias and collaborator evidence")
    parser.add_argument("--rules", type=Path, default=ROOT / "config/song_collection_limits.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache/musicbrainz")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contact-file", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        values = json.loads(args.rules.read_bytes())
        if values.pop("format_version") != 1:
            raise ValueError("Unsupported song collection rules")
        rules = CollectionRules(**{k: values[k] for k in CollectionRules.__dataclass_fields__})
        limits = Limits(**{k: v for k, v in values.items() if k not in CollectionRules.__dataclass_fields__})
        contact = args.contact_file.read_text().strip() if args.contact_file else None
        with MusicBrainzClient(args.cache, limits, contact=contact, offline=args.offline) as client:
            manifest = collect_song_graph(client, args.matches, args.profile or args.matches / "profile.json",
                                          args.output, rules, args.favorite,
                                          progress=lambda i, n: print(f"Collecting contributor {i}/{n}", flush=True),
                                          input_path=args.input, overrides_path=args.policy_overrides)
    except (OSError, ValueError, TypeError, KeyError, FetchError) as error:
        parser.error(str(error))
    print(json.dumps({"output": str(args.output), "stats": manifest["stats"],
                      "http_attempts": manifest["network_attempts"], "status": manifest["collection_status"]}, indent=2))
    if manifest["collection_status"] == "partial":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
