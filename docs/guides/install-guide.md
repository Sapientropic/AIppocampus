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
Safe local configuration starts from
[`../../.env.example`](../../.env.example) and
[safe-environment.md](safe-environment.md).
The runtime and tooling dependency taxonomy lives in
[dependency-contract.md](dependency-contract.md).
The product friction budget lives in
[product-profiles.md](../architecture/product-profiles.md): first recall should
stay `personal_default`; core hook setup is the consented next step for ambient
continuity, while diagnostics, sync, governance, and research surfaces stay
operator or opt-in paths unless a user explicitly needs them.

For a new external user or agent host, follow the
[10-minute public API path](public-api.md#ten-minute-public-path) first:
package probe, read-only provider status, explicit onboarding only with user
consent, then clean-source search for a first source-backed snippet. After that
first source has been found, offer core hook setup as the normal ambient
continuity step, still behind explicit trust and rollback. Treat plugin
packaging, sync, object storage, Dream, semantic jobs, and benchmarks as
advanced surfaces unless that path proves the user actually needs them.

## First Recall Path

Start with the PyPI `uvx` path:

```sh
uvx aippocampus --help
```

The personal/core default does not require purpose tokens, review queues, or
compliance policy setup before this first-recall path. Heavier profile
boundaries are defined in
[public-core-boundary.md](public-core-boundary.md#product-profile-boundary).

Check local provider status without writing memory artifacts:

```sh
uvx aippocampus onboard --provider codex --status
```

The status output is a provider-matrix readiness view. It may include other
locally detectable providers beside Codex; do not read that as Codex-only
provider-scoped evidence.

Register local Codex history only after the user explicitly agrees:

```sh
uvx aippocampus onboard --provider codex --all
uvx aippocampus search "a distinctive old phrase"
```

Try an exact phrase first. If the wording is fuzzy, use a project cue
(`repo / feature / object / topic`) or a time cue (`recent`, `last month`, or a
known period). Those cues are candidate navigation until search returns a
source-backed snippet with source/date/turn metadata. Use `--format json` only
for automation. Use the GitHub `uvx --from git+...` form only when intentionally
testing an unreleased main-branch snapshot.

## Core Hook Setup

Manual onboarding and search prove that local source can be found. Prompt and
lifecycle hooks are the core trusted setup that keeps AIppocampus from feeling
like a manual grep tool in the next conversation.

Review local readiness before changing Codex hook state:

```sh
aippocampus update status
aippocampus hooks prompt status --last
aippocampus hooks lifecycle status
```

Install both AIppocampus-owned Codex hooks only after the user trusts this
machine and understands the boundary:

```sh
aippocampus update apply --surface hooks
```

Or install them separately when you want to inspect each surface:

```sh
aippocampus hooks prompt install
aippocampus hooks lifecycle install
```

Trust boundary in plain language:

- The prompt hook runs on `UserPromptSubmit`. It may read the current prompt and
  local AIppocampus registry to emit no output, a recall scent, candidate
  navigation, or source-backed evidence for the agent to reopen.
- The prompt hook is fail-open and should not block normal chat when
  AIppocampus is missing, stale, or slow.
- The lifecycle hook runs on session events and refreshes clean source, indexes,
  registry rows, and hook-safe sidecars within bounded work.
- Hook/background logs are local diagnostics with retention caps; `aippocampus
  health --json` reports oversized artifacts and `aippocampus logs rotate`
  applies the bounded cleanup without reading log contents into the report.
- Raw rollouts, generated indexes, registry rows, and private artifacts remain
  local unless the user explicitly exports or syncs them.
- External-model semantic routes are separate opt-in configuration. Local hook
  install does not require an LLM key and must not silently enable external
  model calls.

Rollback is explicit:

```sh
aippocampus hooks prompt uninstall
aippocampus hooks lifecycle uninstall
```

For the detailed runtime contract, see
[`../../skills/aippocampus/references/ambient-hooks.md`](../../skills/aippocampus/references/ambient-hooks.md).

## First-Run Capability Ladder

Use `aippocampus update status` as the canonical readiness card. It is not a
second source of truth; it projects existing CLI, hook, MCP, and provider checks
into labels a new user can understand. This avoids the
[#201](https://github.com/Sapientropic/AIppocampus/issues/201)-style failure
mode where source exists and manual search works, but foreground continuity
still feels like grep because hooks or provider visibility are not ready.

| Label | What works | What does not work yet | Next check |
| --- | --- | --- | --- |
| `source_search_ready` | Onboarding plus clean-source search after consent. | Automatic prompt-time recall is not implied. | `aippocampus onboard --provider codex --all` |
| `active_recall_ready` | MCP/progressive recall can let an agent reopen source. | It does not install prompt/lifecycle hooks. | `aippocampus mcp list-tools` |
| `ambient_hooks_ready` | Prompt/lifecycle hooks can emit recall scents and refresh clean source/indexes. | Semantic lift still needs provider visibility. | `aippocampus hooks prompt status --last` |
| `semantic_provider_ready` | Semantic lift, warm scouts, and provider-backed jobs can call the configured route. | It does not prove a previously started hook process can see the key. | `aippocampus doctor provider --json` |
| `hook_provider_ready` | The provider key is visible to the current process and a child process like a future/restarted hook. | It still does not inspect an already-running older Codex Desktop hook process or validate the key value. | `aippocampus hooks prompt status --last` |
| `dream_or_subconscious_ready` | Provider-backed background semantic, subconscious, and Dream-style work can run. | No provider means these routes stay disabled or diagnostic-only today. | `aippocampus doctor provider --json` |
| `agent_fallback_ready` | Staging-only fallback queue can operate without an external LLM key when the host exposes `AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE=1`; fallback results can only materialize through source-backed finding joins. | This does not execute a host agent, promote candidates, bypass source gates, or prove Dream/semantic quality. | `aippocampus doctor provider --json` |

No key is required for basic source-backed search. Missing, disabled, or
invisible provider state should be shown as a capability label, not as a claim
that source search is broken. The doctor reports variable names and visibility
booleans only; it must not print key values, raw prompts, local paths, source
snippets, or registry rows.

## Updating AIppocampus

Run update status when AIppocampus feels installed but not alive yet:

```sh
aippocampus update status
aippocampus update plan
```

The update check is read-only. It reports whether the CLI package, installed
skill copy, MCP config, plugin package, Codex hooks, and optional LLM provider
key are current. Human output leads with profile-aware readiness:

- `core_ready`: the small source-backed CLI/skill path is usable.
- `magic_ready`: hooks plus the optional LLM route can power the more ambient
  external-hippocampus feel.
- optional/plugin and operator surfaces stay visible without making the default
  personal path look broken.

Apply local package/effect surfaces explicitly:

```sh
aippocampus update apply --surface skill
aippocampus update apply --surface hooks
aippocampus update apply --all-local
```

`--all-local` syncs the installable skill, rebuilds the repo-local plugin
package, and installs AIppocampus-owned Codex hooks. It does not copy private
memory data, raw rollouts, generated indexes, sync bundles, or package caches.
It also does not read, print, or store API-key values. If `update status`
reports the LLM surface as missing, set the reported environment variable
(`DEEPSEEK_API_KEY` by default, or the configured OpenAI-compatible key env)
in the process that launches Codex, then rerun status. When the key already
exists in a private source but Codex hooks cannot inherit it, use the explicit
provider-key bridge below instead of editing `hooks.json` by hand.

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
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
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

Maintainer verification from a repository checkout, not required for a first
recall:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier quick
python tools/aippocampus/run_tests.py --tier pr
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

Preview provider readiness before writing:

```sh
aippocampus onboard --status --cwd "$PWD"
```

Then register existing Codex sessions and build clean-source indexes only after
user consent:

```sh
aippocampus onboard --provider codex --all
aippocampus search "a distinctive old phrase"
```

Use `--dry-run` before broad imports when you want a preview, and use
`--format json` for agent/operator automation. Generated memory artifacts
default to the configured AIppocampus registry
(`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
`$CODEX_HOME/aippocampus-registry`) rather than the active project repository.
Codex onboarding now runs through the provider-aware facade or the package owner
`aippocampus_runtime.onboarding.codex`.

`auto` keeps Codex as the safest default and lists other detected providers
separately. `claude-code` and `generic-jsonl` require explicit provider
selection before they write clean source.

First recall query modes:

- Exact phrase: search distinctive old wording when the user remembers it.
- Project cue: search a repo, feature, object, person, or topic name.
- Time cue: search a remembered period such as `recent`, `last month`, or a known date.

Project/time cues are candidate navigation until a source-backed snippet appears.

## Agent-Host / Operator MCP Mode

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

This section is for agent-host wiring and operator verification. It is not a
prerequisite for the first local recall path above.

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

When a key exists somewhere on the machine but the hook-relevant process still
reports `missing_provider_env_var`, use explicit credential-source discovery:

```sh
aippocampus doctor provider --discover-credential-sources --credential-dotenv /path/to/.env --json
```

Discovery is opt-in. It does not recursively scan the filesystem, read the
current directory's `.env` by default, or inspect OS credential stores. The
report redacts secret values and omits local paths unless the operator asks for
them. Add `--validate-credentials` only when you want a lightweight provider
probe; validation is skipped for non-HTTPS routes except loopback HTTP. This
diagnostic does not install a hook wrapper or bridge credentials into Codex
Desktop by itself.

To bridge a private key source into future Codex hook processes, use the
separate onboarding surface:

```sh
aippocampus onboard provider-key --plan --target codex-hooks --source explicit-dotenv --credential-dotenv /path/to/.env --json
aippocampus onboard provider-key --apply --target codex-hooks --source explicit-dotenv --credential-dotenv /path/to/.env --json
aippocampus onboard provider-key --undo --target codex-hooks --json
```

The bridge writes an AIppocampus-owned local wrapper and manifest, then installs
Codex hook commands that call the wrapper. It does not put the key value in
`hooks.json`, the manifest, or public JSON. OS credential-store sources are also
explicit adapters: `macos-keychain`, `windows-credential-manager`, and
`linux-secret-service` require their locator flags and do not run during
ordinary provider doctor checks. After apply, restart Codex or the hook host and
rerun `aippocampus doctor provider --json`; apply can only prepare
future/restarted hook processes, not prove an already-running Desktop hook saw
the key.

Maintainers can smoke-test the OS credential-store bridge separately:

```sh
python tools/aippocampus/smoke/smoke_provider_key_bridge_os_store.py --source auto --json
```

The smoke creates a temporary test credential in the selected OS store, verifies
that the wrapper can load it into a hook-process environment update, and cleans
it up. Public output redacts the secret, store locator, and local temporary
paths. Unsupported platforms or missing OS store tools return an explicit
`skipped` report. Dated evidence and the claim boundary live in
[`public-readiness-verification.md`](../evidence/readiness/public-readiness-verification.md#2026-06-07-issue-784-provider-key-bridge-os-store-smoke).

Package modules remain available when the facade is not installed:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.mcp.server --list-tools
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.onboarding.facade --provider codex --all --format json
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

## Hook Reference Commands

The first-run hook path is [Core Hook Setup](#core-hook-setup). Use the
module-level commands below only when the `aippocampus` facade is not installed
or you are testing the packaged skill copy directly:

```sh
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.hooks.install_prompt status --json
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.hooks.install_prompt status --last --json
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.hooks.install_lifecycle status --json
```

Use `install` or `uninstall` on those scripts when you intentionally want to
change hook state. Prompt hook `--last` reads the local sanitized last-status
projection written by the hook, not the verbose debug JSONL, so it can show the
latest `no_memory` / `scent` / `candidate` / `source_backed_evidence` surface
without exposing prompt text, raw cards, snippets, session ids, secrets, or
local paths.

## Local Sync

The first sync backend is a local folder:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle status --sync-dir <folder> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle push --sync-dir <folder> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle pull --sync-dir <folder> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle repair --sync-dir <folder> --json
```

Raw rollouts are excluded from plaintext sync. Normal `--include-raw` usage
requires encrypted sync:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle push --sync-dir <folder> --encrypt --recipient <age-recipient> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle status --sync-dir <folder> --require-encrypted --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle pull --sync-dir <folder> --require-encrypted --identity-file <age-identity> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle repair --sync-dir <folder> --require-encrypted --identity-file <age-identity> --json
```

Device-key helpers keep local private identity material under the registry's
encrypted sync state and store only public trusted recipients for future pushes:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key init --registry-dir <registry> --device-name <name> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key recipient --registry-dir <registry>
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key trust --registry-dir <registry> --recipient <second-device-recipient> --device-name <name> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key trust --registry-dir <registry> --recipient <offline-recovery-recipient> --device-name paper-recovery-kit --recovery --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key list --registry-dir <registry> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key revoke --registry-dir <registry> --recipient <old-recipient> --dry-run --json
```

The key-provider status surface is explicit and fail-closed:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key provider-status --registry-dir <registry> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key provider-configure --registry-dir <registry> --provider file --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin key provider-configure --registry-dir <registry> --provider windows-credential-manager --json
```

Current public output reports the active provider, availability, and whether a
file-identity fallback was attempted. `file` is the implemented provider.
`macos-keychain`, `windows-credential-manager`, and `linux-secret-service` are
reserved provider names with deterministic diagnostics; until adapters land,
configuring one returns `key_provider_unavailable` and does not fall back to the
local file identity even when that file exists. The JSON output omits local
identity paths and private key material.

After `key init` or `key trust`, encrypted local-folder pushes can use the
trusted-recipient list without repeating `--recipient`. `key recipient` prints
only the public recipient; it must never be used to exchange or publish the
`AGE-SECRET-KEY...` identity file.

Recovery is explicit. `key trust --recovery` stores only the public recovery
recipient and includes it in future encrypted pushes; the matching private
recovery identity must stay offline and must not be copied into a sync folder,
object prefix, issue, or demo bundle. If all trusted device identities and all
recovery identities are lost, encrypted sync data is unrecoverable.

`key list --json` reports the recovery and vault-id backup diagnostics without
printing the vault id, registry path, private identity, or recovery-kit secret.
If a local `vault-id.backup` file exists beside the encrypted-sync `vault-id`,
status reports whether that marker is current, missing, invalid, or mismatched.
This is only a restore diagnostic: AIppocampus does not silently regenerate a
missing or corrupt vault id as the same vault, and it does not provide hosted
escrow or passphrase recovery.

`key revoke --dry-run` reports the re-encryption plan. A revoked recipient is
removed from future trusted-recipient pushes only after a fresh encrypted bundle
is pushed for the remaining recipients and repaired or pulled with a remaining
identity. Older encrypted bundles should be treated as still decryptable by the
revoked identity.

To migrate an existing plaintext sync folder, first inventory it, write a fresh
encrypted target, run encrypted repair or pull, then explicitly clean up the old
plaintext files:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin migrate-to-encrypted --sync-dir <old-plaintext-folder> --target-sync-dir <new-encrypted-folder> --registry-dir <registry> --dry-run --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin migrate-to-encrypted --sync-dir <old-plaintext-folder> --target-sync-dir <new-encrypted-folder> --registry-dir <registry> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle repair --sync-dir <new-encrypted-folder> --require-encrypted --identity-file <age-identity> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin cleanup-plaintext --sync-dir <old-plaintext-folder> --dry-run --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin cleanup-plaintext --sync-dir <old-plaintext-folder> --confirm --verified-encrypted-target --json
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
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli status --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli push --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli pull --registry-dir <target-registry> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli repair --json
```

For S3-compatible providers, use provider-aware signing instead of bearer
tokens:

```sh
export AIPPOCAMPUS_OBJECT_PROVIDER="s3" # or r2, gcs-xml
export AIPPOCAMPUS_OBJECT_BUCKET="aippocampus-memory"
export AIPPOCAMPUS_OBJECT_REGION="us-east-1"
export AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID="<access key id>"
export AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY="<secret access key>"
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli push --encrypt --recipient <age-recipient> --json
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
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli push --encrypt --recipient <age-recipient> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli status --require-encrypted --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli pull --require-encrypted --identity-file <age-identity> --registry-dir <target-registry> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli repair --require-encrypted --identity-file <age-identity> --json
```

Object-storage plaintext migration uses the same admin CLI. The target prefix
must be fresh; dry-run reads the plaintext manifest and reports managed objects
without uploading or deleting:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin migrate-object-to-encrypted --object-prefix <old-plaintext-prefix> --target-object-prefix <new-encrypted-prefix> --registry-dir <registry> --dry-run --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin migrate-object-to-encrypted --object-prefix <old-plaintext-prefix> --target-object-prefix <new-encrypted-prefix> --registry-dir <registry> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli repair --require-encrypted --object-prefix <new-encrypted-prefix> --identity-file <age-identity> --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin cleanup-object-plaintext --object-prefix <old-plaintext-prefix> --dry-run --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.encrypted.admin cleanup-object-plaintext --object-prefix <old-plaintext-prefix> --confirm --verified-encrypted-target --json
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
