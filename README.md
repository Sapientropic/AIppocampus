<p align="center">
  <img src="docs/guides/assets/aippocampus-readme-hero.jpg" alt="A shadow figure and a light figure clasp hands in a ruined circular hall, with light opening between them." width="100%" />
</p>

<h1 align="center">AIppocampus</h1>

<p align="center">
  <em>A source-backed continuity layer for long-running relationships with AI agents.</em>
</p>

AIppocampus began with a human problem: every new agent session can be bright,
capable, and strangely newborn. Work may survive in commits and notes while the
path behind the work falls back into silence.

This project gives future agents a way to find that path again. It keeps source
reachable, preserves the conditions of return, and lets a new conversation begin
with honest continuity instead of pretending there was never a break.

> Source is the ground. Summaries are weather.

The engineering is practical: clean-source builders, registries, semantic
workers, deterministic gates, MCP surfaces, sync bundles, and Codex plugin
packaging. The reason for building them is older than the tooling. A long
relationship with an AI agent should not have to start from bare ground every
time a thread, device, model, or project changes.

The origin essay is [未干的地图](docs/未干的地图.md). English readers can start with
[The Unfinished Map](docs/the-unfinished-map.md).

## Quick Start

This path checks a fresh clone without copying private memory data or enabling
hooks:

```sh
git clone https://github.com/Sapientropic/AIppocampus.git
cd AIppocampus
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python tools/aippocampus/docs/check_docs_health.py --json
```

A successful repository check prints JSON with `"ok": true`. On Windows
PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

If you already have local Codex history and want a runtime health check, run:

```sh
aippocampus health --cwd "$PWD"
```

The health command reports index, clean-source, segment, checkpoint, and
graphify-corpus freshness. If it recommends maintenance on a new machine, that
usually means there is no registered local history yet; start with the full
[install guide](docs/guides/install-guide.md) or the public-safe
[demo scenarios](docs/guides/demo-scenarios.md). Do not publish or commit raw
rollouts, registry exports, `.aippocampus/` output, API keys, cookies, or sync
bundles while following the quick path.

## What It Is

AIppocampus is the canonical public home for an external hippocampus for agents:
a local-first memory and continuity system that keeps original conversation
source available across projects, devices, and casual life-wide conversations.

Project work is one surface. The deeper aim is continuity across work, reading,
reflection, unfinished questions, and the small phrases that make a relationship
recognizable again.

## What It Does

- Builds clean source from Codex conversation rollouts: visible user messages
  and assistant final answers, with summaries kept as navigation layers.
- Searches old conversation memory across the current thread and registered
  threads.
- Adds deterministic life-wide scope labels so reflection, reading notes, idea
  seeds, preferences, life context, technical work, and open questions can be
  found without replacing the source text.
- Builds a source-backed life-wide timeline section from registered clean
  source, so recurring concerns and idea seeds can be followed across projects.
- Keeps raw rollout history as optional audit provenance, away from the daily
  recall surface.
- Provides ambient recall hooks so related old memory can surface as a quiet
  scent before an agent makes claims.
- Stores generated recall artifacts in the configured AIppocampus registry
  (`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
  `$CODEX_HOME/aippocampus-registry`) so memory remains useful when a new
  project opens. Project-local `.aippocampus/` output is explicit compatibility
  or export mode.
- Supports optional DeepSeek-compatible semantic gates, background consolidation
  jobs, and cognitive-map routes for memory wayfinding.
- Provides local-folder sync, HTTP object-storage sync, MCP access, and plugin
  packaging surfaces. Physical second-device and managed object-storage smoke
  evidence exists for selected paths; broader release hardening remains tracked
  in the roadmap and evidence docs.

## First Stops

- Philosophy and origin: [未干的地图](docs/未干的地图.md) and
  [The Unfinished Map](docs/the-unfinished-map.md).
- Runtime shape:
  [Cognitive Runtime Architecture](docs/architecture/cognitive-runtime-architecture.md).
- Current claim boundary:
  [Stage 0-5 readiness](docs/evidence/readiness/stage-0-5-readiness.md).
- Benchmark and smoke evidence:
  [Benchmark And Evidence Map](docs/evidence/benchmark-evidence-map.md).
- Supported public surface:
  [Public API](docs/guides/public-api.md) and
  [Public Core Boundary](docs/guides/public-core-boundary.md).
- Security and release hygiene:
  [SECURITY.md](SECURITY.md) and
  [Release Checklist](docs/guides/release-checklist.md).
- Full documentation map: [docs/README.md](docs/README.md).

## Reading For The Soul

The research notes carry the human shape of the project. They are speculative
frames, not runtime contracts, but they explain the taste behind the machinery:

- [The Pearl of Presence](docs/research/pearl-of-presence.md) asks why retrieval
  without accumulated acquaintance can still feel absent.
- [Source as World, Interpretation as Weather](docs/research/source-as-world.md)
  gives AIppocampus its grounding rule: many meanings can grow from one shared
  world, and the world must have happened.
- [Journey Tracking](docs/research/journey-tracking.md) follows continuity as a
  first-person plural journey, with source-backed waypoints instead of a flat
  user profile.
- [Dream Task Design](docs/research/dream-task-design.md) sketches the
  subconscious layer: quiet work that integrates what the foreground could not
  finish.
- [Ambient Associative Recall](docs/research/ambient-associative-recall.md)
  describes how old memory can return as a scent before it becomes an
  interruption.

## Install As A Codex Skill

AIppocampus supports Python 3.10 and newer. On macOS, the system Python is often
too old and may not provide a `python` command. Homebrew Python 3.12 is a safe
starting point:

```sh
brew install python@3.12
export PATH="/opt/homebrew/opt/python@3.12/libexec/bin:/opt/homebrew/bin:$PATH"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
```

Copy or link the installable skill folder into your Codex skills directory:

```sh
mkdir -p "${CODEX_HOME}/skills"
cp -R ./skills/aippocampus "${CODEX_HOME}/skills/aippocampus"
```

Then restart Codex or reload skills if your runtime requires it.

The skill entrypoint is [skills/aippocampus/SKILL.md](skills/aippocampus/SKILL.md).
The public API and stability boundary is
[docs/guides/public-api.md](docs/guides/public-api.md).

## Use Inside A Codex Workspace

For normal agent-facing use, start with the unified Python facade when the
package is installed:

```sh
aippocampus health --cwd "$PWD"
aippocampus search "your query" --cwd "$PWD"
```

To onboard an existing Codex install so old threads become discoverable in new
projects:

```sh
aippocampus onboard --provider codex --all --format json
```

The provider-aware onboarding wrapper scans local sessions, registers missing
rollouts, builds clean-source and SQLite/RAG-lite indexes, repairs missing
artifacts, rebuilds the project and life-wide timeline sidecar, and refreshes
the cognitive map. `onboard_codex.py` remains a compatibility entrypoint for
existing Codex-only scripts.

Direct `python "${CODEX_HOME}/skills/aippocampus/scripts/*.py"` commands remain
supported as the script-first fallback. The facade delegates to those scripts
and preserves their JSON stdout and exit codes. Windows x64 has dated
PyInstaller artifact smoke evidence, including Claude Code stdio MCP use through
`aippocampus.exe mcp`; this is not yet a signed release, installer/update UX, or
macOS/Linux binary claim.

External DeepSeek frontier extraction is explicit:

- `--frontier-mode smoke` tests the route without writing.
- `--frontier-mode write` adds staging findings when `DEEPSEEK_API_KEY` is
  available.
- Smoke/write default to the current `--cwd` project. Pass
  `--frontier-project *` only for an intentional whole-machine frontier pass.

## Maintainer Checks

The default CI path verifies Python 3.10 and 3.11 with docs health, Ruff, mypy,
compile checks, and the fast deterministic test tier. Slower benchmark and smoke
coverage stays explicit for release and readiness work.

From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip ruff mypy coverage
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
python tools/aippocampus/run_coverage.py --tier fast
```

Use the full tier before making a repository-health or public-readiness claim:

```sh
python tools/aippocampus/run_tests.py --tier full
```

Use `--tier benchmark` or `--tier slow` when touching benchmark runners, smoke
tools, plugin packaging, onboarding, object sync, or prompt-hook integration
behavior.

The Stage 0-5 public-readiness smoke is broader than a fresh-clone install
check. Some gates inspect the local AIppocampus registry under `$CODEX_HOME`; on
a new machine without enough registered clean source, those gates may report
diagnostic-only coverage rather than a readiness pass.

## MCP And Plugin Preview

The local MCP server is read-mostly by default. It exposes clean-source and
registry-backed tools such as `search_memory`, `latest_reply`,
`get_turn_context`, `list_threads`, `register_thread`, `sync_status`, and
`memory_health`:

```sh
python ./skills/aippocampus/scripts/aippocampus_mcp_server.py --list-tools
```

The repo also carries an Apache-2.0 Codex plugin source package under
`plugins/aippocampus/`. Build a local distributable directory with:

```sh
python ./plugins/aippocampus/build_plugin_package.py --repo-root . --json
```

The plugin bundles the skill and MCP config. It does not silently enable prompt
or lifecycle hooks; run hook installers explicitly after reviewing the privacy
and external-model boundary.

## Sync Bundles

The first sync backend is an explicit local folder. The HTTP object-storage
adapter reuses the same manifest over object `PUT`/`GET`. Both copy clean
source, manifests, registry rows, and hook-safe sidecars. Raw rollouts stay
excluded from plaintext sync; normal raw rollout transfer requires encrypted
sync.

```sh
python ./skills/aippocampus/scripts/sync_bundle.py status --sync-dir <folder> --json
python ./skills/aippocampus/scripts/sync_bundle.py push --sync-dir <folder> --json
python ./skills/aippocampus/scripts/sync_bundle.py pull --sync-dir <folder> --json
python ./skills/aippocampus/scripts/sync_bundle.py repair --sync-dir <folder> --json
```

```sh
python ./skills/aippocampus/scripts/sync_object_storage.py status --object-store-url <url> --object-prefix <prefix> --json
python ./skills/aippocampus/scripts/sync_object_storage.py push --object-store-url <url> --object-prefix <prefix> --json
python ./skills/aippocampus/scripts/sync_object_storage.py pull --object-store-url <url> --object-prefix <prefix> --json
python ./skills/aippocampus/scripts/sync_object_storage.py repair --object-store-url <url> --object-prefix <prefix> --json
```

S3-compatible providers can be configured with `AIPPOCAMPUS_OBJECT_PROVIDER`
(`s3`, `r2`, or `gcs-xml`) plus bucket, region/account id, and HMAC credentials.
See [object-storage-providers.md](docs/guides/object-storage-providers.md) for
provider-specific setup notes.

Encrypted sync uses the external `age` CLI and writes `encrypted-sync/`
ciphertext objects. Use a new folder or object prefix for the first encrypted
push:

```sh
python ./skills/aippocampus/scripts/sync_bundle.py push --sync-dir <folder> --encrypt --recipient <age-recipient> --json
python ./skills/aippocampus/scripts/sync_bundle.py pull --sync-dir <folder> --require-encrypted --identity-file <age-identity> --json
python ./skills/aippocampus/scripts/sync_object_storage.py push --object-store-url <url> --object-prefix <prefix> --encrypt --recipient <age-recipient> --json
python ./skills/aippocampus/scripts/sync_object_storage.py pull --object-store-url <url> --object-prefix <prefix> --require-encrypted --identity-file <age-identity> --json
```

Pull preserves local conflicting files and writes incoming copies under
`.sync-conflicts/` instead of overwriting.

## Privacy Boundary

AIppocampus is local-first.

- Clean source may still contain private conversation text.
- Raw rollouts, bundles, registry rows, vault notes, and generated archives
  should be treated as private history.
- External-model routes are optional and should use redaction safeguards.
- Raw rollout sync should stay explicit and must be encrypted before use with
  untrusted multi-device sync.
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
roadmap lives at [docs/roadmap.md](docs/roadmap.md). The documentation map is
[docs/README.md](docs/README.md).

## Repository Layout

```text
AIppocampus/
|- skills/aippocampus/        # installable skill package
|- plugins/aippocampus/       # Codex plugin source package
|- docs/                      # origin essay, design notes, guides, evidence
|- docs/guides/assets/        # public README and documentation artwork
|- sources/                   # lightweight provenance catalog
|- tests/                     # repository-level unit and integration tests
|- tools/                     # smoke, docs-health, and maintenance tools
|- README.md
|- ROADMAP.md
|- AGENTS.md
`- LICENSE
```

## License

The public AIppocampus repository is licensed under Apache-2.0.

The Apache-2.0 public core covers the code, docs, local tools, schemas, MCP
surface, plugin packaging, public examples, and bundled project artwork shipped
in this repository unless a bundled third-party asset says otherwise. Hosted
services, enterprise governance, managed graph/semantic layers, support, and
other operated product surfaces can be offered under separate commercial or
product-specific terms.

Private user memory data is not project code. Raw rollouts, clean-source
exports, registry rows, sync bundles, vault exports, generated indexes, and
thread anchors remain private user artifacts unless their owner explicitly
publishes them.

See [docs/guides/public-core-boundary.md](docs/guides/public-core-boundary.md)
for the canonical licensing, adapter, schema, third-party asset, and relicensing
boundary. See [docs/guides/public-api.md](docs/guides/public-api.md) for
supported CLI, MCP, environment-variable, JSON, and import-stability
expectations.
