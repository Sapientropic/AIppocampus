# Repository Instructions

This repository is the canonical public home for AIppocampus.

AIppocampus is a source-backed continuity layer for long-running relationships
with AI agents. It can support project work, but it is not merely a work-task
memory system. Preserve the broader purpose: cross-thread, cross-device,
life-wide continuity without false claims of innate model memory.

## Agent-Facing Posture

Lead with the continuity promise: AIppocampus helps a later agent find the
local source trail and continue with care. It is useful when the user wants
unfinished work, old corrections, preferences, style, themes, or route context
to survive a new thread without claiming the base model innately remembers.

Use source-reachable action guidance:

- `direction_only`: scent, summaries, or semantic sidecars may orient attention
  but do not support factual claims.
- `reopenable_route`: existing route refs, Active Path Packets, or MCP handles
  should be followed before broad manual search.
- `bounded_evidence`: use within declared scope; deepen for exact, sensitive,
  stale, disputed, or high-risk claims.
- `source_open`: exact wording may be used only within scope and redaction
  boundaries.
- `ignore_or_blocked`: stale, private, conflicted, missing-source, or high-risk
  packets should not shape the answer except to defer or explain the boundary.

AIppocampus is usually not the right fit when the user only needs a simple
vector store, hosted team memory, stateless RAG, or a fully managed cloud
profile service. Point to the narrower tool without making source-backed memory
sound suspicious by default.

## Source Of Truth

- `skills/aippocampus/`: installable skill package.
- `skills/aippocampus/SKILL.md`: slim runtime entrypoint.
- `skills/aippocampus/references/`: detailed contracts loaded on demand.
- `skills/aippocampus/scripts/`: runtime helpers that need to ship with the installable skill.
- `tests/aippocampus/`: repository-level unit and integration tests.
- `benchmarks/aippocampus/`: repository-level benchmark runners.
- `tools/aippocampus/`: repository-level smoke, docs-health, and maintenance tools.
- `docs/roadmap.md`: product roadmap and north star.
- `docs/未干的地图.md`: the canonical Chinese origin essay; do not mirror it elsewhere.
- `docs/the-unfinished-map.md`: English transcreation of the origin essay.
- `sources/skill-sources.yaml`: lightweight provenance.

Do not duplicate long rules across multiple docs. Keep one canonical location
and link to it.

## Public Boundary

- Do not commit raw Codex rollouts, `.aippocampus/` generated indexes, registry
  data, vault exports, cold archives, personal conversation bundles, API keys,
  cookies, tokens, or local machine paths.
- Environment variables should use the `AIPPOCAMPUS_*` prefix. Legacy
  `CODEX_MEMORY_*` compatibility may exist only as fallback behavior.
- Keep raw rollout access as an audit path, not the default recall surface.
- External-model features must be optional and clearly documented.

## Editing Rules

- Keep `SKILL.md` concise. Put detailed operation notes in `references/`.
- Keep tests, benchmarks, and repository smoke/readiness tools out of the
  installable skill body unless they are genuinely runtime entrypoints.
- Keep clean source source-backed; summaries and model-organized findings are
  navigation layers, not truth.
- Preserve casual/life-wide memory as first-class. Do not narrow the project
  into repo-task memory only.
- Prefer portable paths and stable ids over machine-specific assumptions.
- Before changing hooks, sync, registry, or search ranking, explain the
  privacy and over-personalization boundary in code or docs.

## Agent Attention And Domain Hazards

Many AIppocampus regressions are not caused by agents lacking general coding
knowledge. They happen because the implementation path lets an agent attend to
the easy local shape while missing the domain hazard that makes that shape
wrong here.

For high-risk surfaces, keep one compact domain-hazard card near the owning
doc, test helper, or verification reference. Do not mirror the card across
many prompts. A card should name the surface, the recurring hazard, forbidden
shortcuts, required checks, one or two examples / anti-examples, and the
focused command or fixture that proves the hazard stayed covered. Starter
cards live in `docs/architecture/ops/agent-domain-hazards.md`; move or split
them closer to owners when a card grows beyond a quick attention aid.

Use domain-hazard cards especially when touching:

- association, concept-graph, cognitive-map, theme, or phrase-mining code where
  language, segmentation, source diversity, or graph expansion can flood recall
  with low-value navigation;
- recall, MCP, APW, source-open, compact foreground, or repo-familiarity code
  where a route can look safe while still making the foreground agent wander;
- sync, registry, lock, JSONL, compatibility, or cleanup code where a green
  happy path can hide data loss, stale state, or platform-specific behavior.

Changed-surface planning should check whether a known hazard card applies
before proposing tests or accepting a closeout. If a failure keeps recurring
and no card exists, create a small card or open an owner issue instead of
adding another fallback, field, or broad warning.

Domain-hazard cards are attention aids, not source evidence and not a full SDD
layer. Stale cards should be updated or deleted when the owning behavior
changes.

## Roadmap, Issue, And Project Intake

Agents should help turn sprawling docs into executable GitHub work, but docs
remain the source of truth for context and evidence. Do not mechanically convert
every paragraph into an issue.

Use this intake flow when the user asks to organize roadmap/docs/issues/projects,
when a doc contains unresolved commitments, or when a change reveals stale
planning material:

- First classify the source document as current contract, readiness evidence,
  next-slice handoff, exploratory research, or historical archive. If a draft
  has been superseded by implementation, mark or route it as archive instead of
  creating fresh work from stale claims.
- Extract only unfinished commitments, blockers, verification gaps, and
  decisions that need implementation. Preserve source links back to the exact
  doc or issue that motivated the work.
- Keep open issues as an execution queue, not an idea vault. If a topic cannot
  plausibly become a fixture, doc, CLI, runtime slice, or verified cleanup
  within 1-2 weeks, route it to Discussion, a roadmap seed, or
  `docs/research/seeds/` instead of opening or keeping a standalone issue.
- Prefer one umbrella issue for a broad track, then create focused child issues
  or checklist items for independently closable slices. Each actionable issue
  should include goal, source, scope, non-goals, acceptance criteria, and
  relevant files. For agent-prone surfaces, also include the applicable
  domain hazards or forbidden shortcuts.
- Use GitHub Projects as the planning view when available, not as another truth
  source. Suggested fields are `Status`, `Track`, `Kind`, `Stage`, `Evidence`,
  `Source`, and `Priority`. Do not claim a Project, fields, or automations exist
  until verified against GitHub.
- New AIppocampus issues should be auto-triaged into Project fields and, when
  confidently inferable, an open Milestone by
  `.github/workflows/project-triage.yml`, which calls
  `tools/aippocampus/github/project_triage.py`. This workflow needs the
  `AIPPOCAMPUS_PROJECTS_TOKEN` repository secret with GitHub Projects and Issues
  write access; if the secret is missing, it should warn rather than pretending
  fields or milestones were filled. The script fills missing fields
  conservatively, only assigns a Milestone when none exists, and avoids
  overwriting human-edited Project metadata.
- Use `docs/architecture/ops/project-planning-automation.md` for the boundary
  between issue-local triage and recurring roadmap drift audits.
- Keep Project views simple: inbox, roadmap by track/stage, current work, and
  evidence gaps. Automation is optional and should follow the existing issue
  labels/filters instead of inventing a parallel workflow.
- After creating or updating issues, add only short pointers from docs when
  needed. Do not mirror the full issue body into docs or duplicate long rules
  across files.
- Before implementing or closing benchmark, recall, architecture, AIppo,
  source-side, or LongMemEval issues, pull an AIppocampus orientation or deepen
  route first. If the work uses benchmark-local scaffolding, label it as such
  and do not close a broader runtime-capability issue from that proxy result.
- During closeout, report which docs became issues, which stayed as background
  context, which were archived or left for review, and what cannot yet be
  claimed.

## Verification

For ordinary repo changes, plan verification from the changed surface first:

```powershell
python tools\aippocampus\changed_surface_preflight.py --json
```

`changed_surface_preflight.py` is the executable fail-fast gate for the current
dirty surface. It runs `git diff --check`, planner-named static/debt/slop gates,
then focused tests, stopping at the first blocker so agents do not bury a cheap
failure behind broad test output. Use `python tools\aippocampus\test_plan.py
--json` when you need the dry-run command plan or detail output without running
it. `--tier pr` is the fast local pre-push gate, not the old broad deterministic
suite; run it when the preflight or changed surface names it. Use
`python tools\aippocampus\run_tests.py --tier broad-pr`, `--tier full`, or the
specific slow / benchmark tier only when the changed surface or release claim
owns that broader coverage.

For public-readiness changes, also scan the repository for local paths and
secret-like strings.
