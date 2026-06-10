# Foreground Memory UX Budget

Role: current contract.
Status: fixture-backed runtime projection for #1125.

AIppocampus can be strict underneath without turning ordinary foreground recall
into a profile dump, proof ledger, or courtroom transcript. This contract owns
the small packet budget for hook, active recall, and AIppo activation surfaces
after route authority has already been computed elsewhere.

The runtime owner is
`aippocampus_runtime.recall.prompt_foreground_budget`. It consumes compact
MemoryPacket-style rows, removes fields that belong behind `deepen` / `explain`
or review surfaces, and reports public-safe aggregate metrics only.

## Budget

Default V0 budget:

```text
max packet bytes: 480
max total foreground bytes: 1800
max hints: 4
```

These are foreground projection limits, not source-reopen limits.
[`source-reopen-budget.md`](source-reopen-budget.md) owns latency/cost budgets
for hot/warm/cold reopen paths. #1129 owns the agent-native recall/deepen/explain
facade shape.

## Packet Families

The fixture covers four ordinary foreground families:

- tiny orientation: a direction-only hint that can shape low-risk planning;
- bounded summary route: a scoped route that can be used as orientation without
  unnecessary immediate reopen;
- reopenable route: a packet whose next safe action remains `reopen_source`;
- review-needed notice: profile-like or sensitive content is replaced with a
  compact review notice.

Recently dismissed routes are suppressed before foreground output. Suppression
is counted as anti-nag behavior, not as a missing memory failure.

## Red Lines

The projection reports these red lines:

```text
foreground_packet_budget_violation_count
unnecessary_reopen_count
false_personalization_count
anti_nag_violation_count
source_backed_claim_without_reopen
debug_or_source_field_leak_count
```

All must be `0` for the fixture report to pass.

`false_personalization_count` is deliberately conservative. Ordinary foreground
packets must not surface profile-like Ficus details such as private
impressions, identity labels, mental-health labels, or inferred dislikes. If a
candidate may be useful but looks profile-like, the foreground packet degrades
to `review_needed` with `next_action="ask_light_question"`.

`unnecessary_reopen_count` protects the product feel: a valid
`bounded_summary_as_route` should not force full reopen merely to guide
low-risk planning. Exact, disputed, public, stale/currentness, sensitive, or
high-risk claims still require source reopen.

`anti_nag_violation_count` protects recency and dismissal boundaries. A route
that was just dismissed must not reappear in ordinary foreground output.

## Claim Boundary

Passing this contract supports a narrow claim:

```text
AIppocampus has a measurable foreground UX budget for memory packets.
```

It does not support default hook adoption, private Ficus quality, live user
annoyance rates, broad foreground lift, or the safety of arbitrary profile
memory.

## Related Owners

- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns the
  recall/deepen/explain packet shape.
- [`source-reopen-budget.md`](source-reopen-budget.md) owns hot/warm/cold
  reopen policy and timeout fail-open behavior.
- [`source-backed-attention-router.md`](source-backed-attention-router.md) owns
  route-packet authority and hard masks.
- [`schema-field-profiles.md`](schema-field-profiles.md) owns broader
  projection discipline across runtime surfaces.
