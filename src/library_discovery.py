"""Persistent breadth-first contributor discovery over a consolidated profile."""

from collections import Counter
from pathlib import Path

from .build_graph import load_dataset, load_rules
from .collect_song_graph import balanced_frontier
from .credits import SONGWRITING_IDS, extract_credits
from .fetch_musicbrainz import FetchError, digest, json_bytes, mbid
from .library_job import atomic_json, read_json
from .match_recordings import MATCH_INCLUDES
from .song_policy import candidate_eligibility


def discover(job, client, matching: Path, profile: dict, rules: dict, seed_graph: Path | None = None,
             progress=None, retry_failures=False):
    path = job.directory / "discovery_state.json"
    storage = job.directory / "discovery_recordings"
    storage.mkdir(exist_ok=True)
    favorites, original_manifest = load_dataset(matching)
    training = {f["recording_id"] for f in profile["favorites"]}
    registry = profile["artist_registry"]
    originals = {r["id"]: r for r in favorites if r["id"] in training}
    state = read_json(path) if path.exists() else None
    if state is not None and state["failures"] and retry_failures:
        # Re-evaluate failed routes from the frozen successful operations. Budgets
        # stay in the job manifest; no completed transport needs to be repeated.
        history = job.state.setdefault("discovery_failure_history", [])
        archive = job.directory / f"discovery_state.failure-pass-{len(history) + 1}.json"
        atomic_json(archive, state)
        history.append(str(archive.relative_to(job.directory)))
        job.save()
        state = None

    def freeze(record, source, origin):
        rid = mbid(record["id"])
        if (not record.get("title") or not isinstance(record.get("artist-credit"), list)
                or not isinstance(record.get("relations"), list)):
            raise ValueError("Malformed discovery recording")
        extract_credits(record)
        raw = json_bytes(record)
        if rid in state["sources"]:
            if state["sources"][rid]["sha256"] != digest(raw):
                raise ValueError(f"Conflicting duplicate recording snapshots: {rid}")
            if origin not in state["sources"][rid]["origins"]:
                state["sources"][rid]["origins"].append(origin)
            return
        atomic_json(storage / f"{rid}.json", record)
        state["sources"][rid] = source | {"recording_id": rid, "sha256": digest(raw),
                                         "snapshot_file": f"recordings/{rid}.json",
                                         "source_url": f"https://musicbrainz.org/recording/{rid}",
                                         "origins": [origin]}

    if state is None:
        frontier = {}
        for rid, record in sorted(originals.items()):
            for credit in extract_credits(record):
                if credit["category"]:
                    aid = credit["artist"]["id"]
                    item = frontier.setdefault(aid, {"artist": credit["artist"], "recording_ids": set(), "categories": set()})
                    item["recording_ids"].add(rid)
                    item["categories"].add(credit["category"])
        order = balanced_frontier(frontier, originals, training) if frontier else []
        state = {"order": order, "round": 1, "route_index": 0, "sources": {}, "eligible_ids": [],
                 "failures": [], "exclusions": [], "complete": False,
                 "routes": {aid: {"artist_id": aid, "favorite_recording_ids": sorted(frontier[aid]["recording_ids"]),
                                  "categories": sorted(frontier[aid]["categories"]), "initialized": False,
                                  "works": [], "work_cursor": 0, "omitted_work_ids": [],
                                  "queue": [], "seen": [], "pool": {}, "metadata": {}, "pages": [],
                                  "offset": 0, "browse_complete": False, "candidate_lookups": 0,
                                  "selected_recording_ids": [], "exhausted": False} for aid in order}}
        sources = {s["recording_id"]: s for s in original_manifest["sources"]}
        for rid in sorted(training):
            freeze(originals[rid], sources[rid], {"stage": "training_favorite"})
        if seed_graph:
            seeds, manifest = load_dataset(seed_graph)
            if manifest.get("input_sha256") != profile["input_sha256"]:
                raise ValueError("Seed graph belongs to a different favorites input")
            seed_sources = {s["recording_id"]: s for s in manifest["sources"]}
            for record in seeds:
                rid = record["id"]
                if rid in training:
                    freeze(record, seed_sources[rid], {"stage": "historical_favorite"})
                    continue
                policy = candidate_eligibility(record, registry)
                if not policy["eligible"]:
                    state["exclusions"].append({"recording_id": rid, "stage": "seed_graph", "reason": policy["reason"]})
                    continue
                # Only reuse candidates that share a supported contributor with this profile.
                if not ({c["artist"]["id"] for c in extract_credits(record) if c["category"]} & set(order)):
                    continue
                freeze(record, seed_sources[rid], {"stage": "historical_candidate"})
                state["eligible_ids"].append(rid)
        state["eligible_ids"].sort()
        atomic_json(path, state)

    def checkpoint():
        atomic_json(path, state)

    def fetch(endpoint, **params):
        try:
            return client.get(endpoint, **params)
        except FetchError as error:
            state["failures"].append({"endpoint": endpoint, "params": params, "error": str(error)})
            return None

    def add(route, rid, origin, metadata=None):
        rid = mbid(rid)
        route["pool"].setdefault(rid, [])
        if origin not in route["pool"][rid]:
            route["pool"][rid].append(origin)
        if rid not in route["seen"] and rid not in route["queue"]:
            route["queue"].append(rid)
        if metadata is not None:
            route["metadata"][rid] = metadata

    def initialize(route):
        aid = route["artist_id"]
        body = fetch(f"artist/{aid}", inc="recording-rels+work-rels")
        if body is not None:
            if body.get("id") != aid or not isinstance(body.get("relations"), list):
                raise ValueError("Malformed contributor relationships")
            works = set()
            for relation in body["relations"]:
                if "executive" in {a.casefold() for a in relation.get("attributes", [])}:
                    continue
                target = relation.get("target-type")
                if target == "recording" and relation.get("type-id") in load_rules()["eligible_relationships"]:
                    add(route, relation["recording"]["id"], "artist recording relationship")
                elif target == "work" and relation.get("type-id") in SONGWRITING_IDS:
                    works.add(mbid(relation["work"]["id"]))
            route["works"] = sorted(works)[:rules["works_per_contributor"]]
            route["omitted_work_ids"] = sorted(works)[rules["works_per_contributor"]:]
            route["artist_relationships_returned"] = len(body["relations"])
        route["queue"].sort()
        route["initialized"] = True
        checkpoint()

    def refill(route):
        if route["work_cursor"] < len(route["works"]):
            wid = route["works"][route["work_cursor"]]
            body = fetch(f"work/{wid}", inc="recording-rels")
            if body is not None:
                if body.get("id") != wid or not isinstance(body.get("relations"), list):
                    raise ValueError("Malformed songwriting-work relationships")
                for relation in body["relations"]:
                    if relation.get("target-type") == "recording":
                        add(route, relation["recording"]["id"], f"songwriting work {wid}")
            route["work_cursor"] += 1
        elif not route["browse_complete"] and len(route["pages"]) < rules["max_browse_pages"]:
            offset = route["offset"]
            body = fetch("recording", artist=route["artist_id"], inc="artist-credits",
                         limit=rules["browse_page_size"], offset=offset)
            if body is None:
                route["browse_complete"] = True
            else:
                returned, total = body.get("recordings"), body.get("recording-count")
                if (not isinstance(returned, list) or len(returned) > rules["browse_page_size"]
                        or type(total) is not int or total < offset + len(returned)
                        or body.get("recording-offset", offset) != offset):
                    raise ValueError("Malformed contributor browse page")
                for record in returned:
                    add(route, record["id"], "primary-credit browse", record)
                route["pages"].append({"offset": offset, "returned_ids": [r["id"] for r in returned],
                                       "reported_total": total, "source": client.events[-1]})
                route["offset"] += len(returned)
                route["browse_complete"] = route["offset"] >= total or not returned
                route["browse_unfetched_count"] = total - route["offset"]
        else:
            route["exhausted"] = True
        route["queue"].sort()
        checkpoint()

    def seek(route, target):
        if not route["initialized"]:
            initialize(route)
        while len(route["selected_recording_ids"]) < target and not route["exhausted"]:
            if route["candidate_lookups"] >= rules["candidate_lookups_per_contributor"]:
                route["exhausted"] = True
                checkpoint()
                break
            if not route["queue"]:
                refill(route)
                continue
            rid = route["queue"][0]
            metadata = route["metadata"].get(rid)
            reason = "favorite_recording" if rid in training else None
            if not reason and metadata and metadata.get("artist-credit"):
                policy = candidate_eligibility(metadata, registry)
                if policy["reason"] == "submitted_act_without_unfamiliar_collaborator":
                    reason = policy["reason"]
            record = None
            if not reason:
                if rid in state["sources"]:
                    record = read_json(storage / f"{rid}.json")
                else:
                    record = fetch(f"recording/{rid}", inc=MATCH_INCLUDES)
                    route["candidate_lookups"] += 1
                    if record is not None:
                        if record.get("id") != rid:
                            raise ValueError("Discovery lookup returned another recording")
                        source = {k: client.events[-1][k] for k in ("query", "retrieved_at", "response_sha256", "cache_file")}
                        freeze(record, source, {"stage": "candidate", "artist_id": route["artist_id"],
                                                "routes": route["pool"][rid]})
                if record is not None:
                    policy = candidate_eligibility(record, registry)
                    reason = None if policy["eligible"] else policy["reason"]
                    # A route is retrieval evidence; the recording must actually share supported credits.
                    if not reason and not ({c["artist"]["id"] for c in extract_credits(record) if c["category"]}
                                           & set(state["order"])):
                        reason = "no_supported_shared_contributor"
                    if not reason:
                        route["selected_recording_ids"].append(rid)
                        if rid not in state["eligible_ids"]:
                            state["eligible_ids"].append(rid)
                            state["eligible_ids"].sort()
                else:
                    reason = "lookup_failure"
            if reason:
                state["exclusions"].append({"recording_id": rid, "artist_id": route["artist_id"],
                                            "reason": reason, "source": state["sources"].get(rid)})
            route["queue"].pop(0)
            route["seen"].append(rid)
            checkpoint()

    while not state["complete"]:
        explored = sum(r["initialized"] for r in state["routes"].values())
        if (len(state["eligible_ids"]) >= rules["candidate_target"]
                and explored >= min(len(state["order"]), rules["minimum_routes"])):
            state["stop_reason"] = "pool_and_breadth_targets"
            state["complete"] = True
            checkpoint()
            break
        if state["round"] > rules["recordings_per_contributor"] or not state["order"]:
            state["stop_reason"] = "frontier_exhausted_or_route_limits"
            state["complete"] = True
            checkpoint()
            break
        if state["route_index"] >= len(state["order"]):
            state["round"] += 1
            state["route_index"] = 0
            checkpoint()
            continue
        aid = state["order"][state["route_index"]]
        seek(state["routes"][aid], state["round"])
        state["route_index"] += 1
        checkpoint()
        if progress:
            progress("discovery", {"routes_explored": sum(r["initialized"] for r in state["routes"].values()),
                                   "routes_total": len(state["order"]), "eligible_candidates": len(state["eligible_ids"])})
    return discovery_snapshot(job, profile)


def discovery_snapshot(job, profile):
    path = job.directory / "discovery_state.json"
    storage = job.directory / "discovery_recordings"
    state = read_json(path)
    training = {f["recording_id"] for f in profile["favorites"]}
    originals = {rid: read_json(storage / f"{rid}.json") for rid in training}
    ids = training | set(state["eligible_ids"])
    records = [read_json(storage / f"{rid}.json") for rid in sorted(ids)]
    sources = [state["sources"][rid] for rid in sorted(ids)]
    state["summary"] = {"frontier_routes": len(state["order"]),
                        "explored_routes": sum(r["initialized"] for r in state["routes"].values()),
                        "unexplored_routes": sum(not r["initialized"] for r in state["routes"].values()),
                        "exhausted_routes": sum(r["exhausted"] for r in state["routes"].values()),
                        "eligible_candidates": len(state["eligible_ids"]),
                        "exclusion_counts": dict(Counter(e["reason"] for e in state["exclusions"])),
                        "failures": len(state["failures"]), "stop_reason": state.get("stop_reason")}
    groups = {credit["artist"]["id"] for record in originals.values() for credit in record["artist-credit"] if isinstance(credit, dict)}
    reached = {credit["artist"]["id"] for route in state["routes"].values() if route["initialized"]
               for rid in route["favorite_recording_ids"] for credit in originals[rid]["artist-credit"] if isinstance(credit, dict)}
    state["summary"].update(favorite_artist_groups=len(groups), explored_artist_groups=len(reached),
                            unexplored_artist_groups=len(groups - reached),
                            shared_favorite_routes=sum(len(r["favorite_recording_ids"]) > 1 for r in state["routes"].values()),
                            omitted_songwriting_works=sum(len(r["omitted_work_ids"]) for r in state["routes"].values()),
                            categories=dict(Counter(category for route in state["routes"].values() if route["initialized"]
                                                    for category in route["categories"])))
    atomic_json(path, state)
    return records, sources, state
