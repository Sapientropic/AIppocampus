# AIppocampus Benchmarks

This directory keeps the public benchmark runners visible while moving helper,
adapter, fixture-builder, and family-specific implementation code into smaller
layers.

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
