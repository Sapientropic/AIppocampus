# Provider Entrypoint Inventory

Last audited: 2026-05-31.

This inventory classifies the remaining runtime surfaces that mention Codex raw
rollouts or Codex home helpers. It is the companion record for issue #122. The
goal is not to erase the Codex provider; it is to keep public surfaces honest
about whether they are provider-aware, clean-source/registry-only, or Codex-only
audit/host integration paths.

## Classification

| Surface | Classification | Boundary |
| --- | --- | --- |
| `aippocampus_runtime/core.py` plus `aippocampuslib.py` compatibility shim | Shared compatibility helpers | Owns legacy Codex raw-rollout helpers and provider-neutral registry storage resolution. New public raw-source logic should use `conversation_sources/` instead of adding more helpers here. |
| `conversation_sources/codex.py` | Codex provider implementation | The only provider module that should know Codex `sessions/` and `archived_sessions/` layout. |
| `onboard.py` | Provider-aware public entrypoint | Accepts `--provider codex\|claude-code\|generic-jsonl`; `auto` remains conservative and lists other providers separately. |
| `build_clean_source.py` and `aippocampus_runtime/source/clean_source.py` | Provider-aware public entrypoint | Accepts `--provider`; Codex raw rollout discovery is used only for the Codex provider or explicit `--rollout`. The top-level script is a compatibility shim over the package owner. |
| `build_index.py` | Provider-aware public entrypoint | Accepts `--provider`; indexes provider-normalized visible messages. |
| `aippocampus_runtime/registry/api.py` plus `registry.py` compatibility shim | Provider-aware registry entrypoint | CLI accepts `--provider`; in-process `provider or codex_provider(...)` fallback is legacy compatibility only. |
| `aippocampus_runtime/mcp/server.py` plus `aippocampus_mcp_server.py` compatibility shim | MCP over clean source/registry, with provider-aware registration | `search_memory`, `get_turn_context`, `list_threads`, `sync_status`, and `memory_health` consume clean source/registry. `register_thread` accepts `provider`. `latest_reply` prefers clean source and falls back to raw Codex only when no clean-source final answer exists. |
| `sync_vault.py` | Provider-aware projection | Accepts `--provider`; vault output remains a local projection, not a provider truth source. |
| `aippocampus_runtime/health.py` plus `aippocampus_health.py` compatibility shim | Codex-current-thread health plus registry artifact health | Still uses raw Codex rollout discovery for current live thread freshness. Treat it as Codex host health until a provider-neutral health surface exists. It now reports active AIppocampus registry storage separately. |
| `build_segments.py` | Codex-current-thread maintenance | Uses current Codex rollout when `--rollout` is omitted. Use explicit rollout/output paths for non-Codex maintenance until this is migrated. |
| `prepare_graphify_corpus.py` | Codex-current-thread maintenance | Uses current Codex rollout to find the matching default index. Non-Codex callers should pass explicit artifact paths or use registry-derived inputs. |
| `checkpoint.py` | Codex-current-thread maintenance | Checkpoint state is a generated AIppocampus artifact; current default still follows the current Codex thread store. |
| `subconscious_scheduler.py` | Registry maintenance | Reads the AIppocampus registry. Its default root is provider-neutral registry storage, with legacy Codex fallback. |
| `aippocampus_prompt_hook.py` | Codex host integration | UserPromptSubmit hook glue. It may write AIppocampus debug logs, but it is not a generic host hook installer. |
| `aippocampus_lifecycle_hook.py` | Codex host integration | Codex lifecycle hook glue. Maintenance state/logs use AIppocampus registry storage; hook events remain Codex-specific. |
| `install_aippocampus_prompt_hook.py` | Codex host integration | Mutates Codex hook config only after explicit operator command. |
| `install_aippocampus_lifecycle_hook.py` | Codex host integration | Mutates Codex hook config only after explicit operator command. |
| `diagnose_hooks.py` | Codex host diagnostic | Inspects Codex hook config; not a provider-neutral health tool. |
| `locate_rollout.py` | Codex-only raw audit/debug tool | Finds current Codex rollout JSONL. Do not present as general AI-agent transcript discovery. |
| `search_rollout.py` | Codex-only raw audit/debug tool | Searches raw Codex rollout text. Clean-source search is the general recall surface. |
| `aippocampus_runtime/source/latest_reply.py` plus `latest_reply.py` compatibility shim | Codex-only raw audit/debug fallback | Reads final answers from raw Codex rollout. MCP prefers clean-source final answers first. |
| `rollout_size_audit.py` | Codex-only raw audit/debug tool | Audits raw Codex rollout size/path behavior. |
| `cold_archive.py` | Codex-only raw audit/archive tool | Optional raw rollout archive path; not daily recall. |
| `retention_report.py` | Codex-only raw audit/report tool | Uses raw Codex rollout unless an explicit rollout is supplied. |
| `export_bundle.py` | Codex-current-thread export helper | Exports generated artifacts for a current Codex thread unless explicit paths are supplied. |

## Guardrail

Raw Codex helpers should either stay in this inventory or move behind
provider-normalized `conversation_sources/` inputs. If `rg` for
`locate_rollout(`, `iter_rollouts(`, `codex_home(`, or
`provider or codex_provider` finds a new runtime call site, update this file and
add or adjust tests for the changed public boundary.
