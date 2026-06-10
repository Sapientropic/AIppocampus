# Source Reopen Budget

Role: current contract.
Status: fixture-backed hot/warm/cold policy for #1124.

Source is still ground, but source-backed recall should not become "reopen
everything before answering." This contract separates low-risk orientation,
cheap source-span verification, and full source-court reopen/audit work.

The runtime owner is
`aippocampus_runtime.recall.source_reopen_budget`.

## Tiers

| Tier | Use | Proxy budget |
| --- | --- | --- |
| `hot` | Tiny hint, `bounded_summary_as_route`, or verified cached route. | 25 ms / 120 tokens |
| `warm` | Cheap verifier plus selected source span. | 180 ms / 700 tokens |
| `cold` | Full source reopen, audit, public claim, high-risk, stale/currentness, or conflict lane. | 1200 ms / 3200 tokens |

The proxy numbers are deterministic fixture budgets. They are not measured live
latency claims and do not say source reopen is free.

## Mandatory Reopen

Cold/source-court reopen is mandatory before:

- exact quotes or exact wording;
- public issue, PR, report, or benchmark claims;
- high-risk legal, medical, financial, security, or user-impactful claims;
- stale/currentness disputes;
- conflict sets;
- sensitive/private Ficus impressions;
- code changes that depend on old source facts.

`bounded_summary_as_route` may guide low-risk planning on the hot path, but it
remains navigation. It cannot support exact, disputed, public, stale,
sensitive, or high-risk claims.

## Timeout And Fail-Open

Foreground hook paths are fail-open surfaces. If a source reopen or verifier
would exceed the foreground budget, the correct behavior is:

```text
next_action = fail_open_no_claim
```

That protects responsiveness without silently converting stale or unreopened
material into evidence. Background/operator work may use longer budgets, but it
must make timeout/degradation visible instead of aborting as if nothing
happened.

## Metrics

The fixture reports:

```text
latency_ms_proxy_by_path
token_proxy_by_path
source_reopen_required_count
bounded_summary_allowed_count
timeout_fail_open_count
unnecessary_reopen_count
source_backed_claim_without_reopen
```

The red lines are:

```text
unnecessary_reopen_count = 0
source_backed_claim_without_reopen = 0
```

Unit tests also construct a violating public-claim case to prove an attempted
claim without mandatory reopen increments
`source_backed_claim_without_reopen`.

## Claim Boundary

Passing this contract supports:

```text
AIppocampus has a measured policy for when to reopen source versus when to emit
a bounded route or summary.
```

It does not support source reopen being free, summaries as evidence, default
hook adoption, live latency/quality, or private-history reopen quality.

## Related Owners

- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns the
  recall/deepen/explain packet shape.
- [`foreground-memory-ux-budget.md`](foreground-memory-ux-budget.md) owns
  foreground packet size, review-needed, and anti-nag behavior.
- [`source-backed-attention-router.md`](source-backed-attention-router.md) owns
  route-packet authority and hard masks.
