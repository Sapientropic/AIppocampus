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
- [`external-benchmark-map.md`](external-benchmark-map.md) gives external
  benchmark and memory-system comparison paths, with explicit blockers and
  claim boundaries.
- [`atm-bench-hard-protocol-boundary.md`](atm-bench-hard-protocol-boundary.md)
  owns the verified ATM-Bench Hard protocol boundary for the #528 multimodal
  source-backed recall track.
- [`../memory-decision-benchmark-plan.md`](../memory-decision-benchmark-plan.md)
  remains the detailed Track A-D methodology and runner-plan owner.
- [`../hippocampal-recall-plan.md`](../hippocampal-recall-plan.md) owns the
  H-series recall-discrimination design.
- [`../public-longitudinal-users.md`](../public-longitudinal-users.md) owns the
  public longitudinal and VCS hard-event benchmark direction.

Later slices can split stable material from the rationale into dedicated
`track-taxonomy.md` and `scoring-and-claim-boundaries.md` files. Do that only
when the split reduces duplication with the existing runner plans.

## Folder Boundary

This folder owns:

- benchmark philosophy and rationale;
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
