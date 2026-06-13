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

Adjacent runtime owners keep the product bar from collapsing into "safe but
useless." `aippocampus_runtime.recall.continuity_usefulness` owns the shared
usefulness and attention-cost metric group, while
`aippocampus_runtime.ops.foreground_output_audit` owns the no-write matrix over
hook, active-recall, AIppo, router, bounded-summary, and macro foreground
surfaces. `aippocampus_runtime.recall.candidate_survival` separately reports
over-conservative filtering: a candidate can survive as navigation-only without
becoming evidence or foreground profile truth.

## Budget

Default V0 budget:

```text
max packet bytes: 480
max total foreground bytes: 1800
max hints: 4
```

These are foreground projection limits, not source-reopen limits.
[`source-reopen-budget.md`](../source/source-reopen-budget.md) owns latency/cost budgets
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

## Usefulness And Attention Gate

Red-line safety is necessary but not enough. A packet that leaks nothing can
still fail the product contract if it forces blind deepen, makes similar routes
indistinguishable, invents manual search work, drags the agent toward a wrong
route, or spends more foreground attention than it saves.

The shared usefulness group tracks:

- `manual_query_invention_count`
- `blind_deepen_required_count`
- `packet_triage_distinctiveness`
- `wrong_route_drag_count`
- `useful_packet_rate`
- `route_actionability_rate`
- `action_permission_level`
- `minimum_useful_action_permission_level`
- `usefulness_lost_by_demoting_to_scent_count`
- `main_agent_extra_work_count`
- `fresh_agent_broad_search_before_recall_count`
- `deepen_handle_misuse_count`
- `copy_pasteable_deepen_target_present_count`
- `recall_to_source_reopen_success_rate`
- `foreground_protocol_noise_ratio`
- `attention_saved_vs_spent_proxy`
- `time_to_first_useful_packet_ms_proxy`

`action_permission_level` is a foreground usefulness ladder, not a claim
shortcut:

```text
silent_or_blocked -> scent -> route_hint -> actionable_route ->
bounded_context -> source_open -> claim_ready
```

If safe route evidence exists, demoting the foreground packet back to `scent`
is counted as usefulness loss. Actionable route packets must expose a
copy-pasteable deepen target so a fresh foreground agent does not grab a
display-only route id, fall back to broad search, or spend the user's context
budget learning AIppocampus internals.

Candidate-survival metrics keep false negatives visible without weakening hard
masks. Dropped or parked candidates that later become useful, direction-only
false positives/negatives, silent nudge drift, and suppressed useful candidates
must be visible as agency/usability debt, not hidden behind a green privacy
gate.

## Claim Boundary

Passing this contract supports a narrow claim:

```text
AIppocampus has a measurable foreground UX budget for memory packets.
```

It does not support default hook adoption, private Ficus quality, live user
annoyance rates, broad foreground lift, arbitrary profile-memory safety, or
general continuity usefulness.

## Related Owners

- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns the
  recall/deepen/explain packet shape.
- [`source-reopen-budget.md`](../source/source-reopen-budget.md) owns hot/warm/cold
  reopen policy and timeout fail-open behavior.
- [`source-backed-attention-router.md`](source-backed-attention-router.md) owns
  route-packet authority and hard masks.
- [`schema-field-profiles.md`](../runtime/schema-field-profiles.md) owns broader
  projection discipline across runtime surfaces.
