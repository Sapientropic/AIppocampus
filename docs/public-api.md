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

- `aippocampus_health.py`
- `search_clean_source.py`
- `latest_reply.py`
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

Repo-maintenance commands under `tools/aippocampus/` and
`benchmarks/aippocampus/` are public development aids, not end-user runtime APIs,
unless a public doc explicitly promotes a command.

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

- Storage and discovery: `CODEX_HOME`, `AIPPOCAMPUS_REGISTRY_DIR`.
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
- Debug output, trace fields, timing metrics, and local absolute paths.
- Research notes under `docs/research/`.
- External provider pricing, rate limits, model IDs, and cache behavior.
- Hosted, managed, enterprise, or commercial service behavior.

Private memory artifacts are never public API. Raw rollouts, clean-source
exports, registry data, sync bundles, vault exports, generated indexes, and
thread anchors remain private user data unless their owner intentionally
publishes them.
