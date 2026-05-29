# Install Guide

This guide covers the public installation paths for AIppocampus. The canonical
roadmap remains `docs/roadmap.md`; this file is only the operator-facing install
surface.

## Skill-Only Install

### macOS shell setup

macOS can ship with an older `/usr/bin/python3` and no unversioned `python`
command. Install Python 3.10 or newer before running repository checks; the
commands below use Homebrew Python 3.12:

```sh
brew install python@3.12
export PATH="/opt/homebrew/opt/python@3.12/libexec/bin:/opt/homebrew/bin:$PATH"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
```

Use a repo-local virtual environment for verification tools:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip ruff mypy
```

Copy the installable skill package into Codex home:

```sh
mkdir -p "${CODEX_HOME}/skills"
cp -R ./skills/aippocampus "${CODEX_HOME}/skills/aippocampus"
```

Restart Codex or reload skills if your runtime requires it.

Verify the package from the repository:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
```

For a repo-level Stage 0-5 public-readiness smoke, run:

```sh
python ./tools/aippocampus/smoke/run_stage_0_5_smoke.py --repo-root . --json
```

This runs the documented local smoke gates, package-level plugin staging,
local-folder/object-storage sync smokes, and a best-effort secret-like string
scan, then cleans the run-id-scoped `dist/` and `.tmp` artifacts it created.
It is broader than a fresh-clone install check: source-evidence readiness gates
use the local AIppocampus registry under `$CODEX_HOME`, so a new Mac without
enough registered clean source may get diagnostic-only coverage rather than an
overall pass.

## First Onboarding

Register existing Codex sessions and build clean-source indexes:

```sh
python "${CODEX_HOME}/skills/aippocampus/scripts/onboard_codex.py" --all --format json
```

Use `--dry-run` before broad imports when you want a preview. Generated memory
artifacts default to `$CODEX_HOME/aippocampus-registry/threads/<thread>/...`,
not the active project repository.

## MCP Mode

Inspect the local MCP tool catalog:

```sh
python ./skills/aippocampus/scripts/aippocampus_mcp_server.py --list-tools
```

The initial MCP layer is read-mostly. It exposes clean-source and registry
tools plus explicit `register_thread` and `sync_status`.

## Plugin Preview

Build the repo-local Codex plugin package:

```sh
python ./plugins/aippocampus/build_plugin_package.py --repo-root . --json
```

Build output is restricted to `dist/`. The plugin bundles the skill and MCP
config, but it does not silently enable prompt or lifecycle hooks.

Run the package-level install/uninstall smoke:

```sh
python ./plugins/aippocampus/smoke_plugin_install.py --repo-root . --json
```

This stages the built plugin in a temporary plugin root, runs the bundled MCP
tool catalog and a JSON-RPC `initialize` / `notifications/initialized` /
`tools/list` / `tools/call` smoke from that installed location, then removes
the staged plugin. It does not modify your real Codex plugin configuration.

Rollback for this package-level smoke is automatic: the temporary installed
plugin directory is removed before the command exits. For a manual plugin
preview, remove the copied `aippocampus` plugin directory from the temporary
plugin root you chose. Hook installers are separate, so uninstalling the plugin
package does not need to repair prompt or lifecycle hooks unless you explicitly
installed those hooks afterward.

## Hook Install

Install hooks only after reviewing the privacy boundary:

```sh
python "${CODEX_HOME}/skills/aippocampus/scripts/install_aippocampus_prompt_hook.py" status --json
python "${CODEX_HOME}/skills/aippocampus/scripts/install_aippocampus_lifecycle_hook.py" status --json
```

Use `install` or `uninstall` on those scripts when you intentionally want to
change hook state. Prompt-time external-model routes remain optional and depend
on explicit environment configuration.

## Local Sync

The first sync backend is a local folder:

```sh
python ./skills/aippocampus/scripts/sync_bundle.py status --sync-dir <folder> --json
python ./skills/aippocampus/scripts/sync_bundle.py push --sync-dir <folder> --json
python ./skills/aippocampus/scripts/sync_bundle.py pull --sync-dir <folder> --json
python ./skills/aippocampus/scripts/sync_bundle.py repair --sync-dir <folder> --json
```

Raw rollouts are excluded unless `--include-raw` is passed.

`pull` is conservative. When a target file already exists with different
content, AIppocampus keeps the local file in place and writes the incoming copy
under `.sync-conflicts/` inside the target registry. Review those files
manually before replacing anything.

`repair` validates the sync manifest hashes and reports missing files, hash
mismatches, or unsafe manifest paths. Treat any `repair` issue as a stop sign
before using the folder as a cross-device source of truth.

## Object-Storage Sync

The HTTP object-storage adapter uses the same sync manifest and privacy
contract, but stores each bundle file as an object under a prefix. The endpoint
must support HTTP `PUT` and `GET` for object keys:

```sh
export AIPPOCAMPUS_OBJECT_STORE_URL="https://object-store.example/bucket"
export AIPPOCAMPUS_OBJECT_PREFIX="aippocampus/sync"
export AIPPOCAMPUS_OBJECT_STORE_TOKEN="<optional bearer token>"
python ./skills/aippocampus/scripts/sync_object_storage.py status --json
python ./skills/aippocampus/scripts/sync_object_storage.py push --json
python ./skills/aippocampus/scripts/sync_object_storage.py pull --registry-dir <target-registry> --json
python ./skills/aippocampus/scripts/sync_object_storage.py repair --json
```

Raw rollouts are still excluded unless `--include-raw` is passed. The local
object-storage smoke verifies the protocol path without requiring cloud
credentials:

```sh
python ./tools/aippocampus/smoke/smoke_object_storage_sync.py --repo-root . --json
```
