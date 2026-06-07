# Provider Entrypoint Inventory

Role: inventory.

Last audited: 2026-06-05.

This inventory classifies runtime surfaces that mention Codex raw rollouts,
Codex home helpers, or host hook configuration. The goal is not to erase the
Codex provider; it is to keep public surfaces honest about whether they are
provider-aware, clean-source/registry-only, or Codex-only audit/host integration
paths.

Flat top-level scripts are gone. Surfaces below are package owners or public
facade commands.

## Classification

| Surface | Classification | Boundary |
| --- | --- | --- |
| `aippocampus_runtime/core.py` | Shared legacy helper facade | Re-exports selected legacy helper names for trusted in-process callers. New code should import direct owners such as `aippocampus_runtime.text`, `aippocampus_runtime.safety`, `aippocampus_runtime.cli.errors`, `aippocampus_runtime.anchor_graph`, or `aippocampus_runtime.registry.paths`. |
| `aippocampus_runtime/registry/paths.py` | Provider-neutral registry storage helper | Owns `AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, and legacy Codex registry fallback resolution without importing Codex raw-source helpers from `core.py`. |
| `conversation_sources/codex.py` | Codex provider implementation | The only provider module that should know Codex `sessions/` and `archived_sessions/` layout. |
| `conversation_sources/claude_code.py` | Claude Code provider implementation | Parses visible Claude Code transcript rows for explicit onboarding/import; does not imply hook support. |
| `conversation_sources/generic_jsonl.py` | Provider-neutral import implementation | Validates explicit visible-message JSONL imports. |
| `aippocampus_runtime/source/rollout.py` | Codex rollout parser owner | Parses Codex event/response JSONL into the legacy normalized message/turn schema for audit, clean-source, and index consumers. It does not discover rollout files or decide artifact storage. |
| `aippocampus_runtime/onboarding/facade.py` | Provider-aware public onboarding facade | Accepts `--provider codex\|claude-code\|generic-jsonl`; `auto` remains conservative and lists other providers separately. |
| `aippocampus_runtime/onboarding/codex.py` | Codex/default onboarding runner | Registers local Codex sessions, builds clean source/indexes, and refreshes sidecars. |
| `aippocampus_runtime/source/clean_source.py` | Provider-aware clean-source builder | Accepts `--provider`; Codex raw rollout discovery is used only for the Codex provider or explicit `--rollout`. Runtime manifests prefer provider-neutral `source_artifact` / `source_transcript*` fields; `source_rollout*` remains a legacy alias. |
| `aippocampus_runtime/source/agent_self_note_cli.py` | Current-thread self-note facade | `self-note append --current-thread` may locate the current Codex rollout/thread or use an explicit current-thread env handle to attach a route. Public output exposes only a compact route handle; raw rollout paths and raw thread ids stay out of the foreground JSON. |
| `aippocampus_runtime/recall/index_builder.py` | Provider-aware index builder | Accepts `--provider`; indexes provider-normalized visible messages. The default Codex rollout discovery applies only when `--rollout` is omitted. |
| `aippocampus_runtime/registry/api.py` | Provider-aware registry entrypoint | CLI accepts `--provider`; `register-source --provider/--format ... --input ...` is the explicit provider-neutral transcript import/register path, while `register-rollout` keeps Codex-era naming for compatibility. |
| `aippocampus_runtime/registry/source_registration.py` | Provider-aware explicit source registration | Owns `register-source` helpers. Generic JSONL gets an input-path-backed provider; non-generic explicit providers use their existing provider implementations. The `provider or codex_provider(...)` fallback remains only for legacy in-process callers of `register_rollout_thread`. |
| `aippocampus_runtime/mcp/server.py` | MCP over clean source/registry, with provider-aware registration | `search_memory`, `recall_context`, `recall_deepen`, `get_turn_context`, `list_threads`, `sync_status`, and `memory_health` consume clean source/registry. `register_thread` accepts `provider` as a control-plane registry operation, not a general memory-write API. |
| `aippocampus_runtime/vault/sync.py` | Provider-aware projection | Accepts `--provider`; vault output remains a local projection, not a provider truth source. |
| `aippocampus_runtime/health.py` | Codex-current-thread health plus registry artifact health | Still uses raw Codex rollout discovery for current live thread freshness. Treat it as Codex host health until a provider-neutral health surface exists. |
| `aippocampus_runtime/source/emergency_snapshot.py` | Codex-current-thread compaction bridge | Writes a bounded private PreCompact snapshot for the current Codex rollout when clean source may not have caught up. It is a lifecycle recovery bridge, not provider-neutral transcript ingestion or clean-source evidence. |
| `aippocampus_runtime/recall/segment_builder.py` | Codex-current-thread maintenance | Uses current Codex rollout when `--rollout` is omitted. Use explicit rollout/output paths for non-Codex maintenance until this is migrated. |
| `aippocampus_runtime/ops/graphify_corpus.py` | Codex-current-thread maintenance | Uses current Codex rollout to find the matching default index. Non-Codex callers should pass explicit artifact paths or use registry-derived inputs. |
| `aippocampus_runtime/artifacts/checkpoint.py` | Codex-current-thread maintenance | Checkpoint state is a generated AIppocampus artifact; current default still follows the current Codex thread store. |
| `aippocampus_runtime/subconscious/scheduler.py` | Registry maintenance | Reads the AIppocampus registry. Its default root is provider-neutral registry storage, with legacy Codex fallback. |
| `aippocampus_runtime/hooks/prompt.py` | Codex host integration | UserPromptSubmit hook glue. It may write AIppocampus debug logs, but it is not a generic host hook installer. |
| `aippocampus_runtime/hooks/lifecycle.py` | Codex host integration | Codex lifecycle hook glue. Maintenance state/logs use AIppocampus registry storage; hook events remain Codex-specific. |
| `aippocampus_runtime/hooks/install_prompt.py` | Codex host integration | Mutates Codex hook config only after explicit operator command. |
| `aippocampus_runtime/hooks/install_lifecycle.py` | Codex host integration | Mutates Codex hook config only after explicit operator command. |
| `aippocampus_runtime/hooks/diagnose.py` | Codex host diagnostic | Inspects Codex hook config; not a provider-neutral health tool. |
| `aippocampus_runtime/source/locate_rollout.py` | Codex-only raw audit/debug tool | Finds current Codex rollout JSONL. Do not present as general AI-agent transcript discovery. |
| `aippocampus_runtime/recall/rollout_search.py` | Codex-only raw audit/debug tool | Searches raw Codex rollout text. Clean-source search is the general recall surface. |
| `aippocampus_runtime/source/latest_reply.py` | Codex-only raw audit/debug fallback | Reads final answers from raw Codex rollout. MCP prefers clean-source final answers first. |
| `aippocampus_runtime/ops/rollout_size_audit.py` | Codex-only raw audit/debug tool | Audits raw Codex rollout size/path behavior. |
| `aippocampus_runtime/ops/cold_archive.py` | Codex-only raw audit/archive tool | Optional raw rollout archive path; not daily recall. |
| `aippocampus_runtime/ops/retention_report.py` | Codex-only raw audit/report tool | Uses raw Codex rollout unless an explicit rollout is supplied. |
| `aippocampus_runtime/ops/storage_governance.py` | Registry-first storage governance facade with Codex-current-thread retention discovery | `aippocampus storage gc --dry-run` can generate capacity evidence from registry/manifests without reading message bodies. `--apply --class rebuildable` is limited to path-level retention-report eviction of the main SQLite cache through package helper `storage_eviction.py`. |
| `aippocampus_runtime/update/cli.py` | Codex-aware local update facade | `aippocampus update status/plan/apply` compares the repo skill, installed Codex skill copy, plugin staging, MCP config, hook config, and provider-key visibility. It may explicitly sync the installable skill, rebuild the repo-local plugin package, and install AIppocampus-owned Codex hooks; it does not mutate private memory artifacts or read API-key values. |
| `aippocampus_runtime/ops/provider_doctor.py` | Operator provider visibility and credential-source diagnostic | Normal `aippocampus doctor provider` is presence-only and reads no key values. The explicit `--discover-credential-sources` path may inspect the current process env and user-specified `.env` files to report redacted candidate shape and optional validation status; it does not scan by default, read OS credential stores, install hook wrappers, or change runtime provider visibility. |
| `aippocampus_runtime/ops/provider_credentials.py` | Explicit credential-source helper for provider doctor | Parses only user-specified `.env` files or current-process env under the provider doctor discovery flag. It owns redaction, optional HTTPS/loopback validation, and bridge-plan diagnostics; it is not a runtime credential loader or secret-store adapter. |
| `aippocampus_runtime/ops/provider_key_bridge.py` and `aippocampus_runtime/hooks/provider_bridge.py` | Explicit provider-key bridge owner | `aippocampus onboard provider-key --plan|--apply|--undo --target codex-hooks` can write an AIppocampus-owned wrapper and manifest, then install Codex hook commands that call the wrapper. The manifest may contain explicit private source locators, but never key values. The ordinary prompt/lifecycle hooks remain process-env consumers; the wrapper is the only opt-in runtime path that reads a configured `.env` or OS credential-store source before delegating to those hooks. |
| `aippocampus_runtime/cognitive_worker_mode.py` | Provider-neutral background cognition mode resolver | Resolves `external_model`, `agent_fallback`, `deterministic_only`, or `off` from provider-key visibility and explicit `AIPPOCAMPUS_*` mode flags. It never reads key values, starts workers, or changes source truth; scheduler/doctor surfaces consume its public-safe status. |
| `aippocampus_runtime/artifacts/export_bundle.py` | Codex-current-thread export helper | Exports generated artifacts for a current Codex thread unless explicit paths are supplied. |

## Host Integration Matrix

Conversation-provider support means AIppocampus can normalize visible transcript
source into clean source. Host hook support means AIppocampus can install,
diagnose, or run a host-specific hook contract. These are separate claims.
The matrix calls out configuration-mutating installers separately from hook
handlers.

| Host/provider | Conversation provider | Clean-source, registry, MCP surfaces | Host hook handlers | Configuration-mutating installers | Host diagnostics | Boundary |
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
