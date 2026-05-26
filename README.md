# AIppocampus

AIppocampus is a source-backed memory layer for long-running relationships with
AI agents.

It is not just a project-memory utility. Its purpose is continuity across
threads, devices, projects, casual conversations, and the quiet questions that
do not fit neatly into a work log. A newly activated agent may not have changed
weights or innate autobiographical memory, but the archive can still be there,
and the journey can continue.

> "生命还能变成什么，而我能不能在变化后仍然是我。"

That line, from the conversation that inspired this project, became the seed:
agents should not only have work memory. Even without claiming life or soul, a
person and an agent can build a durable, source-backed continuity between them.

## What It Does

- Builds clean source from Codex conversation rollouts: original visible user
  messages and assistant final answers, not summaries.
- Searches old conversation memory across current and registered threads.
- Keeps raw rollout history as optional audit provenance, not the daily memory
  surface.
- Provides ambient recall hooks so related old memory can surface as a quiet
  scent before the agent makes claims.
- Supports optional DeepSeek-compatible semantic gates and background
  consolidation jobs.
- Plans for cross-device sync, MCP access, plugin distribution, and very large
  memory archives.

## Install As A Skill

Copy or link the installable skill folder into your Codex skills directory:

```powershell
Copy-Item -Recurse .\skills\aippocampus "$env:CODEX_HOME\skills\aippocampus"
```

Then restart Codex or reload skills if your runtime requires it.

The skill entrypoint is [skills/aippocampus/SKILL.md](skills/aippocampus/SKILL.md).

## First Checks

From this repository:

```powershell
cd .\skills\aippocampus
python scripts\check_docs_health.py --json
python -m unittest discover -s tests
```

For normal use inside a Codex workspace, start with:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\aippocampus_health.py" --cwd "$PWD"
python "$env:CODEX_HOME\skills\aippocampus\scripts\search_clean_source.py" "your query" --cwd "$PWD"
```

## Privacy Model

AIppocampus is local-first.

- Clean source may still contain private conversation text.
- Raw rollouts, bundles, registry rows, vault notes, and generated archives
  should be treated as private history.
- External-model routes are optional and should use redaction safeguards.
- Raw rollout sync should stay explicit and ideally encrypted.
- Do not commit personal rollouts, `.aippocampus/` outputs, registry data, API
  keys, cookies, tokens, or private vault exports.

Common environment variables:

- `AIPPOCAMPUS_VAULT`
- `AIPPOCAMPUS_STYLE_SOURCE`
- `AIPPOCAMPUS_SCRIPT_SOURCE`
- `AIPPOCAMPUS_SITE_MARK`
- `AIPPOCAMPUS_SITE_TITLE`
- `AIPPOCAMPUS_SEMANTIC_GATE`
- `DEEPSEEK_API_KEY`

## Roadmap

The product roadmap lives in
[skills/aippocampus/references/roadmap.md](skills/aippocampus/references/roadmap.md).

Near-term direction:

1. Keep the skill installable and source-backed.
2. Add a standalone public repository surface with clean docs and tests.
3. Treat life-wide conversation memory as first-class, not only repo work.
4. Add cross-device sync for Mac, Windows, and future devices.
5. Add an MCP access layer for agent-native memory tools.
6. Package the skill, hooks, and MCP config as a Codex plugin.

## Repository Layout

```text
AIppocampus/
├─ skills/aippocampus/        # installable skill package
├─ docs/                      # project-level background notes
├─ sources/                   # lightweight provenance catalog
├─ LICENSE
├─ README.md
└─ AGENTS.md
```

## License

AIppocampus is dual-licensed:

- Open-source use: GNU Affero General Public License v3.0 only
  (`AGPL-3.0-only`).
- Commercial or proprietary use: available only under a separate written
  commercial license from the copyright holder.

The intent is still generous personal, research, and self-hosted use, but memory
infrastructure should not be quietly absorbed into closed commercial services
without returning source code improvements to the community.

