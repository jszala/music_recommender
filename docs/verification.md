# Verification, 2026-10-08

The public demo is the recommendation list in the repository README. It contains
all 11 results from saved runs 6/9/10, with original ranks and no filtering,
reranking, screenshots, cover-art placeholders, or separate website.

The six saved-demo checks passed: exact membership/order, README consistency,
report mutation/escaping, report checksum/rank tampering, complete credit evidence,
offline JSON output, and recomputation of every base score/path from the existing
scorer. Nineteen unmodified source snapshots reproduce those base contributions
exactly. The original exported rows were compared before publication preparation;
all 11 rows, including selection scores and adjustments, are unchanged.

The full offline suite passed **228 tests in 19.196 seconds**. A clean copy of the
143 public inventory files, with `data/private/` absent, passed **228 tests in
19.265 seconds**. README generation matched the saved reports; repeated saved-run
JSON was byte-identical. The older weighted fixture JSON was byte-identical to the
pre-change output, and the equal method ran successfully. All fixture/report and
package checksums passed, all local Markdown links resolved, and public scans found
no private contact contents, credential patterns, machine paths, or employment
framing. `git diff --check` passed.

The new Markdown list uses GitHub's native formatting. No custom visual design or
browser/screenshot work was performed for this revision. `--check-readme` is also
included in CI. Full historical selection uses private pools/profile exclusions;
the public saved-context reproduction covers base scores and all credit paths.

[PUBLIC_FILES.txt](../PUBLIC_FILES.txt) declares the public package. The packaging
command validates all fixtures/reports, copies only that inventory, adds
`SHA256SUMS`, and refuses an existing output directory:

```bash
python3 -B -m src.prepare_release --output dist/first-public-release
```

Existing local history and the prior draft are preserved privately. The revised
package uses a separate initial commit. Source-checkout edits remain uncommitted.

The earlier visual draft and its validation evidence remain private. The previous
222-test baseline and historical experiment results are preserved. Remote CI has
not been reported as run; no remote push or release has been made.
