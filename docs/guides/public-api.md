# Public API And Stability

This document is the canonical public API and stability boundary for
AIppocampus. It explains which repository surfaces are intended for users,
agents, plugin hosts, and scripts to depend on.

It complements [public-core-boundary.md](public-core-boundary.md), which owns
licensing, adapter architecture, and minimal schema contracts. Do not mirror
the schema details here.

## Stability Model

AIppocampus uses additive public contracts:

- Existing documented command names, documented flags, MCP tool names, required
  MCP input fields, and published schema meanings should not silently change.
- New optional flags, optional MCP input fields, JSON fields, labels, metrics,
  warnings, and diagnostics may be added.
- Consumers should tolerate unknown JSON fields and unknown warning codes.
- Debug, provenance, private local path, and implementation-detail fields are
  not stable unless this document or a linked contract explicitly says so.

When a behavior is only supported by tests, smoke tools, or an issue comment, it
is evidence for the current implementation, not a public API promise.

## Supported Public Surfaces

The supported public surfaces are:

- The installable skill package under `skills/aippocampus/`.
- The CLI entrypoints documented in `README.md`,
  [install-guide.md](install-guide.md), and `skills/aippocampus/SKILL.md`.
- The MCP server tool names and input schemas exposed by
  `skills/aippocampus/scripts/aippocampus_mcp_server.py --list-tools`.
- The source-event, clean-source chunk, source-ref, and import-manifest schemas
  documented in [public-core-boundary.md](public-core-boundary.md).
- The Codex plugin package source under `plugins/aippocampus/`, including its
  MCP config and packaged skill surface.
- The documented local-folder, HTTP object-storage, and encrypted sync commands.
- The repository-level verification commands documented in `README.md` and
  [install-guide.md](install-guide.md).

The public API does not include every helper module or every script under
`skills/aippocampus/scripts/`.

## CLI Contract

The CLI contract applies to documented operator commands, especially:

- `aippocampus health|search|onboard|mcp|sync|object-sync|hooks`
- `aippocampus_health.py`
- `search_clean_source.py`
- `latest_reply.py` as a Codex raw-rollout audit compatibility command
- `onboard.py --provider codex|claude-code|generic-jsonl|auto`
- `onboard_codex.py`
- `aippocampus_mcp_server.py --list-tools`
- `sync_bundle.py status|push|pull|repair`
- `sync_object_storage.py status|push|pull|repair`
- `encrypted_sync_admin.py key|migrate-to-encrypted|cleanup-plaintext|migrate-object-to-encrypted|cleanup-object-plaintext`
- `install_aippocampus_prompt_hook.py status|install|uninstall`
- `install_aippocampus_lifecycle_hook.py status|install|uninstall`
- `plugins/aippocampus/build_plugin_package.py`
- documented plugin smoke commands

For these commands:

- Documented command names and documented flags are stable unless release notes
  say otherwise.
- `--json` output, when documented, is intended for automation.
- JSON objects may gain fields. Consumers should key off documented fields and
  tolerate extra keys.
- Human-readable text is not a stable parse target.
- Exit code `0` means the command completed successfully. Non-zero means invalid
  arguments, missing prerequisites, failed validation, failed smoke, or another
  command-specific hard failure.
- Exact non-zero exit-code numbers are not stable yet. Use structured JSON error
  payloads or documented status fields where available.
- The `aippocampus` facade is a thin Python dispatcher. It resolves commands to
  packaged entrypoint mains and preserves stdout/stderr, JSON shape, and return
  code rather than wrapping runtime output in a second envelope.

The Python facade is the current packaging step. Standalone Python-free binaries
are not part of the public claim until the follow-up
[standalone binary packaging plan](../planning/standalone-binary-packaging.md)
has produced artifacts and verified the target platform matrix.

Repo-maintenance commands under `tools/aippocampus/` and
`benchmarks/aippocampus/` are public development aids, not end-user runtime APIs,
unless a public doc explicitly promotes a command.

Remaining Codex raw-rollout/default-home script surfaces are classified in
[provider-entrypoint-inventory.md](../architecture/provider-entrypoint-inventory.md).
General recall should use clean-source search, provider-aware onboarding, MCP
tools, or registry paths; raw Codex audit helpers are not generic
cross-agent-provider APIs.

## MCP Contract

The current MCP tool catalog is read-mostly and intentionally small. The public
tool names are:

- `search_memory`
- `latest_reply`
- `get_turn_context`
- `list_threads`
- `register_thread`
- `sync_status`
- `memory_health`

For these tools:

- Tool names and required input fields are stable.
- Optional input fields may be added.
- Output fields may be added.
- Tool errors use JSON payloads in MCP `content` text as documented in
  [install-guide.md](install-guide.md).
- `unsupported_mutation` is intentional. The MCP surface should not grow broad
  write APIs just to prove integration.

`register_thread` is an explicit control-plane operation. It is not a general
memory-write API.

MCP JSON output defaults to public-safe local-path redaction for tool results
that can be forwarded through host agents. Callers that are acting as local
operators may pass `include_private_paths: true` where documented by the tool
schema to recover local locators for repair/debug work.

## Provider Identity And Privacy

Provider-neutral identity uses stable join keys such as `thread_key`,
`source_id`, `source_ref`, `turn_id`, `message_id`, and content hashes. Local
absolute paths are private locators for audit, repair, and generated artifact
lookup; they are not identity and should not be forwarded as public evidence.

Clean-source manifests may retain private `cwd`, `source_transcript`, and output
paths for local operators. Public/MCP/sync projections should redact or bundle-
relativize those paths while preserving source-backed ids and source refs.

## Generic JSONL Import

`generic-jsonl` is the public import path for hosts that do not yet have a
bespoke provider. Each JSONL row must describe one visible message:

```json
{
  "session_id": "stable-public-or-local-session-id",
  "timestamp": "2026-05-30T05:00:00Z",
  "cwd": "optional local project locator",
  "role": "user",
  "text": "visible message text",
  "turn_id": "optional stable turn id",
  "source_ref": "optional host source pointer",
  "provider_metadata": {"provider": "example-agent"}
}
```

Required fields are `session_id`, `role`, and `text`. `role` must be `user` or
`assistant` for clean source; `system` rows are ignored, and ambiguous or orphan
assistant rows are rejected with actionable validation errors. Markdown import
is intentionally not claimed until role boundaries and stable source refs can be
preserved.

Generic JSONL validation failures expose a machine-readable code, source line,
message, and details, so import callers can report the exact malformed row
without guessing from prose.

## JSON And Schema Contracts

The stable public data schemas are owned by
[public-core-boundary.md](public-core-boundary.md):

- Canonical source event
- Clean-source chunk
- Source ref
- Import manifest

Generated indexes, registry rows, sidecar metrics, cognitive-map artifacts,
subconscious job rows, and debug/provenance envelopes are not stable public
schemas unless a future document promotes a subset.

Consumers should prefer source refs and clean-source artifacts over generated
summary, label, or model-organized output when they need evidence.

## Environment Variables

Public environment variables use the `AIPPOCAMPUS_*` prefix. Important supported
groups are:

- Storage and discovery: `AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME`,
  legacy `THREAD_MEMORY_REGISTRY_DIR`, and legacy `CODEX_HOME`.
- Vault projection: `AIPPOCAMPUS_VAULT`, `AIPPOCAMPUS_STYLE_SOURCE`,
  `AIPPOCAMPUS_SCRIPT_SOURCE`, `AIPPOCAMPUS_SITE_MARK`,
  `AIPPOCAMPUS_SITE_TITLE`.
- Object storage sync: `AIPPOCAMPUS_OBJECT_STORE_URL`,
  `AIPPOCAMPUS_OBJECT_PREFIX`, `AIPPOCAMPUS_OBJECT_STORE_TOKEN`,
  `AIPPOCAMPUS_OBJECT_PROVIDER`, `AIPPOCAMPUS_OBJECT_BUCKET`,
  `AIPPOCAMPUS_OBJECT_REGION`, `AIPPOCAMPUS_OBJECT_ACCOUNT_ID`,
  `AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID`,
  `AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY`,
  `AIPPOCAMPUS_OBJECT_SESSION_TOKEN`.
- Encrypted sync: `AIPPOCAMPUS_AGE_BIN`.
- Hook budgets and semantic recall: `AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS`,
  `AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS`,
  `AIPPOCAMPUS_SEMANTIC_GATE`, and documented warm-recall tuning variables.
- Optional external models: `AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL`,
  `AIPPOCAMPUS_DEEPSEEK_PRO_MODEL`, `AIPPOCAMPUS_DEEPSEEK_BASE_URL`, and
  `DEEPSEEK_API_KEY`.
- Optional provider-portability smoke/config: `AIPPOCAMPUS_OPENAI_COMPAT_ROUTE`,
  `AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER`, `AIPPOCAMPUS_OPENAI_COMPAT_MODEL`,
  `AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL`,
  `AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV`,
  `AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY`,
  `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON`,
  `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID`,
  `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING`, and
  `AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND`.

Legacy `DEEPSEEK_*` model override variables may remain as compatibility
fallbacks. New public configuration should prefer `AIPPOCAMPUS_*`.

Generated registry storage resolves in this order:

1. `AIPPOCAMPUS_REGISTRY_DIR`: exact registry root.
2. `THREAD_MEMORY_REGISTRY_DIR`: legacy exact registry root.
3. `AIPPOCAMPUS_HOME/registry`: provider-neutral AIppocampus home.
4. `CODEX_HOME/aippocampus-registry`, or the default Codex home path if no
   AIppocampus storage variable is set: legacy compatibility fallback.

AIppocampus never migrates or deletes an existing registry automatically.
Codex skill installation and Codex hook configuration may still use
`CODEX_HOME`; generated memory storage should prefer the `AIPPOCAMPUS_*`
variables for new non-Codex setups.

Never log or publish environment variable values that contain credentials,
tokens, cookies, local private paths, or private memory locations.

## Python Import Policy

AIppocampus does not currently publish a stable Python package API. Runtime code
under `skills/aippocampus/scripts/` remains script-first.

Downstream callers should prefer:

- documented CLI commands,
- the MCP surface,
- documented public schemas, or
- adapter/import-manifest files.

Repo-owned docs, smoke, and benchmark tools use a transitional checkout-only
bootstrap in `tools/aippocampus/repo_paths.py`. The small `_paths.py` files under
`tools/aippocampus/docs/`, `tools/aippocampus/smoke/`, and
`benchmarks/aippocampus/` are compatibility wrappers around that single helper.
They keep direct script execution working from an uninstalled checkout; they are
not downstream APIs.

Direct imports from helper modules may keep working in this repository, but they
are not a compatibility promise.

## Internal Or Unstable Surfaces

These are internal, experimental, or best-effort unless promoted elsewhere:

- Undocumented helper functions and modules.
- Repo-local `repo_paths.py` / `_paths.py` checkout import shims.
- Raw rollout envelopes and host-specific JSONL fields.
- Generated SQLite, FTS, graph, semantic, cognitive-map, and benchmark cache
  files.
- Internal retrieval helpers under `aippocampus_runtime.recall`, with flat
  compatibility shims such as `retrieval_score_fusion.py`; their outputs are
  policy diagnostics and ranking hints, not stable public schemas or source
  truth.
- Debug output, trace fields, timing metrics, and local absolute paths.
- Research notes under `docs/research/`.
- External provider pricing, rate limits, model IDs, and cache behavior.
- Hosted, managed, enterprise, or commercial service behavior.

Private memory artifacts are never public API. Raw rollouts, clean-source
exports, registry data, sync bundles, vault exports, generated indexes, and
thread anchors remain private user data unless their owner intentionally
publishes them.
