# AAR v2 Action-Time Nudges

Status: first deterministic slice for #484 and #332 strategy-reader
hardening.

This note defines the narrow AAR v2 runtime surface. It turns source-backed
corrections or postmortems into action-time advisory nudges for one high-risk
class first: making a specific memory/source claim from weak context.

The runtime owner is
`skills/aippocampus/scripts/aippocampus_runtime/reflection/aar_v2.py`.

## Objects

| Object | Meaning |
| --- | --- |
| Failure pattern | A source-backed correction or postmortem summary that describes a repeated failure shape. It must carry source refs before it can become a candidate AAR record. |
| Action class | The current implemented class is `specific_memory_source_claim`: the agent is about to make a concrete memory/source claim. |
| Trigger scope | Weak support levels are `scent`, `candidate`, and `dream`. A trigger is suppressed when clean source is already visible or the action is not a specific memory claim. |
| Nudge | An action-time advisory record recommending source reopen before the claim. It routes attention; it is not evidence and cannot support a factual claim. |
| Counterfactual hypothesis | A bounded hypothesis that the nudge would have prevented a failure. It stays `provisional` unless backed by replay, sandbox ablation, source reopen, explicit user correction, or retrospective outcome evidence with source refs. Even then it is support for the nudge policy, not causal truth. |
| Outcome feedback | Rows such as `useful`, `ignored`, `false_positive`, `prevented_failure`, and `stale`, plus nudge cost. These feed later pruning/demotion decisions; they do not rewrite history. |

## Runtime Boundary

`aar_v2.py` provides:

- `build_aar_v2_report(...)`: no-write report mode over public-safe correction
  or postmortem rows.
- `match_action_time_nudges(...)`: deterministic match for the first
  source-claim action class.
- `summarize_feedback_metrics(...)`: feedback counters for later lifecycle
  pruning, including false-positive rate, ignored/useful counts, prevented
  failures, and nudge cost.

The report must not serialize raw prompts, raw source snippets, secrets, local
paths, or unreviewed model text as evidence. It preserves only compact source
refs and sanitized summaries.

Rows explicitly reviewed as `stale`, `unsupported`, or `rejected` are blocked
before they can become AAR v2 candidate records. This protects the AAR reader
from treating old topology/postmortem material as current strategy guidance.

This slice does not install live prompt hooks, does not mutate clean source,
does not promote formal memory, and does not replace answer-time source gates.
AAR v2 affects attention and routing only.

The #332 scripted review closeout is recorded in
[`reflection-aar-v2-hardening-2026-06-05.md`](../evidence/reflection-aar-v2-hardening-2026-06-05.md).

## Relation To Neighboring Surfaces

- Ambient recall scent, dream hypotheses, active recall locks, route handles,
  and cards can trigger the weak-context side of the match, but none of those
  become evidence through AAR v2.
- #483 activation lifecycle pruning may later consume AAR v2 feedback metrics,
  such as false-positive nudges or useful prevented failures.
- Correction reconsolidation can provide source-backed activation/outcome rows,
  but AAR v2 is the action-time policy surface, not the postmortem store.
