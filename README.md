# AIppocampus

AIppocampus is a source-backed memory layer for long-running relationships with
AI agents.

It is not just a project-memory utility. It keeps original conversation source
reachable across threads, devices, projects, and casual life-wide conversations.
The origin essay is [The Unfinished Map](docs/the-unfinished-map.md).

The runtime design note
[Cognitive Runtime Architecture](docs/cognitive-runtime-architecture.md)
explains why AIppocampus uses deterministic gates, fast semantic workers, job
circuits, and pipeline-level routing instead of one all-purpose agent.

## What It Does

- Builds clean source from Codex conversation rollouts: original visible user
  messages and assistant final answers, not summaries.
- Searches old conversation memory across current and registered threads.
- Keeps raw rollout history as optional audit provenance, not the daily memory
  surface.
- Provides ambient recall hooks so related old memory can surface as a quiet
  scent before the agent makes claims.
- Stores generated recall artifacts under `$CODEX_HOME` by default, so memory
  remains useful when a new project is opened. Project-local `.aippocampus/`
  output is explicit compatibility/export mode.
- Supports optional DeepSeek-compatible semantic gates, background
  consolidation jobs, and cognitive-map routes for memory wayfinding.
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

To onboard an existing Codex install so old threads become discoverable in new
projects:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\onboard_codex.py" --all --format json
```

This is the agent-friendly wrapper around scanning local sessions, registering
missing rollouts, building clean-source and SQLite/RAG-lite indexes, repairing
missing artifacts, rebuilding the project timeline, and refreshing the
cognitive map. External DeepSeek frontier extraction is explicit:
`--frontier-mode smoke` for no-write testing, or `--frontier-mode write` to add
staging findings when `DEEPSEEK_API_KEY` is available. Smoke/write default to
the current `--cwd` project; pass `--frontier-project *` only for an intentional
whole-machine frontier pass.

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

The root roadmap pointer is [ROADMAP.md](ROADMAP.md). The canonical detailed
roadmap lives at [docs/roadmap.md](docs/roadmap.md). The docs map is
[docs/README.md](docs/README.md).

## Repository Layout

```text
AIppocampus/
├─ skills/aippocampus/        # installable skill package
├─ docs/                      # origin essay, design notes, project background
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

