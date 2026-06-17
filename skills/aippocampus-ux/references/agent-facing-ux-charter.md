# AIppocampus Agent-Facing UX Charter

Use this reference when reviewing broad AIppocampus foreground UX, writing an
issue/PR plan, or deciding whether a surface belongs in foreground action,
operator/debug, public demo, source-court, benchmark/report, or setup flows.

Origin: GitHub issue #2022, "Create an agent-facing UX charter for foreground
surfaces and issue triage", plus its 2026-06-16 and 2026-06-17 follow-up
comments. Treat the issue as current planning context; reopen it before making
exact claims about its latest comments or status.

## Product Standard

AIppocampus should feel:

- Linear-clear: a named state, a visible owner, and one obvious next move.
- Raycast-fast: the first useful action is close at hand; command/handle use
  does not require reading the whole system.
- Stripe-integrable: tools explain what they do, when to call them, and what to
  do after the result.
- Stripe-recoverable: failures return executable recovery paths, not mystery
  errors or prose-only apologies.

The user value is usable continuity. Source-backed machinery is the substrate,
not the foreground experience.

## Surface Taxonomy

Classify the output before applying a field budget.

| Surface | Purpose | Foreground shape |
| --- | --- | --- |
| `foreground_agent_action` | Active agent decides what to do now. | Decision, short why, next action, claim boundary, optional callable handle. |
| `operator_debug` | Maintainer inspects internals. | Metrics, red lines, policy ledgers, local/private detail if allowed. |
| `public_demo` | New user sees a safe first recall moment. | Stable commands, public-safe example, plain limitation, no private artifacts. |
| `source_court` | Source has been reopened for claims. | Exact scoped evidence, line/window boundary, redaction/currentness limits. |
| `benchmark_report` | Evidence and readiness accounting. | Method, cohort, result, cannot-claim local to the run, owner action. |
| `setup_onboarding` | Install/update/hooks/provider/sync readiness. | Current status, one recommended next command, rollback or chooser path. |

Do not force a foreground profile onto an operator surface. Do not leak an
operator profile into a foreground surface.

## Checklist

Use these checks for agent-facing surfaces unless the surface is explicitly
operator-only.

1. One primary next action.
   Avoid competing `next_action`, `next_safe_action`, `primary_action`, and
   prose instructions unless precedence is machine-readable.

2. Action card before audit payload.
   First answer: should I use this, why, what do I do next, and what can I not
   claim yet? Put metrics, red lines, raw packets, and debug detail behind
   `--detail`, `explain`, or operator views.

3. Route usefulness is not a claim shortcut.
   A route can be useful before it is claim-ready. If a safe source-backed
   route exists, demoting it to vague scent should be counted as usefulness
   loss.

4. Hook is ignition, not context transport.
   Hook output should say whether a continuity lead exists and which pull to
   try first. It should not dump source, local paths, private handles, or
   audit-scale JSON.

5. Visible handles must be obviously usable or diagnostic.
   Display ids, route ids, callable handles, copy-paste commands, and MCP
   selectors should not look interchangeable.

6. Recovery must be executable.
   Bare commands, missing args, stale handles, no active contract, no source,
   and missing setup should return one safe next command or chooser card.

7. Field width is attention cost.
   Rich provenance can exist, but ordinary foreground agents should not carry
   it in working memory.

8. Privacy and source boundaries remain intact.
   No raw prompt/source leaks, local paths, secrets, or source-backed factual
   claims without reopen/deepen when required.

9. Test behavior, not just JSON validity.
   Ask whether a fresh foreground agent chooses the intended action, avoids
   broad manual search, avoids blind deepen, and avoids false claims.

10. Agent feedback closes the loop.
    When an agent uses or rejects a route, the feedback path should be obvious
    and durable enough to improve future routing.

## AX Map

Borrow the external AX shape only after translating it into AIppocampus'
source-backed domain:

- Access: installed, current, callable, and host-compatible status is legible.
- Context: result includes a small useful lead, not a diagnostic dump.
- Tools: recall, deepen, explain, feedback, setup, and recovery paths have
  clear scopes.
- Orchestration: a fresh agent can complete recall -> deepen/source -> act ->
  feedback without inventing broad search first.

Every tool/card should answer:

- What does this surface do?
- When should the agent use it, and when should it stay silent or read current
  source first?
- After receiving this result, what is the next safe step?

## Recovery Contract

When a recoverable problem occurs, expose structured recovery where practical:

- `error_class`
- `cause`
- `next_command` or chooser options
- `retry_or_escalate`
- `mutation_risk`
- `claim_boundary`

Recovery copy should distinguish "run this now" from "template requiring a real
path, route id, handle, or consent". Rollback should be visible for mutating
setup flows.

## Behavioral Evaluation

Do not accept "JSON validates" as agent-facing polish. A useful eval asks
whether a fresh agent:

- chooses the intended tool;
- avoids broad grep/manual search when a route exists;
- avoids blind deepen when refine/recover is better;
- does not copy display ids as callable handles;
- does not treat scent as fact;
- does not treat useful source-backed route guidance as unusable merely because
  it is not claim-ready.

## Issue Triage Pattern

For new AIppocampus UX issues, keep the issue executable:

- Goal: the user/agent behavior that should improve.
- Source: issue, doc, code, report, or current output that motivated the work.
- Scope: one closable slice, normally 1-2 weeks.
- Non-goals: what this does not claim or refactor.
- Acceptance: behavior checks, source/privacy boundary, and relevant tests.
- Files/tests: likely owners to inspect first.

Link related issues as examples; do not copy their full bodies. If a report
lists recommended issues, either map each recommendation to current issue refs
or mark it archived/no-action so prose does not keep resurfacing as phantom
work.

## Non-Goals

- Do not invent another broad schema every payload must carry.
- Do not weaken source reopen, privacy, or high-risk boundaries.
- Do not make ordinary foreground agents read the benchmark/provenance system
  before taking the next safe action.
- Do not close broad product-readiness claims from a tiny fixture or one
  isolated card repair.
