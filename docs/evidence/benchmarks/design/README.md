# Benchmark Design Hub

This folder explains the design logic behind AIppocampus benchmarks. It exists
so readers and future agents can understand the evaluation philosophy without
reverse-engineering it from runner code, dated evidence ledgers, and issue
history.

It does not own current claim status. Current can-claim / cannot-claim status
belongs in [`../../readiness/stage-0-5-readiness.md`](../../readiness/stage-0-5-readiness.md).
Dated command evidence belongs in
[`../../readiness/public-readiness-verification.md`](../../readiness/public-readiness-verification.md).

## Start Here

- [`benchmark-design-rationale.md`](benchmark-design-rationale.md) explains why
  AIppocampus evaluates memory as source-backed continuity, not generic
  retrieval QA.
- [`benchmark-priority-map.md`](benchmark-priority-map.md) explains which
  benchmark and smoke surfaces are P0/P1/P2/P3, what to run when, and which
  claim boundaries each surface must not cross.
- [`benchmark-maturity-gates.md`](benchmark-maturity-gates.md) owns the
  maturity ladder, sample-size fields, and promotion gates that keep small
  deterministic fixtures useful without reading them as public-quality cohorts.
- [`external-benchmark-map.md`](external-benchmark-map.md) gives external
  benchmark and memory-system comparison paths, with explicit blockers and
  claim boundaries.
- [`multimodal-memory-benchmark-map.md`](multimodal-memory-benchmark-map.md)
  maps multimodal memory benchmark families to #528 source shapes and claim
  boundaries.
- [`atm-bench-hard-protocol-boundary.md`](atm-bench-hard-protocol-boundary.md)
  owns the verified ATM-Bench Hard protocol boundary for the #528 multimodal
  source-backed recall track.
- [`memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md)
  remains the detailed Track A-D methodology and runner-plan owner.
- [`../reports/hippocampal/hippocampal-recall-plan.md`](../reports/hippocampal/hippocampal-recall-plan.md) owns the
  H-series recall-discrimination design.
- [`../public-longitudinal-users.md`](../public-longitudinal-users.md) owns the
  public longitudinal and VCS hard-event benchmark direction.

Later slices can split stable material from the rationale into dedicated
`track-taxonomy.md` and `scoring-and-claim-boundaries.md` files. Do that only
when the split reduces duplication with the existing runner plans.

## Folder Boundary

This folder owns:

- benchmark philosophy and rationale;
- benchmark priority, maturity, and run-profile guidance;
- track-family design summaries;
- scoring and claim-boundary explanations;
- external benchmark analysis maps;
- links to issue families that implement or harden each benchmark surface.

It does not own:

- raw benchmark outputs;
- dated measurement ledgers;
- private real-history artifacts;
- copied runner documentation;
- marketing comparisons or public superiority claims.
