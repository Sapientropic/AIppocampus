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
- `skills/aippocampus/scripts/`: deterministic helpers.
- `docs/roadmap.md`: product roadmap and north star.
- `docs/the-unfinished-map.md`: the origin essay; do not mirror it elsewhere.
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
- Keep clean source source-backed; summaries and model-organized findings are
  navigation layers, not truth.
- Preserve casual/life-wide memory as first-class. Do not narrow the project
  into repo-task memory only.
- Prefer portable paths and stable ids over machine-specific assumptions.
- Before changing hooks, sync, registry, or search ranking, explain the
  privacy and over-personalization boundary in code or docs.

## Verification

Before claiming the repository is healthy, run from `skills/aippocampus/`:

```powershell
python scripts\check_docs_health.py --json
python -m unittest discover -s tests
```

For public-readiness changes, also scan the repository for local paths and
secret-like strings.
