# Repository Instructions

This repository is the canonical public home for AIppocampus.

AIppocampus is a source-backed continuity layer for long-running relationships
with AI agents. It can support project work, but it is not merely a work-task
memory system. Preserve the broader purpose: cross-thread, cross-device,
life-wide continuity without false claims of innate model memory.

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
- Prefer one umbrella issue for a broad track, then create focused child issues
  or checklist items for independently closable slices. Each actionable issue
  should include goal, source, scope, non-goals, acceptance criteria, and
  relevant files.
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
- Use `docs/architecture/project-planning-automation.md` for the boundary
  between issue-local triage and recurring roadmap drift audits.
- Keep Project views simple: inbox, roadmap by track/stage, current work, and
  evidence gaps. Automation is optional and should follow the existing issue
  labels/filters instead of inventing a parallel workflow.
- After creating or updating issues, add only short pointers from docs when
  needed. Do not mirror the full issue body into docs or duplicate long rules
  across files.
- During closeout, report which docs became issues, which stayed as background
  context, which were archived or left for review, and what cannot yet be
  claimed.

## Verification

For ordinary repo changes, run the fast deterministic path from the repository
root:

```powershell
python tools\aippocampus\docs\check_docs_health.py --json
python tools\aippocampus\run_tests.py --tier fast
```

Before release, public-readiness, or broad refactor claims, also run
`python tools\aippocampus\run_tests.py --tier full` or the specific slow /
benchmark tier that owns the changed surface.

For public-readiness changes, also scan the repository for local paths and
secret-like strings.
