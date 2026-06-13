# Legacy Alias Inventory

Role: inventory.

Last audited: 2026-06-04.

This is the canonical inventory for legacy environment names and path
fallbacks that AIppocampus still accepts before the public API freezes. Public
setup docs should prefer `AIPPOCAMPUS_*` names and package-owner/facade
entrypoints. Legacy names stay visible here so migration behavior is honest,
not so new integrations copy them.

## Runtime Diagnostics

Runtime diagnostics must report alias names and active/shadowed status without
printing values or local paths.

- `aippocampus health --json` reports `legacy_aliases` for env fallbacks,
  registry path fallback, and project-local `.aippocampus/` output when it is
  part of the resolved diagnostic paths.
- `aippocampus doctor provider --json` reports `legacy_aliases` for current
  process env fallbacks alongside the provider env presence check.
- Registry storage resolution also keeps the narrower `source` and
  `legacy_fallback` fields for existing callers.

Command-local coverage is intentionally selective:

| Surface | JSON legacy diagnostic | Scope | Reason |
| --- | --- | --- | --- |
| `aippocampus health --json` | `legacy_aliases` | Env fallbacks, registry path fallback, and project-local diagnostic paths | Aggregate readiness is the canonical broad diagnostic. |
| `aippocampus doctor provider --json` | `legacy_aliases` | Current-process env fallbacks only | Provider visibility is already a process-env diagnostic and must not print credential values. |
| `onboard.py --status --json` / `aippocampus onboard --status --json` | `data.legacy_aliases` | Onboarding storage resolution plus current-process env fallbacks | Onboarding is where users first discover storage, so legacy storage fallback should be visible without requiring a separate health run. |
| Registry storage helpers | `source` and `legacy_fallback` | Storage resolution only | Existing callers depend on this compact shape; use aggregate diagnostics for full alias inventory context. |
| Vault/dashboard commands | Aggregate-only through health / status diagnostics | `CODEX_MEMORY_*` vault and asset fallbacks | Values are local paths/content branding, and command outputs focus on generated vault artifacts rather than environment introspection. |
| Scheduler / hook paths | Aggregate-only through health / provider doctor diagnostics | `AIIPPOCAMPUS_SUBCONSCIOUS_HOOK` typo fallback | Hooks should stay quiet and bounded; diagnostics belong in explicit operator commands. |

## Env Aliases

| Alias | Canonical replacement | Why it exists | Classification | Diagnostic behavior | Removal stage |
| --- | --- | --- | --- | --- | --- |
| `THREAD_MEMORY_REGISTRY_DIR` | `AIPPOCAMPUS_REGISTRY_DIR` | Early registry builds used the thread-memory name before the project settled on AIppocampus storage naming. | Migration-only storage fallback | Active when set and `AIPPOCAMPUS_REGISTRY_DIR` is unset; diagnostics expose alias name only. | Remove only after a migration note and storage smoke prove canonical registry discovery for existing installs. |
| `CODEX_MEMORY_VAULT` | `AIPPOCAMPUS_VAULT` | Old vault/dashboard tooling used the Codex Memory project name. | Migration-only vault projection fallback | Active when the canonical vault env is unset; values and paths are not printed. | Remove after vault docs and any remaining local scripts use `AIPPOCAMPUS_VAULT`. |
| `CODEX_MEMORY_STYLE_SOURCE` | `AIPPOCAMPUS_STYLE_SOURCE` | Old dashboard asset env name. | Migration-only vault projection fallback | Active only when the canonical style source is unset. | Remove with the vault/dashboard alias cleanup. |
| `CODEX_MEMORY_SCRIPT_SOURCE` | `AIPPOCAMPUS_SCRIPT_SOURCE` | Old dashboard asset env name. | Migration-only vault projection fallback | Active only when the canonical script source is unset. | Remove with the vault/dashboard alias cleanup. |
| `CODEX_MEMORY_SITE_MARK` | `AIPPOCAMPUS_SITE_MARK` | Old dashboard branding env name. | Migration-only vault projection fallback | Active only when the canonical site mark is unset. | Remove with the vault/dashboard alias cleanup. |
| `CODEX_MEMORY_SITE_TITLE` | `AIPPOCAMPUS_SITE_TITLE` | Old dashboard branding env name. | Migration-only vault projection fallback | Active only when the canonical site title is unset. | Remove with the vault/dashboard alias cleanup. |
| `DEEPSEEK_BASE_URL` | `AIPPOCAMPUS_DEEPSEEK_BASE_URL` | Early DeepSeek route configuration used provider-native names directly. | Migration-only model-route fallback | Active only when the canonical DeepSeek base URL env is unset; diagnostics never print the URL value. | Remove after public docs and smokes use the canonical model-route env. |
| `DEEPSEEK_MODEL` | `AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL` | Early flash/default route configuration used a provider-native model env. | Migration-only model-route fallback | Active only when the canonical flash-model env is unset; diagnostics never print the model value. | Remove after route docs, tests, and smokes no longer depend on the fallback. |
| `DEEPSEEK_PRO_MODEL` | `AIPPOCAMPUS_DEEPSEEK_PRO_MODEL` | Early pro-route configuration used a provider-native model env. | Migration-only model-route fallback | Active only when the canonical pro-model env is unset; diagnostics never print the model value. | Remove after route docs, tests, and smokes no longer depend on the fallback. |
| `DEEPSEEK_API_KEY` | `AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV` for custom routes; DeepSeek route still defaults to this credential env | DeepSeek's own key name is the current default credential env for the optional DeepSeek route. It is provider-specific, but not yet a deprecated alias. | Public optional provider credential; values are secret | Provider doctor checks presence only and never reads or prints the value. | Keep until a provider-neutral secret indirection is promoted for the DeepSeek route. |
| `AIIPPOCAMPUS_SUBCONSCIOUS_HOOK` | `AIPPOCAMPUS_SUBCONSCIOUS_HOOK` | A misspelled early subconscious hook knob reached runtime compatibility before the public prefix was corrected. | Typo compatibility fallback | Active only when `AIPPOCAMPUS_SUBCONSCIOUS_HOOK` is unset; diagnostics expose alias name only. | Remove after a migration note and one scheduler smoke prove the canonical spelling works for existing installs. |
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
`DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `DEEPSEEK_PRO_MODEL`, provider-specific
`DEEPSEEK_API_KEY`, `CODEX_HOME/aippocampus-registry`, or `.aippocampus/`
occurrence is added to current docs/code without a row in this inventory. The
guard intentionally ignores archived docs and ordinary DeepSeek constants such
as cache-contract identifiers that are not environment aliases.
