# AIppocampus

AIppocampus is a source-backed memory layer for long-running relationships with
AI agents.

It supports Python 3.10 and newer. The default CI path verifies Python 3.10 and
3.11 with docs health, Ruff, mypy, compile checks, and the fast deterministic
test tier. Slower benchmark and smoke coverage stays available as an explicit
release/readiness check.

It is not just a project-memory utility. It keeps original conversation source
reachable across threads, devices, projects, and casual life-wide conversations.
The origin essay is [未干的地图](docs/未干的地图.md), with an English transcreation
at [The Unfinished Map](docs/the-unfinished-map.md).

The runtime design note
[Cognitive Runtime Architecture](docs/cognitive-runtime-architecture.md)
explains why AIppocampus uses deterministic gates, fast semantic workers, job
circuits, and pipeline-level routing instead of one all-purpose agent.

## What It Does

- Builds clean source from Codex conversation rollouts: original visible user
  messages and assistant final answers, not summaries.
- Searches old conversation memory across current and registered threads.
- Adds deterministic life-wide scope labels so personal reflection, reading
  notes, idea seeds, preferences, life context, technical work, and open
  questions can be found without replacing source text.
- Builds a source-backed life-wide timeline section from registered clean
  source, so recurring concerns and idea seeds can be followed across projects.
- Keeps raw rollout history as optional audit provenance, not the daily memory
  surface.
- Provides ambient recall hooks so related old memory can surface as a quiet
  scent before the agent makes claims.
- Stores generated recall artifacts under `$CODEX_HOME` by default, so memory
  remains useful when a new project is opened. Project-local `.aippocampus/`
  output is explicit compatibility/export mode.
- Supports optional DeepSeek-compatible semantic gates, background
  consolidation jobs, and cognitive-map routes for memory wayfinding.
- Provides local-folder sync, HTTP object-storage sync, MCP access, and plugin
  packaging surfaces, with selected physical second-device and managed
  object-storage smoke evidence plus broader release hardening still on the
  roadmap.

## Install As A Skill

On macOS, the system Python is usually too old for this project and may not
provide a `python` command. Use Python 3.10 or newer, for example Homebrew
Python 3.12, and set `CODEX_HOME` when running shell commands:

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

## First Checks

From this repository:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip ruff mypy
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
```

Use `python tools/aippocampus/run_tests.py --tier full` before making a
repository-health or public-readiness claim. Use `--tier benchmark` or
`--tier slow` when touching benchmark runners, smoke tools, plugin packaging,
onboarding, object sync, or prompt-hook integration behavior.

The Stage 0-5 public-readiness smoke is broader than a fresh-clone install
check. Some gates inspect the local AIppocampus registry under `$CODEX_HOME`;
on a new machine without enough registered clean source, those gates may report
diagnostic-only coverage rather than a readiness pass.

For normal use inside a Codex workspace, start with:

```sh
python "${CODEX_HOME}/skills/aippocampus/scripts/aippocampus_health.py" --cwd "$PWD"
python "${CODEX_HOME}/skills/aippocampus/scripts/search_clean_source.py" "your query" --cwd "$PWD"
```

To onboard an existing Codex install so old threads become discoverable in new
projects:

```sh
python "${CODEX_HOME}/skills/aippocampus/scripts/onboard_codex.py" --all --format json
```

This is the agent-friendly wrapper around scanning local sessions, registering
missing rollouts, building clean-source and SQLite/RAG-lite indexes, repairing
missing artifacts, rebuilding the project and life-wide timeline sidecar, and
refreshing the cognitive map. External DeepSeek frontier extraction is explicit:
`--frontier-mode smoke` for no-write testing, or `--frontier-mode write` to add
staging findings when `DEEPSEEK_API_KEY` is available. Smoke/write default to
the current `--cwd` project; pass `--frontier-project *` only for an intentional
whole-machine frontier pass.

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
or lifecycle hooks; run the hook installers explicitly after reviewing the
privacy and external-model boundary.

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
See [object-storage-providers.md](docs/object-storage-providers.md) for the
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

## Privacy Model

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
roadmap lives at [docs/roadmap.md](docs/roadmap.md). The docs map is
[docs/README.md](docs/README.md).

## Repository Layout

```text
AIppocampus/
├─ skills/aippocampus/        # installable skill package
├─ plugins/aippocampus/       # Codex plugin source package
├─ docs/                      # origin essay, design notes, project background
├─ sources/                   # lightweight provenance catalog
├─ LICENSE
├─ README.md
└─ AGENTS.md
```

## License

The public AIppocampus repository is licensed under Apache-2.0.

The Apache-2.0 public core covers the code, docs, local tools, schemas, MCP
surface, plugin packaging, and public examples shipped in this repository unless
a bundled third-party asset says otherwise. Hosted services, enterprise
governance, managed graph/semantic layers, support, and other operated product
surfaces can be offered under separate commercial or product-specific terms.

Private user memory data is not project code. Raw rollouts, clean-source
exports, registry rows, sync bundles, vault exports, generated indexes, and
thread anchors remain private user artifacts unless their owner explicitly
publishes them.

See [docs/public-core-boundary.md](docs/public-core-boundary.md) for the
canonical licensing, adapter, schema, third-party asset, and relicensing
boundary.
