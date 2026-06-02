# Install Guide

This guide covers the public installation paths for AIppocampus. The canonical
roadmap remains `docs/roadmap.md`; this file is only the operator-facing install
surface.

For supported CLI, MCP, JSON, environment-variable, and import-stability
expectations, see [public-api.md](public-api.md).
For host-family support status and what not to overclaim, see
[ecosystem-integration-matrix.md](ecosystem-integration-matrix.md).
The install guide shows common commands only; the full environment-variable
matrix and Python import layer policy live in that public API document so the
stability boundary has one owner.

For a new external user or agent host, follow the
[10-minute public API path](public-api.md#ten-minute-public-path) first:
package probe, read-only provider status, MCP tool list, then health and
clean-source search once the current workspace has registered or imported
source. Treat plugin packaging, hooks, sync, object storage, Dream, semantic
jobs, and benchmarks as advanced surfaces unless that path proves the user
actually needs them.

## Agent One-Command Path

Agents that need to verify AIppocampus without cloning the repository can use
the PyPI `uvx` path:

```sh
uvx aippocampus --help
```

Check local provider status without writing memory artifacts:

```sh
uvx aippocampus onboard --provider codex --status --format json
```

Register local Codex history only after the user explicitly agrees:

```sh
uvx aippocampus onboard --provider codex --all --format json
```

Use the GitHub `uvx --from git+...` form only when intentionally testing an
unreleased main-branch snapshot.

## Standalone Binary Status

The default public install path is the PyPI `uvx aippocampus ...` probe above.
Windows x64 has dated maintainer smoke evidence for a
PyInstaller standalone binary, but AIppocampus does not yet claim signed
downloads, installer/update UX, or Python-free standalone binaries for macOS or
Linux.

The current support/defer/drop matrix lives in
[standalone-binary-packaging.md](../planning/standalone-binary-packaging.md).
Use that matrix before recommending a binary path. For macOS and Linux today,
recommend the PyPI/source install path instead.

## Skill-Only Install

### macOS shell setup

macOS can ship with an older `/usr/bin/python3` and no unversioned `python`
command. Install Python 3.12 or newer before running repository checks; the
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
`${CODEX_HOME}/skills/aippocampus`. Generated registries are user data, not
package files; do not delete them as part of package rollback unless you are
intentionally discarding local memory artifacts. New non-Codex setups should
prefer `AIPPOCAMPUS_REGISTRY_DIR` or `AIPPOCAMPUS_HOME`; existing Codex installs
continue to use `$CODEX_HOME/aippocampus-registry/` as a legacy fallback.

Verify the package from the repository:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
```

That Ruff command is the staged hard gate from `pyproject.toml`; broader
`--select ALL --statistics` output is advisory lint debt, not a normal install
or CI failure gate.

For benchmark work from a fresh clone, install the stable benchmark extra and
run the deterministic smoke lane before attempting broader benchmark tiers:

```sh
python -m pip install -e ".[benchmark]"
python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast
```

The `benchmark` extra is currently empty because the deterministic benchmark
smoke uses only stdlib plus checked-in public fixtures. Live/provider-backed
tracks need explicit environment configuration and are not part of normal
install verification.

### Remote macOS install smoke

Maintainers can trigger the fresh-clone macOS install smoke from a Windows
machine without switching to a MacBook. The workflow at
`.github/workflows/macos-install-smoke.yml` runs on a GitHub-hosted macOS runner,
creates a clean virtual environment, installs the package, stages the skill into
an isolated `CODEX_HOME`, checks the CLI/MCP surface, and uploads the smoke logs.

From Windows PowerShell:

```powershell
gh workflow run macos-install-smoke.yml `
  --repo Sapientropic/AIppocampus `
  --ref main `
  -f runner-label=macos-latest `
  -f python-version=3.12

gh run list --repo Sapientropic/AIppocampus --workflow "macOS Install Smoke" --limit 1
gh run watch --repo Sapientropic/AIppocampus <run-id>
```

This is a public install smoke, not a claim about private Codex Desktop state,
local registry quality, keychain behavior, or full Stage 0-5 readiness. Use a
self-hosted MacBook runner only when you intentionally need those local-machine
surfaces.

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
check: source-evidence readiness gates use the configured AIppocampus registry,
so a new machine without enough registered clean source may get diagnostic-only
coverage rather than an overall pass.

For the source-evidence selection slice directly, run:

```sh
python ./tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py --json
```

By default this is a semantic-sidecar-required smoke: it only selects
non-technical life-wide clean-source turns that already have dynamic semantic
scope labels. If it reports `insufficient_selected_cases`, that usually means
the registry has too few semantic-sidecar rows for this claim, not that clean
source search is broken. Rerun with `--allow-deterministic-labels` only as a
wiring baseline; fallback results can check deterministic label/search behavior,
but they must not be used as evidence that semantic-sidecar selected coverage is
ready.

## First Onboarding

Register existing Codex sessions and build clean-source indexes:

```sh
aippocampus onboard --provider codex --all --format json
```

Use `--dry-run` before broad imports when you want a preview. Generated memory
artifacts default to the configured AIppocampus registry
(`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
`$CODEX_HOME/aippocampus-registry`) rather than the active project repository.
`onboard_codex.py` remains available as the Codex-only compatibility entrypoint.

Check provider readiness before writing:

```sh
aippocampus onboard --status --cwd "$PWD"
```

`auto` keeps Codex as the safest default and lists other detected providers
separately. `claude-code` and `generic-jsonl` require explicit provider
selection before they write clean source.

## MCP Mode

Inspect the local MCP tool catalog:

```sh
aippocampus mcp list-tools
```

Or through the packaged `uvx` path:

```sh
uvx aippocampus mcp list-tools
```

The MCP layer is read-mostly. It exposes clean-source and registry tools,
progressive recall navigation through `recall_context` / `recall_deepen`, plus
explicit `register_thread` and `sync_status`.

For a human-facing progressive recall wiring check without hand-copying MCP
route handles, run:

```sh
aippocampus smoke recall-funnel "remembered phrase or project cue" --json
```

The smoke calls `recall_context`, passes the first reopenable `recall_deepen`
route handle to `recall_deepen`, and reports counts, field names,
stale/wrong-handle status, and the privacy boundary. It does not echo the cue
or print source-window text.

For optional external-model work, check whether the route's API-key environment
variable is visible to the current process and a child process:

```sh
aippocampus doctor provider --json
```

This is a visibility diagnostic, not a credential-store reader. A key can exist
in a `.env` file, password manager, shell profile, or another project while the
Codex hook process still cannot see `DEEPSEEK_API_KEY` or the selected
OpenAI-compatible key variable. The doctor prints variable names and booleans,
never key values or base URL values. It is a presence-only check: it does not
read or validate the key value, so it cannot prove the key is non-empty, correct,
or unexpired. It checks the process running the command and a child process it
starts; it does not prove what a previously started Codex Desktop hook process
could see. Use `--provider-env-var <NAME>` when you need to test a local route
override without changing the route configuration.

Direct script commands remain supported when the facade is not installed:

```sh
python ./skills/aippocampus/scripts/aippocampus_mcp_server.py --list-tools
python "${CODEX_HOME}/skills/aippocampus/scripts/onboard.py" --provider codex --all --format json
```

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
`message_not_found`, `turn_not_found`, `missing_intent`,
`missing_recall_handle`, `malformed_recall_handle`, `stale_recall_handle`,
`source_ref_not_found`, `active_recall_lock_not_reopenable`,
`health_check_failed`, and `tool_failed`. `unsupported_mutation` is intentional:
the plugin should not add broad write APIs merely to prove MCP integration.

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
  `docs/evidence/readiness/public-readiness-verification.md`

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
python "${CODEX_HOME}/skills/aippocampus/scripts/install_aippocampus_prompt_hook.py" status --last --json
python "${CODEX_HOME}/skills/aippocampus/scripts/install_aippocampus_lifecycle_hook.py" status --json
```

Use `install` or `uninstall` on those scripts when you intentionally want to
change hook state. Prompt-time external-model routes remain optional and depend
on explicit environment configuration. Prompt hook `--last` reads the local
sanitized last-status projection written by the hook, not the verbose debug
JSONL, so it can show the latest `no_memory` / `scent` / `candidate` /
`source_backed_evidence` surface without exposing prompt text, raw cards,
snippets, session ids, secrets, or local paths.

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

Device-key helpers keep local private identity material under the registry's
encrypted sync state and store only public trusted recipients for future pushes:

```sh
python ./skills/aippocampus/scripts/encrypted_sync_admin.py key init --registry-dir <registry> --device-name <name> --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py key recipient --registry-dir <registry>
python ./skills/aippocampus/scripts/encrypted_sync_admin.py key trust --registry-dir <registry> --recipient <second-device-recipient> --device-name <name> --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py key trust --registry-dir <registry> --recipient <offline-recovery-recipient> --device-name paper-recovery-kit --recovery --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py key list --registry-dir <registry> --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py key revoke --registry-dir <registry> --recipient <old-recipient> --dry-run --json
```

After `key init` or `key trust`, encrypted local-folder pushes can use the
trusted-recipient list without repeating `--recipient`. `key recipient` prints
only the public recipient; it must never be used to exchange or publish the
`AGE-SECRET-KEY...` identity file.

Recovery is explicit. `key trust --recovery` stores only the public recovery
recipient and includes it in future encrypted pushes; the matching private
recovery identity must stay offline and must not be copied into a sync folder,
object prefix, issue, or demo bundle. If all trusted device identities and all
recovery identities are lost, encrypted sync data is unrecoverable.

`key revoke --dry-run` reports the re-encryption plan. A revoked recipient is
removed from future trusted-recipient pushes only after a fresh encrypted bundle
is pushed for the remaining recipients and repaired or pulled with a remaining
identity. Older encrypted bundles should be treated as still decryptable by the
revoked identity.

To migrate an existing plaintext sync folder, first inventory it, write a fresh
encrypted target, run encrypted repair or pull, then explicitly clean up the old
plaintext files:

```sh
python ./skills/aippocampus/scripts/encrypted_sync_admin.py migrate-to-encrypted --sync-dir <old-plaintext-folder> --target-sync-dir <new-encrypted-folder> --registry-dir <registry> --dry-run --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py migrate-to-encrypted --sync-dir <old-plaintext-folder> --target-sync-dir <new-encrypted-folder> --registry-dir <registry> --json
python ./skills/aippocampus/scripts/sync_bundle.py repair --sync-dir <new-encrypted-folder> --require-encrypted --identity-file <age-identity> --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py cleanup-plaintext --sync-dir <old-plaintext-folder> --dry-run --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py cleanup-plaintext --sync-dir <old-plaintext-folder> --confirm --verified-encrypted-target --json
```

Cleanup reports and deletes only plaintext files managed by the plaintext sync
manifest, and non-dry-run cleanup requires both confirmation and an explicit
acknowledgement that the encrypted target already passed repair or pull. It is
not a cloud-provider lifecycle rule and it does not claim to erase unrelated
objects or forensic SSD remnants.

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
must support HTTP `PUT` and `GET` for sync, plus `DELETE` when using plaintext
cleanup:

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
API interoperability HMAC keys. See `docs/guides/object-storage-providers.md` for the
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

Object-storage plaintext migration uses the same admin CLI. The target prefix
must be fresh; dry-run reads the plaintext manifest and reports managed objects
without uploading or deleting:

```sh
python ./skills/aippocampus/scripts/encrypted_sync_admin.py migrate-object-to-encrypted --object-prefix <old-plaintext-prefix> --target-object-prefix <new-encrypted-prefix> --registry-dir <registry> --dry-run --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py migrate-object-to-encrypted --object-prefix <old-plaintext-prefix> --target-object-prefix <new-encrypted-prefix> --registry-dir <registry> --json
python ./skills/aippocampus/scripts/sync_object_storage.py repair --require-encrypted --object-prefix <new-encrypted-prefix> --identity-file <age-identity> --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py cleanup-object-plaintext --object-prefix <old-plaintext-prefix> --dry-run --json
python ./skills/aippocampus/scripts/encrypted_sync_admin.py cleanup-object-plaintext --object-prefix <old-plaintext-prefix> --confirm --verified-encrypted-target --json
```

Object cleanup deletes only objects listed in the plaintext sync manifest,
with the manifest object deleted last, and requires the same verified-target
acknowledgement for non-dry-run cleanup. If old plaintext objects exist without
a manifest, inspect and remove them through the provider's own tools.

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
