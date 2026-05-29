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

To uninstall or roll back a skill-only preview, remove or replace only
`${CODEX_HOME}/skills/aippocampus`. Generated registries under
`$CODEX_HOME/aippocampus-registry/` are user data, not package files; do not
delete them as part of package rollback unless you are intentionally discarding
local memory artifacts.

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
The product-surface secret/local-path scan excludes third-party benchmark
corpora, which require a separate corpus audit before making claims about the
corpora themselves. The unified smoke is broader than a fresh-clone install
check: source-evidence readiness gates use the local AIppocampus registry under
`$CODEX_HOME`, so a new Mac without enough registered clean source may get
diagnostic-only coverage rather than an overall pass.

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

Tool errors use stable JSON payloads inside MCP `content` text:

```json
{
  "ok": false,
  "error": {
    "code": "clean_source_unavailable",
    "message": "Clean-source artifacts are unavailable for the requested workspace or clean_source_dir.",
    "details": {
      "missing_files": ["messages.jsonl"]
    }
  }
}
```

Common client-facing codes include `missing_query`, `malformed_params`,
`malformed_arguments`, `missing_tool_name`, `unknown_tool`,
`unsupported_mutation`, `clean_source_unavailable`, `missing_turn_selector`,
`message_not_found`, `turn_not_found`, `health_check_failed`, and
`tool_failed`. `unsupported_mutation` is intentional: the plugin should not add
broad write APIs merely to prove MCP integration.

`list_threads` reports a missing registry as a non-error
`status: "registry_missing"` with an empty `threads` list. That distinguishes a
fresh install from an existing registry that simply has no matching threads.

## Plugin Preview

Build the repo-local Codex plugin package:

```sh
python ./plugins/aippocampus/build_plugin_package.py --repo-root . --json
```

Build output is restricted to `dist/`. The plugin bundles the skill and MCP
config, but it does not silently enable prompt or lifecycle hooks.

### Distribution status

Current verified package surfaces are:

- repo-local plugin build output under `dist/`
- package-level temporary install/MCP JSON-RPC/uninstall smoke
- real Codex app-server local-marketplace install/MCP/uninstall smoke
- external install validation recorded by issue #29 and summarized in
  `docs/public-readiness-verification.md`

These checks do not claim a public marketplace submission, every Codex client UI
wrapper, or independent third-party review. If you publish through a marketplace
or another distribution channel, keep that evidence separate from the local
smokes and record the exact client/runtime used.

Run the package-level install/uninstall smoke:

```sh
python ./plugins/aippocampus/smoke_plugin_install.py --repo-root . --json
```

This stages the built plugin in a temporary plugin root, runs the bundled MCP
tool catalog and a JSON-RPC `initialize` / `notifications/initialized` /
`tools/list` / `tools/call` smoke from that installed location, then removes
the staged plugin. It does not modify your real Codex plugin configuration.

When you intentionally want to exercise the real Codex app-server plugin
manager and host MCP path, run:

```sh
python ./plugins/aippocampus/smoke_real_codex_host.py --repo-root . --json
```

This creates a run-id-scoped local marketplace, installs the plugin through the
real host, reloads MCP config, calls `sync_status`, then uninstalls the plugin
and removes temporary marketplace/build/cache artifacts. It still is not a
public marketplace submission or third-party fresh-clone review.

### Uninstall and rollback

Rollback for the package-level smoke is automatic: the temporary installed plugin
directory is removed before the command exits. For a manual plugin preview,
remove the copied `aippocampus` plugin directory from the plugin root you chose
or use the host client's plugin uninstall action if you installed through a
plugin manager.

Plugin uninstall removes the packaged skill/MCP surface only. Hook installers
are separate consent surfaces, so uninstalling the plugin package does not need
to repair prompt or lifecycle hooks unless you explicitly installed those hooks
afterward. External-model routes are also separate: remove the relevant
environment configuration if you no longer want any optional model-backed
background jobs to run.

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

Raw rollouts are excluded from plaintext sync. Normal `--include-raw` usage
requires encrypted sync:

```sh
python ./skills/aippocampus/scripts/sync_bundle.py push --sync-dir <folder> --encrypt --recipient <age-recipient> --json
python ./skills/aippocampus/scripts/sync_bundle.py status --sync-dir <folder> --require-encrypted --json
python ./skills/aippocampus/scripts/sync_bundle.py pull --sync-dir <folder> --require-encrypted --identity-file <age-identity> --json
python ./skills/aippocampus/scripts/sync_bundle.py repair --sync-dir <folder> --require-encrypted --identity-file <age-identity> --json
```

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

For S3-compatible providers, use provider-aware signing instead of bearer
tokens:

```sh
export AIPPOCAMPUS_OBJECT_PROVIDER="s3" # or r2, gcs-xml
export AIPPOCAMPUS_OBJECT_BUCKET="aippocampus-memory"
export AIPPOCAMPUS_OBJECT_REGION="us-east-1"
export AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID="<access key id>"
export AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY="<secret access key>"
python ./skills/aippocampus/scripts/sync_object_storage.py push --encrypt --recipient <age-recipient> --json
```

For Cloudflare R2, set `AIPPOCAMPUS_OBJECT_PROVIDER=r2` and
`AIPPOCAMPUS_OBJECT_ACCOUNT_ID=<account id>`; the default region is `auto`.
For Google Cloud Storage, set `AIPPOCAMPUS_OBJECT_PROVIDER=gcs-xml` and use XML
API interoperability HMAC keys. See `docs/object-storage-providers.md` for the
provider-specific pitfalls.

Raw rollouts are still excluded from plaintext object-storage sync. Use
`--encrypt --include-raw` only when the object prefix is new or already
encrypted:

```sh
python ./skills/aippocampus/scripts/sync_object_storage.py push --encrypt --recipient <age-recipient> --json
python ./skills/aippocampus/scripts/sync_object_storage.py status --require-encrypted --json
python ./skills/aippocampus/scripts/sync_object_storage.py pull --require-encrypted --identity-file <age-identity> --registry-dir <target-registry> --json
python ./skills/aippocampus/scripts/sync_object_storage.py repair --require-encrypted --identity-file <age-identity> --json
```

The local object-storage smoke verifies the protocol path without requiring cloud
credentials:

```sh
python ./tools/aippocampus/smoke/smoke_object_storage_sync.py --repo-root . --json
```

To verify a real managed provider or remote object-store environment, configure
`AIPPOCAMPUS_OBJECT_STORE_URL` or `AIPPOCAMPUS_OBJECT_PROVIDER` plus the matching
provider credentials, then run the encrypted real-provider smoke:

```sh
python ./tools/aippocampus/smoke/smoke_real_provider_encrypted_sync.py --json
```

If those variables are absent, the command should fail early with a missing
object-store/provider diagnostic; do not treat the local HTTP smoke as managed
provider evidence.

Encrypted sync preflights the external `age` CLI before syncing. It looks at
`AIPPOCAMPUS_AGE_BIN` before `PATH`, because GUI clients on macOS may not
inherit the same shell path as Terminal. Use a new sync directory or object
prefix for the first encrypted push; encrypted push refuses known plaintext
local sync data and plaintext object prefixes, but it does not clean up older
plaintext copies elsewhere.
