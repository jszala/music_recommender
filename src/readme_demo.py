"""Render the three saved recommendation lists as ordinary GitHub Markdown."""

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .build_graph import ROOT, load_dataset


DEFAULT_RUNS = ROOT / "data/recommendations"
START = "<!-- recommendations:start -->"
END = "<!-- recommendations:end -->"


def load_runs(directory=DEFAULT_RUNS):
    directory = Path(directory).resolve()
    index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    if index.get("format_version") != 1:
        raise ValueError("Unsupported saved-demo format")
    reports = []
    for entry in index["runs"]:
        dataset = (directory / entry["directory"]).resolve()
        if not dataset.is_relative_to(directory):
            raise ValueError("Saved run path escapes the dataset")
        data = (dataset / "report.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["report_sha256"]:
            raise ValueError("Saved recommendation report checksum mismatch")
        report = json.loads(data)
        load_dataset(dataset)
        rows = report["recommendations"]
        if (report.get("format_version") != 1 or report["run_number"] != entry["number"]
                or len(rows) != report["selection_summary"]["returned"]
                or [r["selection_rank"] for r in rows] != list(range(1, len(rows) + 1))):
            raise ValueError("Saved recommendation membership/ranks disagree with the report")
        reports.append(report)
    return reports


def md(value):
    text = escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    for symbol in ("\\", "[", "]", "*", "_", "`", "|"):
        text = text.replace(symbol, "\\" + symbol)
    return text


def link(label, url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "musicbrainz.org" or parsed.username or parsed.password:
        return md(label)
    return f"[{md(label)}]({url.replace(')', '%29').replace('(', '%28')})"


def artists(recording):
    credits = [c for c in recording["artist_credit"] if isinstance(c, dict)]
    return "".join((c.get("name") or c["artist"]["name"]) + c.get("joinphrase", ", ") for c in credits).rstrip(", ")


def main_connection(row):
    favorites = row["primary_seed_song"]["favorite_recording_ids"]
    paths = [c for c in row["contributions"] if c["favorite_recording_id"] in favorites]
    connection = max(paths or row["contributions"], key=lambda c: c["value"])
    return connection, max(connection["contributors"], key=lambda c: c["raw_value"])


def role_labels(categories):
    return "/".join("engineering" if category == "staff" else category for category in categories)


def render_list(reports):
    lines = []
    for report in reports:
        summary = report["selection_summary"]
        lines += [f"### Run {report['run_number']} · {summary['returned']}/{summary['requested']} recordings", ""]
        for row in report["recommendations"]:
            recording = row["recording"]
            connection, contributor = main_connection(row)
            query = urlencode({"term": artists(recording) + " " + recording["title"]})
            apple = f"https://music.apple.com/de/search?{query}"
            lines += [f"{row['selection_rank']}. {link(recording['title'], recording['source_url'])} — {md(artists(recording))} · [Apple search]({apple})<br>",
                      f"   {md(contributor['contributor']['name'])}: {md(role_labels(contributor['favorite_roles']))} on "
                      f"{link(connection['favorite_recording_title'], connection['favorite_source_url'])} → "
                      f"{md(role_labels(contributor['candidate_roles']))} here.", ""]
    return "\n".join(lines).rstrip()


def render_details(reports):
    lines = ["# Recommendation evidence", "", "All paths and scores from the three saved runs. Membership and order are unchanged; the lists are not merged or reranked.", ""]
    for report in reports:
        lines += [f"## Run {report['run_number']}", ""]
        for row in report["recommendations"]:
            recording = row["recording"]
            length = recording.get("length_ms")
            duration = f"{length / 60000:.2f} minutes" if length else "duration not observed"
            lines += [f"### {row['selection_rank']}. {link(recording['title'], recording['source_url'])} — {md(artists(recording))}", "",
                      f"{duration}; version: {md(recording.get('disambiguation') or 'not specified')}. "
                      f"Base score **{row['score']:.6f}**; selection score **{row['selection_score']:.6f}**.", ""]
            for connection in row["contributions"]:
                lines += [f"From {link(connection['favorite_recording_title'], connection['favorite_source_url'])} "
                          f"({md(connection['favorite_artist']['name'])}):", ""]
                for credit in connection["contributors"]:
                    favorite = ", ".join(link(c["role"] + (" (performance proxy)" if c.get("primary_artist") else ""), c["source_url"]) for c in credit["favorite_credits"])
                    candidate = ", ".join(link(c["role"] + (" (performance proxy)" if c.get("primary_artist") else ""), c["source_url"]) for c in credit["candidate_credits"])
                    lines.append(f"- {md(credit['contributor']['name'])}: {credit['favorite_role_weight']:g} × {credit['candidate_role_weight']:g} = {credit['raw_value']:g}. Favorite: {favorite}. Candidate: {candidate}.")
                lines += ["", f"x = {connection['raw_shared_credit_value']:g}; x/(1+x) = {connection['bounded_pair_affinity']:.6f}; "
                          f"divide by {connection['distinct_favorites_in_artist_group']} favorite(s) in this artist group, "
                          f"then multiply by {connection['artist_influence']:.6f}: +{connection['value']:.6f}.", ""]
            lines += ["Connector reuse adjustments:", ""]
            for adjustment in row["selection_adjustments"]:
                lines.append(f"- {md(adjustment['contributor']['name'])}: {adjustment['value']:.6f} × "
                             f"1/(1+{adjustment['previous_selected_appearances']}) = {adjustment['selection_value']:.6f}.")
            lines += [""]
    lines += ["See [the method](method.md) for role weights, source assignment, exclusions, and score limitations."]
    return "\n".join(lines).rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json", "details"), default="markdown")
    parser.add_argument("--check-readme", action="store_true")
    args = parser.parse_args()
    try:
        reports = load_runs()
        if args.check_readme:
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            if readme.split(START, 1)[1].split(END, 1)[0].strip() != render_list(reports):
                raise ValueError("README list differs from the saved recommendations")
            return
        print(json.dumps(reports, ensure_ascii=False, indent=2) if args.format == "json" else
              render_details(reports) if args.format == "details" else render_list(reports))
    except (OSError, ValueError, KeyError, IndexError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
