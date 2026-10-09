"""Copy an explicit public inventory to a new directory, preserving local history."""

import argparse
import hashlib
from pathlib import Path
import shutil

from .build_graph import ROOT, load_dataset
from .readme_demo import load_runs


ROOT_FILES = {".gitignore", "README.md", "DECISIONS.md", "ROADMAP.md", "DATA_LICENSE.md",
              "RELEASE_NOTES.md", "PUBLIC_FILES.txt", "pyproject.toml"}


def prepare_release(output):
    output = Path(output).resolve()
    names = (ROOT / "PUBLIC_FILES.txt").read_text(encoding="utf-8").splitlines()
    if not names or len(names) != len(set(names)):
        raise ValueError("Public inventory must be nonempty and unique")
    paths = []
    for name in names:
        relative = Path(name)
        source = (ROOT / relative).resolve()
        allowed = (name in ROOT_FILES or len(relative.parts) > 1 and
                   relative.parts[0] in {"src", "tests", "config", "docs", "reports", ".github"}
                   or len(relative.parts) > 2 and relative.parts[:2] in {("data", "demo"), ("data", "fixture"), ("data", "recommendations")})
        if (not allowed or relative.is_absolute() or ".." in relative.parts or not source.is_relative_to(ROOT)
                or any(p in {"private", "cache", "downloads", ".git", "__pycache__"} for p in relative.parts)
                or not source.is_file()):
            raise ValueError(f"Invalid public inventory entry: {name}")
        paths.append((relative, source))
    load_dataset(ROOT / "data/demo")
    load_dataset(ROOT / "data/fixture")
    load_runs()
    output.mkdir(parents=True, exist_ok=False)
    sums = []
    for relative, source in paths:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        sums.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {relative.as_posix()}")
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return len(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = prepare_release(args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Prepared {count} public files and SHA256SUMS in {args.output}")


if __name__ == "__main__":
    main()
