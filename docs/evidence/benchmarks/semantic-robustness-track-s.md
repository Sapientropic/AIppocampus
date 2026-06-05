# Track S Semantic Robustness Diagnostics

Track S is the semantic-robustness diagnostic lane for AIppocampus. It is a
cross-cutting evidence surface over Track A gate decisions and Track B
source-retrieval behavior, not a replacement for those product-behavior
benchmarks.

## Scope

The first #747 slice is implemented by
`benchmarks/aippocampus/benchmark_semantic_robustness.py`.

Default command:

```sh
python benchmarks/aippocampus/benchmark_semantic_robustness.py --json
```

The default runner is public-safe and dependency-free:

- no live LLM judge;
- no provider keys;
- no model download;
- no raw prompt/query text unless `--include-private-text` is explicit;
- no absolute local paths in sanitized output.

## Slices

| Slice | Default behavior | Metrics |
| --- | --- | --- |
| S1 gate robustness | Reuses the Track A prompt hook fixture and deterministic semantic-gate stubs. | decision stability, false evidence escalation, missed scent/evidence, route-flip taxonomy |
| S2 retrieval invariance | Reuses the runtime hybrid source-retrieval path over public-safe local SQLite fixture rows. | target source rank variance, score variance, Top-K survival, rank drop |
| S3 hard-negative suppression | Reuses Track A gate behavior on explicit negation/currentness hard negatives. | suppression rate, stale-as-current rate, negation violation, source-evidence over-escalation |
| S4 offline proxy alignment | Disabled by default. | only a skipped/proxy boundary until a local model is explicitly configured and reviewed |
| S5 representation-space health | Skipped unless a local embedding index is supplied. | health checks only; not product-quality evidence |

## Initial Diagnostic Reading

The initial deterministic fixture is intentionally allowed to reveal failures.
At the time this slice landed, S2 showed the public-safe equivalent-query
retrieval path surviving Top-K, while S1/S3 exposed negative-constraint risk:
some prompts that explicitly say not to reuse old memory still surface as scent
or evidence.

That is a useful Track S signal, not a reason to make the runner fail. The
runner's `ok` means the diagnostic executed and stayed inside the privacy
contract. The separate `quality_gate_ok` field reports whether the current
fixture clears the narrow robustness thresholds.

## Claim Boundary

Track S can support only this narrow claim:

> AIppocampus has a no-live-judge diagnostic surface for semantic perturbation,
> equivalent-query retrieval invariance, and hard-negative/negation suppression
> over public-safe fixtures.

It cannot claim:

- human-level semantic understanding;
- replacement for Track A/B/C/D quality gates;
- live semantic-model quality;
- proxy-model agreement as source truth;
- broad private real-history semantic robustness;
- embedding topology as proof of understanding.

Optional S4/S5 work should stay explicit and local-first. Missing local models
or embedding indexes should produce skipped diagnostics, not silent fallbacks or
quality failures.
