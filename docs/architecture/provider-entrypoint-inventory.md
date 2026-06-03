# Provider Entrypoint Inventory

Last audited: 2026-06-02.

This inventory classifies the remaining runtime surfaces that mention Codex raw
rollouts, Codex home helpers, or host hook configuration. It is the companion
record for issue #122 and issue #501. The goal is not to erase the Codex
provider; it is to keep public surfaces honest about whether they are
provider-aware, clean-source/registry-only, or Codex-only audit/host integration
paths.

## Classification

| Surface | Classification | Boundary |
| --- | --- | --- |
| `aippocampus_runtime/core.py` plus `aippocampuslib.py` compatibility shim | Shared compatibility helpers | Re-exports legacy Codex rollout parser helpers from `aippocampus_runtime/source/rollout.py` and registry path helpers from `aippocampus_runtime/registry/paths.py`. Text compaction, external-model safety/credential transport, CLI error payloads, and anchor graph helpers are re-exported for compatibility only; new code should import `aippocampus_runtime.text`, `aippocampus_runtime.safety`, `aippocampus_runtime.cli.errors`, `aippocampus_runtime.anchor_graph`, or `aippocampus_runtime.registry.paths` directly. New public raw-source logic should use `conversation_sources/` or source package owners instead of adding more helpers here. |
| `aippocampus_runtime/registry/paths.py` | Provider-neutral registry storage helper | Owns `AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, and legacy Codex registry fallback resolution without importing the Codex raw-source helpers from `core.py`. |
| `conversation_sources/codex.py` | Codex provider implementation | The only provider module that should know Codex `sessions/` and `archived_sessions/` layout. |
| `aippocampus_runtime/source/rollout.py` | Codex rollout parser owner | Parses Codex event/response JSONL into the legacy normalized message/turn schema for audit, clean-source, and index consumers. It does not discover rollout files or decide artifact storage; `core.py` and `aippocampuslib.py` only re-export these helpers for compatibility. |
| `aippocampus_runtime/onboarding/facade.py` plus `onboard.py` compatibility shim | Provider-aware public entrypoint | Accepts `--provider codex\|claude-code\|generic-jsonl`; `auto` remains conservative and lists other providers separately. |
| `build_clean_source.py` and `aippocampus_runtime/source/clean_source.py` | Provider-aware public entrypoint | Accepts `--provider`; Codex raw rollout discovery is used only for the Codex provider or explicit `--rollout`. Runtime manifests prefer provider-neutral `source_artifact` / `source_transcript*` fields; `source_rollout*` remains a legacy compatibility alias, not the current contract. The top-level script is a compatibility shim over the package owner. |
| `aippocampus_runtime/recall/index_builder.py` plus `build_index.py` compatibility shim | Provider-aware public entrypoint | Accepts `--provider`; indexes provider-normalized visible messages. The default Codex rollout discovery applies only when `--rollout` is omitted. |
| `aippocampus_runtime/registry/api.py` plus `registry.py` compatibility shim | Provider-aware registry entrypoint | CLI accepts `--provider`; `register-source --provider/--format ... --input ...` is the explicit provider-neutral transcript import/register path, while `register-rollout` keeps Codex-era naming for compatibility. In-process `provider or codex_provider(...)` fallback is legacy compatibility only. |
| `aippocampus_runtime/registry/source_registration.py` | Provider-aware explicit source registration | Owns `register-source` / explicit transcript registration helpers. Generic JSONL gets an input-path-backed provider; non-generic explicit providers use their existing provider implementations. The `provider or codex_provider(...)` fallback remains only for legacy in-process callers of `register_rollout_thread`. |
| `aippocampus_runtime/mcp/server.py` plus `aippocampus_mcp_server.py` compatibility shim | MCP over clean source/registry, with provider-aware registration | `search_memory`, `recall_context`, `recall_deepen`, `get_turn_context`, `list_threads`, `sync_status`, and `memory_health` consume clean source/registry. `register_thread` accepts `provider` as a control-plane registry operation, not a general memory-write API; concurrent registry writers use the registry writer lease and report `registry_writer_busy` when contention is retryable. Unsupported write-like tool names return `unsupported_mutation`. `latest_reply` prefers clean source and falls back to raw Codex only when no clean-source final answer exists. |
| `aippocampus_runtime/vault/sync.py` plus `sync_vault.py` compatibility shim | Provider-aware projection | Accepts `--provider`; vault output remains a local projection, not a provider truth source. |
| `aippocampus_runtime/health.py` plus `aippocampus_health.py` compatibility shim | Codex-current-thread health plus registry artifact health | Still uses raw Codex rollout discovery for current live thread freshness. Treat it as Codex host health until a provider-neutral health surface exists. It now reports active AIppocampus registry storage separately. |
| `aippocampus_runtime/recall/segment_builder.py` plus `build_segments.py` compatibility shim | Codex-current-thread maintenance | Uses current Codex rollout when `--rollout` is omitted. Use explicit rollout/output paths for non-Codex maintenance until this is migrated. |
| `aippocampus_runtime/ops/graphify_corpus.py` plus `prepare_graphify_corpus.py` compatibility shim | Codex-current-thread maintenance | Uses current Codex rollout to find the matching default index. Non-Codex callers should pass explicit artifact paths or use registry-derived inputs. |
| `aippocampus_runtime/artifacts/checkpoint.py` plus `checkpoint.py` compatibility shim | Codex-current-thread maintenance | Checkpoint state is a generated AIppocampus artifact; current default still follows the current Codex thread store. |
| `subconscious_scheduler.py` | Registry maintenance | Reads the AIppocampus registry. Its default root is provider-neutral registry storage, with legacy Codex fallback. |
| `aippocampus_runtime/hooks/prompt.py` plus `aippocampus_prompt_hook.py` compatibility shim | Codex host integration | UserPromptSubmit hook glue. It may write AIppocampus debug logs, but it is not a generic host hook installer. |
| `aippocampus_runtime/hooks/lifecycle.py` plus `aippocampus_lifecycle_hook.py` compatibility shim | Codex host integration | Codex lifecycle hook glue. Maintenance state/logs use AIppocampus registry storage; hook events remain Codex-specific. |
| `aippocampus_runtime/hooks/install_prompt.py` plus `install_aippocampus_prompt_hook.py` compatibility shim | Codex host integration | Mutates Codex hook config only after explicit operator command. |
| `aippocampus_runtime/hooks/install_lifecycle.py` plus `install_aippocampus_lifecycle_hook.py` compatibility shim | Codex host integration | Mutates Codex hook config only after explicit operator command. |
| `aippocampus_runtime/hooks/diagnose.py` plus `diagnose_hooks.py` compatibility shim | Codex host diagnostic | Inspects Codex hook config; not a provider-neutral health tool. |
| `aippocampus_runtime/source/locate_rollout.py` plus `locate_rollout.py` compatibility shim | Codex-only raw audit/debug tool | Finds current Codex rollout JSONL. Do not present as general AI-agent transcript discovery. |
| `aippocampus_runtime/recall/rollout_search.py` plus `search_rollout.py` compatibility shim | Codex-only raw audit/debug tool | Searches raw Codex rollout text. Clean-source search is the general recall surface. |
| `aippocampus_runtime/source/latest_reply.py` plus `latest_reply.py` compatibility shim | Codex-only raw audit/debug fallback | Reads final answers from raw Codex rollout. MCP prefers clean-source final answers first. |
| `aippocampus_runtime/ops/rollout_size_audit.py` plus `rollout_size_audit.py` compatibility shim | Codex-only raw audit/debug tool | Audits raw Codex rollout size/path behavior. |
| `aippocampus_runtime/ops/cold_archive.py` plus `cold_archive.py` compatibility shim | Codex-only raw audit/archive tool | Optional raw rollout archive path; not daily recall. |
| `aippocampus_runtime/ops/retention_report.py` plus `retention_report.py` compatibility shim | Codex-only raw audit/report tool | Uses raw Codex rollout unless an explicit rollout is supplied. |
| `aippocampus_runtime/ops/storage_governance.py` | Registry-first storage governance facade with Codex-current-thread retention discovery | `aippocampus storage gc --dry-run` can generate capacity evidence from registry/manifests without reading message bodies. `--apply --class rebuildable` is limited to path-level retention-report eviction of the main SQLite cache through package helper `storage_eviction.py`. It uses Codex current-thread discovery only to find an already-written default `retention_report.json`; operators can pass `--retention-report` for explicit/non-Codex evidence. No top-level compatibility shim is added. |
| `aippocampus_runtime/artifacts/export_bundle.py` plus `export_bundle.py` compatibility shim | Codex-current-thread export helper | Exports generated artifacts for a current Codex thread unless explicit paths are supplied. The package owner calls the packaged index builder in-process; the top-level script is compatibility only. |

## Host Integration Matrix

Conversation-provider support means AIppocampus can normalize visible transcript
source into clean source. Host hook support means AIppocampus can install,
diagnose, or run a host-specific hook contract. These are separate claims.

| Host/provider | Conversation provider | Clean-source, registry, MCP surfaces | Host hook handlers | configuration-mutating installers | Host diagnostics | Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `codex` | Yes: Codex rollout provider. | Yes: clean source, registry, MCP, onboarding, and current-thread maintenance paths. | Yes: `aippocampus_runtime/hooks/prompt.py` and `aippocampus_runtime/hooks/lifecycle.py` implement Codex hook handlers. | Yes: `install_prompt.py` and `install_lifecycle.py` mutate Codex `hooks.json` after explicit operator command. | Yes: `diagnose.py` inspects Codex `hooks.json` and emulates Codex hook stdin. | Codex hook install/status/uninstall remains opt-in Codex host integration, not a provider-neutral AIppocampus install. |
| `claude-code` | Yes: Claude Code transcript parser and explicit onboarding. | Yes: clean-source registration and MCP/project-skill surfaces. | No shipped AIppocampus Claude Code hook handler. | No shipped AIppocampus Claude Code hook installer. | MCP host smokes only; no hook diagnostic claim. | Claude Code hook support: not yet claimable until a dedicated installer/status/privacy/smoke targets the official Claude Code hooks contract. |
| `generic-jsonl` | Yes: explicit visible-message import provider. | Yes: clean-source registration/import surfaces. | No host hook handler. | No host hook installer. | Import validation only. | Generic import proves transcript ingestion, not host automation. |

## Guardrail

Raw Codex helpers should either stay in this inventory or move behind
provider-normalized `conversation_sources/` inputs. If `rg` for
`locate_rollout(`, `iter_rollouts(`, `codex_home(`, or
`provider or codex_provider` finds a new runtime call site, update this file and
add or adjust tests for the changed public boundary.
