# AIppocampus Benchmarks

This directory keeps the public benchmark runners visible while moving helper,
adapter, fixture-builder, and family-specific implementation code into smaller
layers.

## What To Run

Start with the claim you need to support, then choose the smallest profile that
can actually answer it.

- Ordinary PR confidence:
  `python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast`
- Fresh-clone public suite:
  `python benchmarks/aippocampus/benchmark_suite.py --profile public-fast --cite-summary`
- Public release evidence update:
  `python benchmarks/aippocampus/benchmark_suite.py --profile release-evidence --output reports/benchmark-suite-release.json --cite-summary`
- Live/provider calibration:
  use `--profile live-semantic` only when the provider/key budget is explicit.
- Private or sanitized replay:
  use the owning protocol/runner; do not cite private-history output as public
  release evidence without a sanitized rerun.

`--json` keeps the Unix contract and prints the full report to stdout. When a
foreground agent needs the full report on disk but only a readable claimability
answer in chat, use `--output <report.json> --cite-summary`.

The compact map of benchmark tracks, maturity, and escalation order lives in
`docs/evidence/benchmarks/design/benchmark-priority-map.md`.

## Layout

- `benchmark_*.py`: stable benchmark runners. These paths are cited by docs,
  manifests, and tests; keep new runner entrypoints here unless a benchmark
  family becomes large enough to justify a dedicated package.
- `benchmark_suite.py`: aggregate runner used by local and CI tiers.
- `source_evidence/`: package-style source-evidence benchmark families.
- `shared/`: reusable helpers for statistics, claim-boundary references,
  sampling, budget checks, and benchmark metadata.
- `adapters/`: dataset and provider adapters that translate external benchmark
  surfaces into AIppocampus-safe public state.
- `builders/`: fixture-generation commands.
- `families/`: benchmark-family helpers that are too specific for `shared/`
  but too large to keep inside a single runner.

New non-runner code should usually go under `shared/`, `adapters/`,
`builders/`, or `families/` instead of adding more flat files here.

## Migration Rule

If a helper, adapter, or builder path is moved, update the evidence-map,
manifest, and test references in the same change. Avoid compatibility shims in
this directory; they keep the root visually noisy and make later agents inspect
dead entrypoints.
