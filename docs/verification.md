# Verification

## Documentation revision, 2026-10-09

The README now explains the problem, pipeline, one worked example, and experiment
findings. The case study and architecture document provide the longer technical
account. The runnable public demo is `src.demo`; all eleven saved historical
results appear in `data/recommendations/README.md`, with complete credit evidence
in `docs/recommendations.md`.

The local offline suite passed **229 tests in 19.147 seconds**. The saved-report
checks cover membership and rank preservation, base-score and credit-path
recomputation, escaping, checksum tampering, and offline CLI output. The document
check also rejects missing, reordered, or duplicated markers and changed list or
evidence content.

Repeated weighted-demo JSON and saved-run JSON were byte-identical to their
respective outputs captured before the documentation edits. The equal-weight demo
ran successfully. Scoring, selection policies, source snapshots, and saved reports
were preserved.

The supporting documentation is checked with:

```bash
python3 -B -m src.readme_demo --check-docs
```

CI runs that check alongside the offline suite and deterministic JSON checks.
Local verification does not establish a remote CI result or listener usefulness.

## Public package

[PUBLIC_FILES.txt](../PUBLIC_FILES.txt) declares the public package, including the
case study and architecture document. The packaging command validates the public
fixtures and saved reports, copies only the declared inventory, adds `SHA256SUMS`,
and refuses an existing output directory:

```bash
python3 -B -m src.prepare_release --output dist/public-package
```

The constructed fixture reproduces full scoring and selection. Public historical
context reproduces base scores and credit paths; the complete historical selection
requires private candidate pools and familiar-act exclusions.

## Earlier checkpoint, 2026-10-08

Before this revision, the root README displayed the eleven saved results. That
checkpoint passed 228 tests locally and in a clean copy of 143 inventory files
without private data. Fixture/report checksums, deterministic output, and document
consistency were verified. Those results describe the earlier package; historical
experiment protocols and observations remain in the reports and
[results](results.md).
