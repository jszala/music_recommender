"""Rank recordings through shared contributors with additive roles and artist saturation."""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from .apple_music import country_code, validate_availability
from .build_graph import DEFAULT_FIXTURE, ROOT, load_dataset
from .credits import credit_coverage, extract_credits
from .song_policy import build_registry, candidate_eligibility, registry_digest, registry_for, validate_registry


CATEGORIES = {"musician", "songwriter", "producer", "staff"}
DEFAULT_FAVORITE = "863288d1-0fb0-410f-ac45-98e0bd62eac1"


def load_weights(path: Path = ROOT / "config/song_weights.json") -> dict:
    data = json.loads(path.read_bytes())
    if data.get("format_version") != 1:
        raise ValueError("Unsupported song-weight format")
    validate_weights(data["role_weights"], data["saturation_k"])
    return data


def validate_weights(weights: dict, saturation_k: float | None) -> None:
    if set(weights) != CATEGORIES:
        raise ValueError("Weights must define musician, songwriter, producer, and staff")
    if any(type(w) not in {int, float} or not math.isfinite(w) or w <= 0 for w in weights.values()):
        raise ValueError("Role weights must be finite positive numbers")
    maximum = sum(weights.values())
    if not math.isfinite(maximum * maximum):
        raise ValueError("Role weights overflow shared-contributor arithmetic")
    if saturation_k is not None and (type(saturation_k) not in {int, float}
                                     or not math.isfinite(saturation_k) or saturation_k <= 0):
        raise ValueError("Saturation k must be finite and positive")


def contributor_features(record: dict, weights: dict) -> dict:
    features = {}
    for credit in extract_credits(record):
        if credit["category"] is None:
            continue
        aid = credit["artist"]["id"]
        feature = features.setdefault(aid, {"artist": credit["artist"], "categories": set(), "credits": []})
        feature["categories"].add(credit["category"])
        feature["credits"].append(credit)
    for feature in features.values():
        feature["categories"] = sorted(feature["categories"])
        feature["weight"] = sum(weights[c] for c in feature["categories"])
    return features


def score_song_candidates(records: list[dict], favorite_ids: list[str], *, weights: dict | None = None,
                    saturation_k: float | None = 5.0, excluded_ids: set[str] | None = None) -> list[dict]:
    weights = load_weights()["role_weights"] if weights is None else weights
    validate_weights(weights, saturation_k)
    by_id = {}
    for record in records:
        if record["id"] in by_id and by_id[record["id"]] != record:
            raise ValueError("Conflicting duplicate recording snapshots")
        by_id[record["id"]] = record
    favorites = set(favorite_ids)
    if missing := favorites - by_id.keys():
        raise ValueError(f"Unknown favorite recording IDs: {', '.join(sorted(missing))}")
    if not favorites:
        return []
    excluded = favorites | (set() if excluded_ids is None else set(excluded_ids))
    features = {rid: contributor_features(record, weights) for rid, record in sorted(by_id.items())}
    groups = defaultdict(set)
    for rid in sorted(favorites):
        primaries = {c["artist"]["id"] for c in by_id[rid].get("artist-credit", []) if isinstance(c, dict)}
        if not primaries:
            raise ValueError("Favorite recording lacks primary artist context for saturation")
        for aid in primaries:
            groups[aid].add(rid)
    artists = {f["artist"]["id"]: f["artist"] for by_artist in features.values() for f in by_artist.values()}
    rows = []
    for candidate in sorted(by_id.keys() - excluded):
        contributions, artist_totals = [], []
        for aid, favorite_group in sorted(groups.items()):
            count = len(favorite_group)
            influence = count if saturation_k is None else count / (count + saturation_k)
            group_total = 0.0
            for favorite in sorted(favorite_group):
                shared = sorted(features[favorite].keys() & features[candidate].keys())
                evidence = []
                for contributor in shared:
                    left, right = features[favorite][contributor], features[candidate][contributor]
                    evidence.append({"contributor": left["artist"], "favorite_roles": left["categories"],
                                     "candidate_roles": right["categories"],
                                     "favorite_role_weight": left["weight"], "candidate_role_weight": right["weight"],
                                     "raw_value": left["weight"] * right["weight"],
                                     "favorite_credits": left["credits"], "candidate_credits": right["credits"]})
                raw = sum(e["raw_value"] for e in evidence)
                affinity = raw / (1 + raw)
                value = affinity / count * influence
                group_total += value
                if evidence:
                    contributions.append({"favorite_recording_id": favorite,
                                          "favorite_recording_title": by_id[favorite]["title"],
                                          "favorite_source_url": f"https://musicbrainz.org/recording/{favorite}",
                                          "candidate_recording_id": candidate,
                                          "favorite_artist": artists[aid], "distinct_favorites_in_artist_group": count,
                                          "artist_influence": influence, "raw_shared_credit_value": raw,
                                          "bounded_pair_affinity": affinity, "value": value, "contributors": evidence})
            artist_totals.append({"artist": artists[aid], "distinct_favorites": count,
                                  "influence": influence, "score": group_total})
        record = by_id[candidate]
        rows.append({"recording": {"id": candidate, "title": record["title"],
                                    "disambiguation": record.get("disambiguation", ""),
                                    "length_ms": record.get("length"), "artist_credit": record.get("artist-credit", []),
                                    "source_url": f"https://musicbrainz.org/recording/{candidate}"},
                     "score": sum(c["value"] for c in contributions),
                     "artist_contributions": artist_totals, "contributions": contributions})
    return sorted(rows, key=lambda row: (-row["score"], row["recording"]["title"].casefold(), row["recording"]["id"]))


def contributor_evidence(row: dict) -> list[dict]:
    totals = {}
    for contribution in row["contributions"]:
        raw = contribution["raw_shared_credit_value"]
        for item in contribution["contributors"]:
            aid = item["contributor"]["id"]
            total = totals.setdefault(aid, {"contributor": item["contributor"], "value": 0.0})
            total["value"] += contribution["value"] * item["raw_value"] / raw
    return [totals[aid] for aid in sorted(totals)]


def select_song_list(rows: list[dict], records: list[dict], registry: dict, *, limit: int = 10,
                     diversity: str = "none", availability: dict | None = None, country: str = "DE",
                     contributor_policy: str = "strict") -> dict:
    if type(limit) is not int or limit < 1:
        raise ValueError("Recommendation limit must be positive")
    if diversity not in {"none", "contributors"}:
        raise ValueError("Unknown list diversity method")
    if contributor_policy not in {"strict", "penalized"}:
        raise ValueError("Unknown contributor policy")
    if contributor_policy == "penalized":
        diversity = "contributors"
    validate_registry(registry)
    by_id = {r["id"]: r for r in records}
    available = validate_availability(availability, records, country=country) if availability is not None else None
    pending, skipped, selected = [], [], []
    eligible_count = 0
    for row in rows:
        rid = row["recording"]["id"]
        policy = candidate_eligibility(by_id[rid], registry)
        candidate = row | {"eligibility": policy, "contributor_evidence": contributor_evidence(row)}
        if not policy["eligible"] or row["score"] <= 0:
            skipped.append({"recording_id": rid, "reason": policy["reason"] if not policy["eligible"] else "nonpositive_score",
                            "eligibility": policy})
        else:
            eligible_count += 1
            if available is not None:
                status = available.get(rid)
                if status is None or status["reason"] != "available":
                    skipped.append({"recording_id": rid, "reason": "apple_availability",
                                    "availability_reason": status["reason"] if status else "not_checked"})
                    continue
                candidate = candidate | {"apple_availability": status}
            pending.append(candidate)
    available_count = len(pending)
    used, exposures, collaborations = set(), defaultdict(int), 0
    while pending and len(selected) < limit:
        feasible = []
        for row in pending:
            rid, policy = row["recording"]["id"], row["eligibility"]
            conflicts = used & {m["artist"]["id"] for m in policy["musicians"]}
            contributor_conflicts = {e["contributor"]["id"] for e in row["contributor_evidence"]
                                     if exposures[e["contributor"]["id"]]}
            reason = ("musician_already_selected" if conflicts else
                      "familiar_collaboration_limit" if collaborations and policy["familiar_collaboration"] else
                      "contributor_already_selected" if contributor_conflicts and contributor_policy == "strict" else None)
            if reason:
                skipped.append({"recording_id": rid, "reason": reason, "conflicting_musician_ids": sorted(conflicts),
                                "conflicting_contributor_ids": sorted(contributor_conflicts)})
                continue
            adjustments = []
            for evidence in row["contributor_evidence"]:
                count = exposures[evidence["contributor"]["id"]]
                multiplier = 1 / (1 + count) if diversity == "contributors" else 1.0
                adjustments.append(evidence | {"previous_selected_appearances": count, "multiplier": multiplier,
                                               "selection_value": evidence["value"] * multiplier})
            feasible.append(row | {"selection_score": sum(a["selection_value"] for a in adjustments),
                                   "selection_adjustments": adjustments})
        if not feasible:
            pending = []
            break
        feasible.sort(key=lambda r: (-r["selection_score"], -r["score"], r["recording"]["title"].casefold(), r["recording"]["id"]))
        chosen = feasible[0]
        selected.append(chosen | {"selection_rank": len(selected) + 1})
        used.update(m["artist"]["id"] for m in chosen["eligibility"]["musicians"])
        collaborations += int(chosen["eligibility"]["familiar_collaboration"])
        for evidence in chosen["contributor_evidence"]:
            exposures[evidence["contributor"]["id"]] += 1
        pending = feasible[1:]
    for row in pending:
        policy = row["eligibility"]
        conflicts = used & {m["artist"]["id"] for m in policy["musicians"]}
        contributor_conflicts = {e["contributor"]["id"] for e in row["contributor_evidence"]
                                 if exposures[e["contributor"]["id"]]}
        reason = ("musician_already_selected" if conflicts else
                  "familiar_collaboration_limit" if collaborations and policy["familiar_collaboration"] else
                  "contributor_already_selected" if contributor_conflicts and contributor_policy == "strict" else "requested_limit_reached")
        skipped.append({"recording_id": row["recording"]["id"], "reason": reason,
                        "conflicting_musician_ids": sorted(conflicts), "conflicting_contributor_ids": sorted(contributor_conflicts)})
    evidence_totals = defaultdict(float)
    for row in selected:
        for item in row["contributor_evidence"]:
            evidence_totals[item["contributor"]["id"]] += item["value"]
    total = sum(evidence_totals.values())
    musician_counts = Counter(m["artist"]["id"] for row in selected for m in row["eligibility"]["musicians"])
    repeated = sum(count > 1 for count in musician_counts.values())
    repeated_contributors = sum(count > 1 for count in exposures.values())
    if repeated or collaborations > 1 or (repeated_contributors and contributor_policy == "strict"):
        raise ValueError("Selected list violates musician, contributor, or collaboration constraints")
    return {"recommendations": selected, "skipped_candidates": sorted(skipped, key=lambda r: r["recording_id"]),
            "candidate_count": len(rows), "eligible_positive_candidates": eligible_count,
            "policy": "D-020" if contributor_policy == "strict" else "D-025",
            "policy_sha256": registry_digest(registry), "diversity": diversity,
            "contributor_policy": contributor_policy,
            "availability_summary": {"applied": available is not None,
                                     "country": country_code(country) if available is not None else None,
                                     "eligible_before_filter": eligible_count, "eligible_after_filter": available_count,
                                     "excluded": eligible_count - available_count},
            "selection_summary": {"requested": limit, "returned": len(selected), "shortfall": max(0, limit - len(selected)),
                                  "familiar_collaborations": collaborations, "max_familiar_collaborations": 1,
                                  "distinct_observed_musicians": len(musician_counts), "repeated_observed_musicians": repeated,
                                  "unique_explanatory_contributors": len(evidence_totals),
                                  "max_songs_per_explanatory_contributor": 1 if contributor_policy == "strict" else None,
                                  "repeated_explanatory_contributors": repeated_contributors,
                                  "largest_contributor_evidence_share": max(evidence_totals.values(), default=0) / total if total else None},
            "artist_registry_scope": registry["scope"], "submitted_artist_name_count": len(registry["submitted_names"]),
            "selection_limitations": ["Greedy selection may not maximize list size or total score.",
                                      "Musician uniqueness covers observed credits; primary credits are performance proxies.",
                                      "Soft contributor diversity is redundant under the hard contributor cap." if contributor_policy == "strict"
                                      else "Repeated explanatory contributors receive a diminishing selection contribution.",
                                      "Apple availability, when applied, is an API indication rather than guaranteed playback."]}


def recommendation_report(records: list[dict], favorite_ids: list[str], *, registry: dict | None = None,
                          weights: dict | None = None, saturation_k: float | None = 5.0,
                          excluded_ids: set[str] | None = None, limit: int = 10, diversity: str = "none",
                          availability: dict | None = None, country: str = "DE",
                          contributor_policy: str = "strict") -> dict:
    rows = score_song_candidates(records, favorite_ids, weights=weights, saturation_k=saturation_k, excluded_ids=excluded_ids)
    registry = build_registry(records, favorite_ids) if registry is None else registry
    # A supplied registry cannot accidentally omit the active favorite artists.
    required = {a["id"] for a in build_registry(records, favorite_ids)["submitted_artists"]}
    if required - {a["id"] for a in registry["submitted_artists"]}:
        raise ValueError("Artist registry omits favorite artists")
    return select_song_list(rows, records, registry, limit=limit, diversity=diversity,
                            availability=availability, country=country, contributor_policy=contributor_policy)


def recommend_songs(records: list[dict], favorite_ids: list[str], **kwargs) -> list[dict]:
    """Public song recommendations always apply discovery and complete-list rules."""
    return recommendation_report(records, favorite_ids, **kwargs)["recommendations"]


def write_song_review(path: Path, report: dict) -> None:
    summary = report["selection_summary"]
    lines = ["# Song suggestions under the discovery policy", "",
             f"Selected {summary['returned']} of {summary['requested']} requested songs; shortfall {summary['shortfall']}.",
             f"Familiar collaborations: {summary['familiar_collaborations']}/1; repeated observed musicians: {summary['repeated_observed_musicians']}.",
             f"Shared contributors: {'at most one song each' if report.get('contributor_policy', 'strict') == 'strict' else 'reuse allowed with diminishing contributions'}; repeated connectors: {summary['repeated_explanatory_contributors']}.",
             f"Artist exclusions: {report['artist_registry_scope']}, {report['submitted_artist_name_count']} submitted names.",
             f"List diversity: {report['diversity']}. Policy fingerprint: {report['policy_sha256']}.", "",
             "Favorite matches and listening usefulness remain subject to review. Uniqueness covers observed performance credits.", ""]
    counts = defaultdict(int)
    for skipped in report["skipped_candidates"]:
        counts[skipped["reason"]] += 1
    lines += ["Skipped candidates: " + "; ".join(f"{reason}: {count}" for reason, count in sorted(counts.items())), ""]
    if report["availability_summary"]["applied"]:
        availability = report["availability_summary"]
        lines += [f"Apple {availability['country']} filter: {availability['eligible_after_filter']} of {availability['eligible_before_filter']} eligible candidates have qualifying API-indicated streaming matches.",
                  "Availability and recording matches are automatic metadata checks, not guaranteed playback.", ""]
    for number, row in enumerate(report["recommendations"], 1):
        recording = row["recording"]
        names = ", ".join(c.get("name", c["artist"]["name"]) for c in recording["artist_credit"] if isinstance(c, dict))
        lines += [f"## {number}. {names} — {recording['title']}", "",
                  f"[Recording source]({recording['source_url']}); version: {recording['disambiguation'] or 'unspecified'}.",
                  f"Base affinity: {row['score']:.6f}; selection score: {row['selection_score']:.6f}; eligibility: {row['eligibility']['reason']}.", "",
                  "Observed musicians:", ""]
        if row.get("apple_availability"):
            status = row["apple_availability"]
            track = status["match"]
            lines[-2:-2] = [f"[Listen on Apple Music]({track['trackViewUrl']}); API-indicated streamability: true; checked {status['checked_at']}.",
                            f"Matched release: {track.get('collectionName', 'unspecified')}; studio remaster: {status['checks']['studio_remaster']}; duration difference: {status['checks']['duration_difference_ms']} ms.", ""]
        for musician in row["eligibility"]["musicians"]:
            person = musician["artist"]
            lines.append(f"- [{person['name']}](https://musicbrainz.org/artist/{person['id']}): {', '.join(musician['roles'])}")
        lines += ["", "Strongest favorite connections:", ""]
        for contribution in sorted(row["contributions"], key=lambda c: -c["value"])[:3]:
            credits = "; ".join(f"{c['contributor']['name']} ({'/'.join(c['favorite_roles'])} → {'/'.join(c['candidate_roles'])})"
                                for c in contribution["contributors"])
            lines.append(f"- +{contribution['value']:.6f} via [{contribution['favorite_recording_title']}]({contribution['favorite_source_url']}): {credits}")
        lines += ["", "Listening / identity review: pending.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_playlist_preparation(path: Path, report: dict) -> None:
    if not report["availability_summary"]["applied"]:
        raise ValueError("Playlist preparation requires an Apple availability report")
    tracks = []
    for row in report["recommendations"]:
        status = row["apple_availability"]
        track = status["match"]
        tracks.append({"position": row["selection_rank"], "recording_id": row["recording"]["id"],
                       "itunes_track_id": track["trackId"], "apple_music_catalog_id": None,
                       "title": track["trackName"], "artist": track["artistName"], "url": track["trackViewUrl"],
                       "is_streamable": True, "checked_at": status["checked_at"]})
    with path.open("x", encoding="utf-8") as target:
        json.dump({"format_version": 1, "status": "playlist_preparation_only", "country": report["availability_summary"]["country"],
                   "policy": report["policy"], "tracks": tracks,
                   "limitations": ["iTunes IDs require verification before use as Apple Music catalog IDs.",
                                    "No playlist has been created in an Apple account."]}, target, ensure_ascii=False, indent=2)
        target.write("\n")


def profile_favorites(path: Path, manifest: dict) -> list[str]:
    profile = json.loads(path.read_bytes())
    if profile.get("format_version") != 1:
        raise ValueError("Unsupported recording profile")
    if manifest.get("input_sha256") is not None and profile.get("input_sha256") != manifest["input_sha256"]:
        raise ValueError("Favorite profile belongs to a different input")
    if manifest.get("artist_registry_sha256") is not None:
        if profile.get("artist_registry") is None or registry_digest(profile["artist_registry"]) != manifest["artist_registry_sha256"]:
            raise ValueError("Favorite profile artist registry does not match dataset provenance")
    sources = {s["recording_id"]: s for s in manifest["sources"]}
    ids = []
    for favorite in profile["favorites"]:
        rid = favorite["recording_id"]
        if rid not in sources or sources[rid].get("sha256") != favorite["source_sha256"]:
            raise ValueError("Favorite profile does not match recording snapshots")
        ids.append(rid)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_FIXTURE)
    favorites = parser.add_mutually_exclusive_group()
    favorites.add_argument("--favorite", action="append", help="Recording MBID; repeat for several favorites")
    favorites.add_argument("--profile", type=Path, help="Accepted recording profile from the matcher")
    parser.add_argument("--input", type=Path, help="Full favorites JSON, required for older profiles without an artist registry")
    parser.add_argument("--policy-overrides", type=Path, help="Input-bound aliases, related performers, and collaboration evidence")
    parser.add_argument("--diversity", choices=["none", "contributors"], default="none",
                        help="Compatibility option; redundant under the hard shared-contributor cap")
    parser.add_argument("--availability", type=Path, help="Automatic Apple lookup availability.json")
    parser.add_argument("--country", type=country_code, default="DE")
    parser.add_argument("--playlist-output", type=Path, help="Write a new ordered playlist preparation JSON")
    parser.add_argument("--review-output", type=Path, help="Write a source-linked listening review in Markdown")
    parser.add_argument("--weights", type=Path, default=ROOT / "config/song_weights.json")
    parser.add_argument("--method", choices=["equal", "weighted"], default="weighted")
    parser.add_argument("--no-saturation", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        records, manifest = load_dataset(args.dataset)
        configuration = load_weights(args.weights)
        favorite_ids = (profile_favorites(args.profile, manifest) if args.profile else
                        args.favorite if args.favorite is not None else [DEFAULT_FAVORITE])
        weights = {c: 1.0 for c in CATEGORIES} if args.method == "equal" else configuration["role_weights"]
        k = None if args.no_saturation else configuration["saturation_k"]
        if args.limit < 1:
            raise ValueError("Recommendation limit must be positive")
        profile = json.loads(args.profile.read_bytes()) if args.profile else {"input_sha256": manifest.get("input_sha256")}
        registry = registry_for(records, favorite_ids, profile=profile, input_path=args.input,
                                overrides_path=args.policy_overrides)
        if args.profile and profile.get("input_sha256") and registry["scope"] != "full_input":
            raise ValueError("Older profile lacks full-input artist exclusions; supply --input")
        report = recommendation_report(records, favorite_ids, weights=weights, saturation_k=k,
                                       registry=registry, limit=args.limit, diversity=args.diversity,
                                       availability=json.loads(args.availability.read_bytes()) if args.availability else None,
                                       country=args.country)
        if args.playlist_output:
            write_playlist_preparation(args.playlist_output, report)
        if args.review_output:
            write_song_review(args.review_output, report)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    if args.format == "json":
        print(json.dumps(report | {"method": args.method, "favorite_recording_ids": sorted(set(favorite_ids)),
                          "role_weights": weights, "saturation_k": k,
                          "weight_status": configuration["status"],
                          "credit_coverage": credit_coverage(records),
                          "limitations": ["Scores are bounded credit affinities, not preference probabilities.",
                                          "Cross-ID equivalence, unknown roles, and release-level credits remain unresolved.",
                                          "Multi-primary favorites contribute to each named artist group.",
                                          "The supplied dataset determines candidates; matcher alternatives are not a discovery sample."],
                          }, ensure_ascii=False, indent=2))
        return
    print(f"Song recommendations: {len(set(favorite_ids))} favorites, {report['eligible_positive_candidates']} eligible candidates.")
    summary = report["selection_summary"]
    print(f"Selected {summary['returned']}/{summary['requested']}; familiar collaborations {summary['familiar_collaborations']}/1.")
    print(f"Method: {args.method}; artist saturation k: {k}; weights are provisional.\n")
    for number, row in enumerate(report["recommendations"], 1):
        recording = row["recording"]
        print(f"{number}. {recording['title']} ({recording['disambiguation'] or 'version unspecified'}): {row['score']:.6f}")
        if row.get("apple_availability"):
            print(f"   Apple Music ({args.country}, API-indicated streamability): {row['apple_availability']['match']['trackViewUrl']}")
        for contribution in row["contributions"]:
            names = ", ".join(e["contributor"]["name"] for e in contribution["contributors"])
            print(f"   +{contribution['value']:.6f}: shared credits with {contribution['favorite_recording_title']} via {names}")
            print(f"   {contribution['favorite_source_url']} → {recording['source_url']}")


if __name__ == "__main__":
    main()
