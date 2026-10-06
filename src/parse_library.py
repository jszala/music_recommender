"""Convert copied favorites text locally; this does not match recordings."""

import argparse
import json
from pathlib import Path
import re


def parse_favorites(text: str) -> dict:
    tracks, review = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        row = {"line_number": number, "original_line": line}
        if "\t" in line:
            columns = line.split("\t")
            if (len(columns) != 8 or not columns[0].strip() or not columns[3].strip()
                    or not re.fullmatch(r"\d+:[0-5]\d", columns[2])):
                review.append({**row, "source_columns": columns,
                               "reason": "Expected eight tab-separated columns with title, duration, and artist"})
                continue
            tracks.append({**row, "artist_text": columns[3].strip(),
                           "song_text": columns[0].strip(), "album_text": columns[4].strip(),
                           "duration_text": columns[2], "genre_text": columns[5].strip(),
                           "source_columns": columns})
            continue
        parts = line.split(" — ")
        if len(parts) != 2 or not all(p.strip() for p in parts):
            review.append({**row, "reason": "Expected exactly one Artist — Song separator and two nonempty fields"})
            continue
        tracks.append({**row, "artist_text": parts[0].strip(), "song_text": parts[1].strip()})
    return {"format_version": 1, "source": "copied favorites", "tracks": tracks, "needs_review": review}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/private/favorites.json"))
    args = parser.parse_args()
    try:
        result = parse_favorites(args.input.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Avoid overwriting a reviewed or previously converted list silently.
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (OSError, UnicodeError) as error:
        parser.error(str(error))
    print(f"Converted {len(result['tracks'])} rows; {len(result['needs_review'])} rows need review. "
          f"Saved locally to {args.output}.")


if __name__ == "__main__":
    main()
