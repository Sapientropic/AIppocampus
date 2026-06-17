---
name: aippocampus-ux
description: Review, shape, or implement AIppocampus agent-facing UX for foreground recall, hooks, MCP/CLI tools, action cards, recovery cards, onboarding, public demos, and issue triage. Use when work mentions AIppocampus UX, foreground surfaces, source-backed continuity usability, Linear/Raycast/Stripe-style clarity/speed/integration/recoverability, or when generic visual critique is too broad for AIppocampus product surfaces.
---

# AIppocampus UX

## Overview

Use this skill to make AIppocampus usable by a foreground agent on behalf of a
human. The bar is not generic visual polish: AIppocampus UX should be clear
like Linear, fast like Raycast, and integrable/recoverable like Stripe while
preserving source-backed boundaries.

This is a product/agent-use skill, not a design-director critique. Optimize for
the next agent being able to decide, pull the right source route, act, recover,
and leave feedback without reading audit-scale internals.

For broad reviews, issue triage, or new foreground contracts, read
`references/agent-facing-ux-charter.md`. For a tiny copy, CLI, or card fix, use
the workflow below directly.

## Workflow

1. Reopen the task source.

   Use the current issue, PR, comments, docs, code, or CLI output before
   judging the surface. If older AIppocampus context may affect the work, use
   the normal AIppocampus orientation/recall route first. Treat route packets as
   navigation until source is opened.

2. Classify the surface.

   Pick one primary class before recommending fields or tests:

   - `foreground_agent_action`: compact route, action card, hook hint, MCP/CLI
     result, or recovery card used by an active agent.
   - `operator_debug`: diagnostics, red lines, policy ledgers, run metadata, or
     private local detail for maintainers.
   - `public_demo`: public-safe docs, examples, screenshots, or first-run proof.
   - `source_court`: deepen/source-open output used for exact, public, stale,
     sensitive, disputed, or high-risk claims.
   - `benchmark_report`: evaluation, readiness, or evidence reports.
   - `setup_onboarding`: install, update, hook, provider, sync, or readiness
     flows.

3. Map the agent journey.

   Use the Access / Context / Tools / Orchestration map:

   - Access: can the agent tell whether AIppocampus is installed, current, and
     callable in this host?
   - Context: does the agent receive a small useful continuity lead, not
     audit-scale JSON?
   - Tools: are recall, deepen, explain, feedback, setup, and recovery paths
     discoverable with clear scopes?
   - Orchestration: can a fresh agent complete recall -> deepen/source -> act
     -> feedback without inventing broad manual search first?

4. Review against the four product standards.

   - Clear: one primary next action, one handle vocabulary, action card before
     audit payload, no visually interchangeable display ids and callable
     handles.
   - Fast: first useful packet appears early, foreground fields stay small,
     copy-paste commands exist where useful, no broad search when a route
     already exists.
   - Integrable: each tool/card answers What / When / After, schemas are
     task-first, host boundaries are explicit, public demos use stable commands.
   - Recoverable: missing args, stale handles, blocked source, missing setup,
     no active contract, or permission/config problems return one executable
     recovery action or chooser card.

5. Preserve source-backed usefulness.

   Route usefulness is not a claim shortcut. A route can be actionable before
   it is claim-ready; exact/public/stale/sensitive/high-risk claims still need
   deepen/source reopen. If a safe useful route exists but the surface demotes
   it to vague scent or silence, count that as UX debt rather than safety
   success.

6. Recommend the smallest durable slice.

   Prefer one repair that improves the agent journey across sibling surfaces.
   If the smell is recurring across CLI/MCP/cards, point to a shared contract or
   helper. If it is isolated, keep the patch local. Do not introduce a broad
   schema, scoring layer, or governance abstraction unless it removes repeated
   product debt.

## Output Shape

Start with a direct verdict, then the smallest useful next action.

Use this structure for reviews or plans:

- Verdict: `ship`, `fix_one_slice`, `needs_contract`, or `blocked`.
- Surface class: one of the classes above.
- Primary next action: one command, patch target, issue update, or source route.
- Findings: 3-5 items max, ordered by user impact, with file/line/issue refs
  when available.
- Fix slice: exact files/docs/tests to change; name non-goals.
- Verification: behavior checks first, then JSON/schema/docs checks.
- Unknowns: mark with `[⚠️]` and say how to confirm.

For implementation, use normal codebase patterns. Add comments only where a
fallback, gate, threshold, field projection, or recovery boundary prevents a
future agent from making an attractive but unsafe simplification.

## Do Not

- Do not run a generic visual critique unless there is an actual UI visual.
- Do not use Nielsen-style scoring as the main answer for CLI/MCP/agent cards.
- Do not turn AIppocampus UX into marketing copy.
- Do not require foreground agents to understand full provenance, benchmark
  ledgers, or internal policy machinery before acting.
- Do not weaken source reopen, privacy, high-risk, or local-path boundaries to
  make the foreground feel simpler.
