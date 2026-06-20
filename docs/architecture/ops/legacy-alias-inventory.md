# Legacy Alias Inventory

Role: inventory.

Last audited: 2026-06-21.

This is the canonical inventory for remaining host/path compatibility and
retired migration-only aliases. Public setup docs must use `AIPPOCAMPUS_*`
names and package-owner/facade entrypoints.

Migration-only environment fallbacks were removed on 2026-06-21. The old names
remain visible here only so docs-health can catch regressions and explain the
sunset; normal runtime resolution no longer reads them.

## Runtime Diagnostics

Runtime diagnostics must report remaining path/host alias names and active
status without printing values or local paths.

- `aippocampus health --json` reports `legacy_aliases` for remaining registry
  path fallback and project-local `.aippocampus/` output when it is part of the
  resolved diagnostic paths.
- `aippocampus doctor provider --json` no longer reports migration-only
  provider-native env fallbacks; use canonical `AIPPOCAMPUS_DEEPSEEK_*` names or
  explicit custom route env configuration.
- Registry storage resolution also keeps the narrower `source` and
  `legacy_fallback` fields for existing callers.

Command-local coverage is intentionally selective:

| Surface | JSON legacy diagnostic | Scope | Reason |
| --- | --- | --- | --- |
| `aippocampus health --json` | `legacy_aliases` | Registry path fallback and project-local diagnostic paths | Aggregate readiness is the canonical broad diagnostic. |
| `aippocampus doctor provider --json` | None for retired env aliases | Provider env aliases were removed; canonical config is reported through `provider_env`. | Provider visibility must not teach deprecated names. |
| `onboard.py --status --json` / `aippocampus onboard --status --json` | `data.legacy_aliases` | Onboarding storage resolution only | Onboarding is where users first discover storage, so remaining host path fallback should be visible without env alias support. |
| Registry storage helpers | `source` and `legacy_fallback` | Storage resolution only | Existing callers depend on this compact shape; use aggregate diagnostics for full alias inventory context. |
| Vault/dashboard commands | None for retired env aliases | `CODEX_MEMORY_*` vault and asset fallbacks were removed | Use `AIPPOCAMPUS_VAULT` / `AIPPOCAMPUS_*_SOURCE` only. |
| Scheduler / hook paths | None for retired typo alias | `AIIPPOCAMPUS_SUBCONSCIOUS_HOOK` typo fallback was removed | Use `AIPPOCAMPUS_SUBCONSCIOUS_HOOK` only. |

## Env Aliases

| Alias | Canonical replacement | Why it exists | Classification | Diagnostic behavior | Removal stage |
| --- | --- | --- | --- | --- | --- |
| `THREAD_MEMORY_REGISTRY_DIR` | `AIPPOCAMPUS_REGISTRY_DIR` | Early registry builds used the thread-memory name before the project settled on AIppocampus storage naming. | Removed migration-only storage fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `CODEX_MEMORY_VAULT` | `AIPPOCAMPUS_VAULT` | Old vault/dashboard tooling used the Codex Memory project name. | Removed migration-only vault projection fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `CODEX_MEMORY_STYLE_SOURCE` | `AIPPOCAMPUS_STYLE_SOURCE` | Old dashboard asset env name. | Removed migration-only vault projection fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `CODEX_MEMORY_SCRIPT_SOURCE` | `AIPPOCAMPUS_SCRIPT_SOURCE` | Old dashboard asset env name. | Removed migration-only vault projection fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `CODEX_MEMORY_SITE_MARK` | `AIPPOCAMPUS_SITE_MARK` | Old dashboard branding env name. | Removed migration-only vault projection fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `CODEX_MEMORY_SITE_TITLE` | `AIPPOCAMPUS_SITE_TITLE` | Old dashboard branding env name. | Removed migration-only vault projection fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `DEEPSEEK_BASE_URL` | `AIPPOCAMPUS_DEEPSEEK_BASE_URL` | Early DeepSeek route configuration used provider-native names directly. | Removed migration-only model-route fallback | Not read by runtime. | Removed 2026-06-21; use explicit OpenAI-compatible route config for custom providers. |
| `DEEPSEEK_MODEL` | `AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL` | Early flash/default route configuration used a provider-native model env. | Removed migration-only model-route fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `DEEPSEEK_PRO_MODEL` | `AIPPOCAMPUS_DEEPSEEK_PRO_MODEL` | Early pro-route configuration used a provider-native model env. | Removed migration-only model-route fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `DEEPSEEK_API_KEY` | `AIPPOCAMPUS_DEEPSEEK_API_KEY` for the built-in DeepSeek route; `AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV` for custom routes | Early DeepSeek route configuration used the provider-native credential name directly. | Removed migration-only model-route fallback; values are secret | Not read by the built-in DeepSeek route. | Removed 2026-06-21; explicit custom routes may still name any env var through `AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV`. |
| `AIIPPOCAMPUS_SUBCONSCIOUS_HOOK` | `AIPPOCAMPUS_SUBCONSCIOUS_HOOK` | A misspelled early subconscious hook knob reached runtime compatibility before the public prefix was corrected. | Removed typo compatibility fallback | Not read by runtime. | Removed 2026-06-21; keep this row only as a regression guard. |
| `CODEX_HOME` | `AIPPOCAMPUS_REGISTRY_DIR` or `AIPPOCAMPUS_HOME/registry` for generated storage; Codex skill install still uses `CODEX_HOME` | Codex host installation and hook config still need the host home. Storage fallback keeps existing Codex users' registries discoverable. | Host install env and legacy storage base, not preferred non-Codex storage API | Storage diagnostics expose only the source label when the fallback is active. | Keep for Codex host install; sunset only the storage fallback after migration evidence. |

## Path Fallbacks

| Path alias | Canonical replacement | Why it exists | Classification | Diagnostic behavior | Removal stage |
| --- | --- | --- | --- | --- | --- |
| `CODEX_HOME/aippocampus-registry` and `default_CODEX_HOME/aippocampus-registry` | `AIPPOCAMPUS_REGISTRY_DIR` or `AIPPOCAMPUS_HOME/registry` | Existing Codex installs may already have generated registry data under Codex home. The `default_CODEX_HOME/...` label means the fallback used the default Codex home because `CODEX_HOME` was unset. | Legacy registry path fallback | `aippocampus_registry_resolution()` and health JSON expose `source` plus `legacy_fallback=true`, without printing the private path in the alias diagnostics. | Do not remove before migration docs and smoke coverage for canonical storage. |
| `.aippocampus/` | AIppocampus registry storage by default, or an explicit export/debug path | Older project-local output and explicit debug/export workflows still use this directory shape. | Explicit compatibility/export/debug mode only | Health JSON reports the alias when resolved diagnostic paths are inside project-local `.aippocampus/`, without printing the actual path in `legacy_aliases`. | Keep as opt-in export/debug mode; do not make it default generated storage. |
| `.aippocampus/clean-source` | Registry-backed clean source, or explicit `--output .aippocampus/clean-source` | Compatibility path for old clean-source artifacts and fixture/debug work. | Explicit compatibility/export/debug mode only | Covered by the `.aippocampus/` project-local diagnostic. | Keep only while explicit export/debug flows need it. |
| `.aippocampus/segments` | Registry-backed segments, or explicit `--output .aippocampus/segments` | Compatibility path for old segmented index artifacts and fixture/debug work. | Explicit compatibility/export/debug mode only | Covered by the `.aippocampus/` project-local diagnostic. | Keep only while explicit export/debug flows need it. |
| `.aippocampus/source_index.sqlite` | Registry-backed rebuildable SQLite index | Legacy search/index helpers can still inspect this project-local SQLite file for compatibility or negative-control fixtures. | Explicit compatibility/export/debug mode only | Covered by the `.aippocampus/` project-local diagnostic. | Keep only while explicit export/debug flows need it. |
| `.aippocampus/graph.json` | Registry-backed generated graph/index artifacts | Legacy rollout-search helpers can still inspect this project-local graph file for compatibility or fixture work. | Explicit compatibility/export/debug mode only | Covered by the `.aippocampus/` project-local diagnostic. | Keep only while explicit export/debug flows need it. |

## Guardrail

`python tools/aippocampus/docs/check_docs_health.py --json` fails when a new
`CODEX_MEMORY_*`, `THREAD_MEMORY_*`, `AIIPPOCAMPUS_SUBCONSCIOUS_HOOK`,
`DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `DEEPSEEK_PRO_MODEL`,
`DEEPSEEK_API_KEY`, `CODEX_HOME/aippocampus-registry`, or `.aippocampus/`
occurrence is added to current docs/code without a row in this inventory. The
guard intentionally ignores archived docs and ordinary DeepSeek constants such
as cache-contract identifiers that are not environment aliases.
