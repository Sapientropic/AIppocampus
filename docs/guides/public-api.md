# Public API And Stability

This document is the canonical public API and stability boundary for
AIppocampus. It explains which repository surfaces are intended for users,
agents, plugin hosts, and scripts to depend on.

It complements [public-core-boundary.md](public-core-boundary.md), which owns
licensing, adapter architecture, and minimal schema contracts. Do not mirror
the schema details here.
For host-family support status, smoke evidence boundaries, and planned versus
verified ecosystem claims, see
[ecosystem-integration-matrix.md](ecosystem-integration-matrix.md).

## Ten-Minute Public Path

Use this path when an external user, agent host, or downstream script needs the
smallest dependable AIppocampus surface before learning the research features.

1. Verify the packaged CLI without cloning or writing local memory artifacts:

   ```sh
   uvx aippocampus --help
   ```

2. Check whether the local provider has usable source without registering new
   history. Human-readable output is the default; add `--format json` only for
   automation:

   ```sh
   uvx aippocampus onboard --provider codex --status
   ```

3. After explicit user consent, register local history and search for the first
   source-backed snippet:

   ```sh
   uvx aippocampus onboard --provider codex --all
   uvx aippocampus search "a distinctive old phrase"
   ```

   Use an exact phrase when possible. If the user only remembers a vague cue,
   search a project cue or time cue, but treat that as candidate navigation
   until a source-backed snippet appears.

4. In an installed checkout, inspect the MCP catalog or run health checks when
   the host needs those surfaces:

   ```sh
   aippocampus health --cwd "$PWD" --json
   aippocampus mcp list-tools
   ```

5. Know where data lives before enabling writes. Generated memory artifacts use
   the configured AIppocampus registry: `AIPPOCAMPUS_REGISTRY_DIR`, then
   `AIPPOCAMPUS_HOME/registry`, then legacy Codex registry fallback. Project
   repositories should not receive raw rollouts, registry exports, generated
   indexes, sync bundles, or private local paths.

This path intentionally does not require Dream, cognitive-map jobs, semantic
gates, sync, plugin packaging, benchmark runners, or hook installation. Those
surfaces can be useful, but they are not the 10-minute dependency story.

## Which Layer Should I Depend On?

| Need | Depend on | Stable enough today | Do not depend on |
| --- | --- | --- | --- |
| No-clone probe or install smoke | PyPI `uvx aippocampus ...` and documented repository checks | Documented CLI command names, documented flags, return code success/failure, and public-safe `--json` outputs where documented | Unreleased GitHub `uvx --from git+...` snapshots as stable release evidence; unsigned binary paths beyond the dated Windows x64 evidence |
| Local operator status | `aippocampus health`, `aippocampus onboard --status`, and `memory_health` MCP | Documented status fields, additive JSON fields, and CLI JSON error classes | Human-readable prose, local absolute paths, or private registry internals |
| Agent-host read tools | MCP `search_memory`, `recall_context`, `recall_deepen`, `latest_reply`, `get_turn_context`, `list_threads`, `register_thread`, `sync_status`, `memory_health` | Tool names, required input fields, additive output fields, JSON tool errors, and public-safe path redaction | Broad memory writes, hook install/uninstall, sync push/pull, or arbitrary file ingest through MCP |
| Provider-neutral import | `aippocampus import conversation --format generic-jsonl` and `registry.py register-source --provider generic-jsonl` | Generic JSONL required fields, validation diagnostics, canonical source refs, and import manifests | Markdown import as a public claim, role-ambiguous transcripts, or host-private metadata as public identity |
| Script or CI integration | CLI `--json`, public schemas, and `aippocampus_runtime.cli.facade.run_command(capture_output=True)` inside a trusted Python process | Same command names, JSON shapes, and return-code policy as the public CLI | A broad Python or TypeScript domain SDK; helper-module internals under `skills/aippocampus/scripts/` |
| Cross-device transfer | Documented local-folder, object-storage, and encrypted sync commands | Documented command names, flags, sync manifests, privacy refusal rules, and `AIPPOCAMPUS_*` configuration names | Raw plaintext rollout sync, provider credentials in logs, or managed hosted-service behavior |
| Research or roadmap work | Roadmap, evidence docs, benchmarks, and research notes | Evidence for the current implementation or design direction only | Public API stability for Dream, subconscious jobs, semantic caches, benchmark cache files, or cognitive-map artifacts |

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

Changes that alter public API stability promises, CLI/MCP schema meanings,
documented return-code behavior, ecosystem support status, or `can claim` /
`cannot claim` boundaries use the strict PR lane defined in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#maintainer-shipping-lanes), even when
the edit looks like copy.

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

- `aippocampus health|search|onboard|export|import|doctor|mcp|smoke|storage|sync|object-sync|hooks`
- `aippocampus_health.py`
- `search_clean_source.py`
- `latest_reply.py` as a Codex raw-rollout audit compatibility command
- `onboard.py --provider codex|claude-code|generic-jsonl|auto`
- `aippocampus import conversation --format generic-jsonl --input <path>`
- `aippocampus doctor provider` as a no-model-call visibility diagnostic for
  optional external-model route key environment variables
- `aippocampus smoke recall-funnel "<cue>"` as a no-write progressive recall
  diagnostic over `recall_context` / first reopenable `recall_deepen` route
- `aippocampus storage gc --dry-run` as the no-mutation storage governance plan
  over capacity data and existing retention JSON
- `registry.py register-source --provider generic-jsonl --input <path>`
- `onboard_codex.py`
- `aippocampus_mcp_server.py --list-tools`
- `export_bundle.py` / `import_bundle.py`
- `sync_bundle.py status|push|pull|repair`
- `sync_object_storage.py status|push|pull|repair`
- `aippocampus_runtime.sync.encrypted.admin` package owner and the `encrypted_sync_admin.py` direct command: `key|migrate-to-encrypted|cleanup-plaintext|migrate-object-to-encrypted|cleanup-object-plaintext`
- `install_aippocampus_prompt_hook.py status|install|uninstall`
- `install_aippocampus_lifecycle_hook.py status|install|uninstall`
- `plugins/aippocampus/build_plugin_package.py`
- documented plugin smoke commands

The clone-free PyPI `uvx` entrypoint is also a documented agent-facing
install/probe path:

```sh
uvx aippocampus --help
```

The GitHub `uvx --from git+...` form remains useful for unreleased main-branch
snapshots, but it is not the release evidence path.

The hook scripts and installers above are direct-path compatibility shims over
`aippocampus_runtime.hooks.*` package owners. Keep invoking the documented
script paths from Codex hook configs; Python/runtime callers should import the
package owners.

The onboarding scripts are direct-path compatibility shims over
`aippocampus_runtime.onboarding.*` package owners. Keep invoking documented
script paths from installs and older automation; Python/runtime callers should
import the package owners.

The portable bundle scripts are direct-path compatibility shims over
`aippocampus_runtime.artifacts.export_bundle` and
`aippocampus_runtime.artifacts.import_bundle`. Python callers should prefer
those package owners or the `aippocampus export` / `aippocampus import` facade
commands when they need captureable in-process execution.

For these commands:

- Documented command names and documented flags are stable unless release notes
  say otherwise.
- `--json` output, when documented, is intended for automation.
- JSON objects may gain fields. Consumers should key off documented fields and
  tolerate extra keys.
- Human-readable text is not a stable parse target.
- Warm ambient recall CLI JSON is a public-safe operational summary. It keeps
  status, counts, cache telemetry, and gate buckets, but does not emit raw
  prompts, scout rows, model route secrets, user ids, or raw cards. Python
  callers that need local private diagnostics should call the packaged runtime
  API directly inside the trusted process boundary.
  `provenance_counts` and `support_level_counts` are allowed public-safe
  aggregate diagnostics. Per-card provenance/debug envelopes are not public
  schemas and must not be treated as source-backed evidence.
- `semantic_recall_gate.py --cache-report --json` is an additive trusted-local
  operator diagnostic for the exact semantic result cache. Its public-safe
  projection may include counts, telemetry counters, value-class buckets, and
  hashed cache keys, but must not emit raw prompt text, cue text, source
  snippets, or local paths. Treat the report as cache economics and routing
  health only, not as a source-backed memory or downstream API schema.
- Prompt hook `status --last --json` / `aippocampus hooks prompt status --last --json`
  exposes a public-safe audit projection for the latest prompt hook run. Stable
  automation fields are `status`, `source`, `privacy_boundary`, and
  `last_prompt_hook` fields for `event_id`, `memory_surface`, card/support
  counts, source-reopen count, cache status, topic-epoch presence, and
  warm-background status. The projection is intentionally stricter than verbose
  debug JSONL: it must not include raw prompt text, raw cards, source
  snippets/titles, session or turn ids, secrets, topic-epoch values, or local
  paths. Human-readable status text is not a stable parse target, and
  `scent`/`candidate` memory surfaces are not evidence.
- Verbose prompt-hook debug JSON may include a public-safe
  `scent_threshold_policy` block with base/effective thresholds, adjustment
  reason codes, and a risk boundary. It is route telemetry only, not a stable
  source-backed evidence schema.
- Exit code `0` means the command completed successfully. Non-zero means invalid
  arguments, missing prerequisites, failed validation, failed smoke, or another
  command-specific hard failure.
- Exact non-zero exit-code numbers are not stable yet. Use structured JSON error
  payloads or documented status fields where available.
- The `aippocampus` facade is a thin Python dispatcher. It resolves commands to
  packaged entrypoint mains and preserves stdout/stderr, JSON shape, and return
  code rather than wrapping runtime output in a second envelope. Python callers
  that need composability can use `aippocampus_runtime.cli.facade.run_command`
  with `capture_output=True` to receive a `CommandResult` without launching a
  subprocess or polluting the caller's stdout/stderr.

### CLI JSON Error Contract

Documented `--json` outputs that fail should use this public-safe shape when a
command owns structured errors:

```json
{
  "ok": false,
  "error": {
    "code": "missing_api_key",
    "class": "missing_prerequisite",
    "message": "Missing API key"
  },
  "data": null
}
```

Stable fields for automation are:

- `error.code`: specific machine-readable reason. Consumers may branch on
  documented codes, but must tolerate new codes.
- `error.class`: coarse stable failure class. Consumers should prefer this when
  they only need retry/help behavior.
- `error.message`: human-facing diagnostic. It is not a stable parse target.

The initial stable classes are:

| `error.class` | Meaning | Current example codes | Exit class |
| --- | --- | --- | --- |
| `usage_error` | Caller selected an unsupported operation or malformed command shape. | `usage_error`, `unsupported_operation` | `2` |
| `validation_error` | Caller input was present but invalid. | `invalid_json`, `validation_error`, `missing_required_fields`, `unsupported_role`, `unknown_turn_id` | `2` |
| `missing_prerequisite` | A required file, credential, provider, or local artifact is absent. | `missing_api_key`, `missing_file`, `missing_prerequisite` | `2` |
| `privacy_block` | The command refused to expose or transport private data without an explicit safe mode. | `privacy_blocked` | `2` |
| `runtime_error` | The command reached an unexpected runtime failure or an unclassified downstream error. | `runtime_error`, unknown future codes without a class | `1` |

Exit code `2` is the stable caller/actionable failure class for documented JSON
errors; exit code `1` is the stable runtime/unclassified failure class. Exact
bespoke non-zero numbers remain out of contract until a future release
documents them.

The Python facade remains the default public runtime surface. Windows x64 has
dated PyInstaller artifact smoke evidence, including the standalone binary as a
Claude Code stdio MCP server through `aippocampus.exe mcp`; the current claim is
limited to that verified Windows path. Signed downloads, installer/update UX,
and macOS/Linux Python-free artifacts are not public claims. The current
support/defer/drop matrix is tracked by the
[standalone binary packaging plan](../planning/standalone-binary-packaging.md).

Repo-maintenance commands under `tools/aippocampus/` and
`benchmarks/aippocampus/` are public development aids, not end-user runtime APIs,
unless a public doc explicitly promotes a command.

Remaining Codex raw-rollout/default-home script surfaces are classified in
[provider-entrypoint-inventory.md](../architecture/provider-entrypoint-inventory.md).
General recall should use clean-source search, provider-aware onboarding, MCP
tools, or registry paths; raw Codex audit helpers are not generic
cross-agent-provider APIs.

### Host Hook Boundary

Provider support is not host hook support. `aippocampus onboard --provider
claude-code`, `aippocampus import conversation --format generic-jsonl`, and MCP
registry operations prove transcript registration or clean-source access only.
They do not install, diagnose, or run host hooks.

Codex-only hook installers are exposed through `aippocampus hooks ...`,
`install_aippocampus_prompt_hook.py`, and `install_aippocampus_lifecycle_hook.py`.
Their JSON/status output includes `host_integration.host = "codex"` and
`host_integration.config_surface = "codex_hooks_json"`. Claude Code hook support
is not a public AIppocampus claim until a dedicated Claude Code installer,
status command, privacy note, and host smoke are documented.

## MCP Contract

The current MCP tool catalog is read-mostly and intentionally small. The public
tool names are:

- `search_memory`
- `recall_context`
- `recall_deepen`
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

The caller-facing MCP failure boundary is:

- Missing or malformed tool names/arguments return JSON tool errors such as
  `missing_query`, `malformed_params`, `malformed_arguments`,
  `missing_tool_name`, or `unknown_tool`.
- Missing registered source returns a diagnostic such as
  `clean_source_unavailable` or a non-error empty listing such as
  `status: "registry_missing"`; callers should treat this as "no local memory
  source yet", not as proof that memory does not exist elsewhere.
- Unsupported writes return `unsupported_mutation`. That is a deliberate
  privacy and provenance boundary.
- Tool results redact local paths by default. Local operators may request
  private locators only through documented `include_private_paths` fields.

`recall_context` and `recall_deepen` are the progressive recall navigation
tools. `recall_context` accepts a fuzzy intent or query and returns small route
handles, related source-window candidates, scope labels, evidence levels, and
the next tool to call. It does not return a final answer or factual memory
claim. `recall_deepen` consumes a route handle or ambient navigation seed and
opens the next source-backed layer when the handle is still fresh and
reopenable. Stale, malformed, or non-reopenable handles fail as MCP tool errors
instead of silently becoming evidence.

`register_thread` is an explicit control-plane operation. It is not a general
memory-write API.

### MCP Control-Plane Boundary

Control-plane registration means attaching an existing local conversation source
to the AIppocampus registry so later read tools can find source-backed memory.
For the current public MCP surface, `register_thread` may:

- create or update a registry thread record for the selected provider,
  workspace, and registry root;
- optionally build generated clean-source/index artifacts from existing
  provider-visible history when `build_index` is true; and
- return operational status and locators, with local paths redacted unless the
  caller explicitly requests `include_private_paths`.

It must not accept arbitrary user-authored memory facts, rewrite source events,
delete or overwrite existing memory artifacts, install hooks, push/pull/repair
sync state, or mutate model-organized summaries. Those behaviors are memory
writes or operator mutations, not control-plane registration.

Calls for unsupported mutating tools such as `store_memory`, `write_memory`,
`delete_memory`, `sync_push`, `sync_pull`, `install_hook`, or `uninstall_hook`
must fail as MCP tool errors with `error.code: "unsupported_mutation"` rather
than silently becoming broad write APIs. Unknown non-mutating tool names should
remain `unknown_tool`.

Future MCP write additions must prove privacy, provenance, idempotence, and
source-backed auditability before they become public. They also need an explicit
operator consent path, a repair/rollback story, and a machine-readable error
contract that does not require callers to parse human prose.

Explicit file or directory import is a separate provider-neutral CLI operation:
use `aippocampus import conversation --format generic-jsonl --input <path>` or
`registry.py register-source --provider generic-jsonl --input <path>` for an
exported transcript. `register_thread` is for attaching/building the selected
current provider session through the MCP control plane; it is not a generic arbitrary-file ingest endpoint.

MCP JSON output defaults to public-safe local-path redaction for tool results
that can be forwarded through host agents. Callers that are acting as local
operators may pass `include_private_paths: true` where documented by the tool
schema to recover local locators for repair/debug work.

## Provider Identity And Privacy

Provider-neutral identity uses stable join keys such as `thread_key`,
`source_id`, `source_ref`, `turn_id`, `message_id`, and content hashes. Local
absolute paths are private locators for audit, repair, and generated artifact
lookup; they are not identity and should not be forwarded as public evidence.

Clean-source manifests may retain private `cwd`, `source_transcript`,
`source_artifact.path`, and output paths for local operators. Public/MCP/sync
projections should redact or bundle-relativize those paths while preserving
source-backed ids and source refs. Legacy `source_rollout*` manifest aliases are
compatibility fields for old Codex consumers; new provider-neutral integrations
should read `source_artifact` or `source_transcript*`.

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

To register an explicit file without relying on provider discovery environment
variables:

```sh
aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --project "Project name" --json
```

Use `--dry-run` to validate and preview the target thread key without writing
clean-source artifacts or registry rows.

## JSON And Schema Contracts

The stable public data schemas are owned by
[public-core-boundary.md](public-core-boundary.md):

- Canonical source event
- Clean-source chunk
- Source ref
- Import manifest

Provider-specific `metadata` and third-party extension rules also live there;
this document only points to the schema owner.

Generated indexes, registry rows, sidecar metrics, cognitive-map artifacts,
subconscious job rows, and debug/provenance envelopes are not stable public
schemas unless a future document promotes a subset.

Consumers should prefer source refs and clean-source artifacts over generated
summary, label, or model-organized output when they need evidence.

## Environment Variables

Public environment variables use the `AIPPOCAMPUS_*` prefix. This section is
the canonical public matrix for environment configuration; install docs may
show examples and the safe [`.env.example`](../../.env.example) template may
point here, but they should not mirror this whole list. "Public" means
documented and stable enough to configure. It does not mean the variable value
is safe to publish.

### Environment Configuration Matrix

| Variable / family | Group | Audience | Default / precedence | Sensitivity | Stability |
| --- | --- | --- | --- | --- | --- |
| `AIPPOCAMPUS_REGISTRY_DIR` | Storage and discovery | End users, agents, operators | Exact registry root; first registry lookup choice | Local private path | Public configuration |
| `AIPPOCAMPUS_HOME` | Storage and discovery | End users, agents, operators | Uses `AIPPOCAMPUS_HOME/registry` after exact registry vars | Local private path | Public configuration |
| `THREAD_MEMORY_REGISTRY_DIR` | Legacy storage | Existing installs and compatibility scripts | Legacy exact registry root after `AIPPOCAMPUS_REGISTRY_DIR` | Local private path | Compatibility fallback; avoid in new docs |
| `CODEX_HOME` | Codex install and legacy storage | Codex users and hook installers | Skill/home discovery; generated registry fallback when no `AIPPOCAMPUS_*` storage var is set | Local private path | Compatibility fallback, not the preferred non-Codex storage API |
| `AIPPOCAMPUS_GENERIC_IMPORT_DIR` | Generic JSONL onboarding | Integrators testing provider-neutral import | Optional default import file/dir when CLI args omit a source | Local private path | Public convenience configuration |
| `AIPPOCAMPUS_VAULT`, `AIPPOCAMPUS_STYLE_SOURCE`, `AIPPOCAMPUS_SCRIPT_SOURCE`, `AIPPOCAMPUS_SITE_MARK`, `AIPPOCAMPUS_SITE_TITLE` | Vault projection | Local operators publishing their own memory view | Optional; CLI defaults apply when unset | Local path/content branding may be private | Public operator configuration |
| `AIPPOCAMPUS_OBJECT_STORE_URL`, `AIPPOCAMPUS_OBJECT_PREFIX`, `AIPPOCAMPUS_OBJECT_PROVIDER`, `AIPPOCAMPUS_OBJECT_BUCKET`, `AIPPOCAMPUS_OBJECT_REGION`, `AIPPOCAMPUS_OBJECT_ACCOUNT_ID` | Object-storage sync | Operators configuring HTTP, S3-compatible, R2, or GCS XML sync | CLI flags override; provider defaults apply where documented | Endpoint/account/prefix may reveal infrastructure | Public sync configuration |
| `AIPPOCAMPUS_OBJECT_STORE_TOKEN`, `AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID`, `AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY`, `AIPPOCAMPUS_OBJECT_SESSION_TOKEN` | Object-storage credentials | Operators configuring managed object storage | Read only when the selected provider needs credentials | Secret credential material | Public variable names; values must never be logged or published |
| `AIPPOCAMPUS_AGE_BIN`, `AIPPOCAMPUS_AGE_KEYGEN_BIN` | Encrypted sync tooling | Operators whose GUI shell does not inherit `PATH` | Preferred before `PATH` lookup for the relevant `age` binary | Local executable path | Public operator configuration |
| `AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS`, `AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT`, `AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY`, `AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS`, `AIPPOCAMPUS_SEMANTIC_GATE` | Hook budgets, aggregate skip telemetry, and semantic recall | Local operators tuning hook latency, false-negative calibration, and semantic gating | Built-in conservative budgets; aggregate skip telemetry enabled by default and disabled with `0` / `false` / `off` / `no` | Timing policy and aggregate skip counts may reveal local workflow shape; raw prompt text must not be logged | Public operator configuration |
| `AIPPOCAMPUS_SEMANTIC_TIMEOUT`, `AIPPOCAMPUS_SEMANTIC_TEMPERATURE`, `AIPPOCAMPUS_SEMANTIC_CACHE_TTL`, `AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT`, `AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT` | Semantic recall diagnostics | Trusted local operators and repo tests | Used by semantic recall helpers when explicit config is absent | May affect private prompt/model behavior | Diagnostic/operator configuration; prefer explicit config in new integrations |
| `AIPPOCAMPUS_WARM_RECALL_TIMEOUT`, `AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT`, `AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS`, `AIPPOCAMPUS_WARM_RECALL_BACKGROUND`, `AIPPOCAMPUS_DETACHED_WARM_TIMEOUT`, `AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_SCOUTS`, `AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_DELAY` | Warm ambient recall limits | Local operators tuning background recall cost and latency | Built-in defaults; explicit CLI/config should own product tuning | Timing/concurrency policy may reveal local workflow shape | Public operator configuration for limits only |
| `AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL`, `AIPPOCAMPUS_DEEPSEEK_PRO_MODEL`, `AIPPOCAMPUS_DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY` | Optional DeepSeek route | Operators enabling optional external-model work | DeepSeek defaults where unset; legacy `DEEPSEEK_*` model vars may remain fallback-only | `DEEPSEEK_API_KEY` is secret; base URL/model may reveal provider choice | Public optional route configuration; external-model features remain optional |
| `AIPPOCAMPUS_OPENAI_COMPAT_ROUTE`, `AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER`, `AIPPOCAMPUS_OPENAI_COMPAT_MODEL`, `AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL`, `AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV`, `AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING`, `AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND` | Optional OpenAI-compatible route | Operators testing provider portability | Only active when a complete compatible route is configured | API-key variable name and base URL may reveal provider setup; referenced key value is secret | Public optional route configuration |
| `AIPPOCAMPUS_SUBCONSCIOUS_HOOK`, `AIPPOCAMPUS_SUBCONSCIOUS_CONCURRENCY`, `AIPPOCAMPUS_SUBCONSCIOUS_JOB_CONCURRENCY`, `AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB` | Subconscious/background jobs | Trusted local operators and repo-maintenance smokes | Conservative defaults; jobs still require explicit commands or hook conditions | May reveal private background-work policy | Diagnostic/operator configuration, not a broad hosted-service API |
| `AIPPOCAMPUS_DREAM_DELIVERY_MODE`, `AIPPOCAMPUS_DREAM_SHADOW_AB`, `AIPPOCAMPUS_DREAM_SHADOW_AB_SALT`, `AIPPOCAMPUS_DREAM_ROLLOUT_RATE` | Dream/research delivery policy | Trusted local operators evaluating research features | Defaults keep research surfaces conservative unless explicitly enabled | Salt/rollout policy may reveal experiment setup | Experimental diagnostic configuration |
| `AIPPOCAMPUS_PROJECTS_TOKEN`, `GH_TOKEN`, `GITHUB_REPOSITORY`, `AIPPOCAMPUS_PROJECT_OWNER`, `AIPPOCAMPUS_PROJECT_NUMBER` | GitHub Project triage and planning audit | Repository maintainers and GitHub Actions | Workflow token/env defaults where available; local maintainer tools may also use `gh auth token` when env tokens are absent | Tokens are secret; repo/project ids are public or repo-maintenance metadata | Public maintenance configuration, not end-user runtime API |

Common installs should stay small:

- Fresh local use can start with no AIppocampus-specific env vars.
- Non-Codex or shared local storage should set `AIPPOCAMPUS_HOME` or
  `AIPPOCAMPUS_REGISTRY_DIR`.
- Sync needs only the relevant local-folder or object-storage variables plus
  encryption settings when raw/private data is included.
- External-model and background-job variables are optional. Do not set them just
  to use clean-source search, MCP, import/export, or local sync.
- `aippocampus doctor provider --json` checks whether the selected model
  route's API-key environment variable is visible to the current process and a
  child process. This is a presence-only check: it does not read or validate the
  key value, so it cannot prove the key is non-empty, correct, or unexpired. It
  does not read `.env` files, credential stores, or keychain entries, it never
  prints key values, and it does not claim to inspect a previously started Codex
  Desktop hook process. JSON output names this surface `provider_env`; use
  `--provider-env-var` to override the selected route variable name for local
  diagnostics.

Registry storage precedence remains explicit:

1. `AIPPOCAMPUS_REGISTRY_DIR`: exact registry root.
2. `THREAD_MEMORY_REGISTRY_DIR`: legacy exact registry root.
3. `AIPPOCAMPUS_HOME/registry`: provider-neutral AIppocampus home.
4. `CODEX_HOME/aippocampus-registry`, or the default Codex home path if no
   AIppocampus storage variable is set: legacy compatibility fallback.

AIppocampus never migrates or deletes an existing registry automatically.
Codex skill installation and Codex hook configuration may still use
`CODEX_HOME`; generated memory storage should prefer the `AIPPOCAMPUS_*`
variables for new non-Codex setups.

Product-tuning values such as warm-recall temperature, quorum, thinking mode,
and foreground prefix-cache warmup should use explicit CLI flags or structured
runtime config such as `WarmRecallConfig`, not ambient import-time env defaults.
For foreground prompt integrations, prefer the packaged prompt wrapper over
calling the semantic gate directly. Direct Python callers that mark a call as
foreground must provide an explicit wall-clock deadline and a worker timeout
within that deadline; otherwise the gate fails open without an external model
call. Background and operator semantic recall can still use the longer
quality-first defaults.

Never log or publish environment variable values that contain credentials,
tokens, cookies, local private paths, or private memory locations.

## Python Import Policy

AIppocampus does not currently publish a broad stable Python package API.
Runtime code under `skills/aippocampus/scripts/` remains script-first unless a
package owner is explicitly documented here or in a linked contract.

SDK status: there is no general public Python SDK and no TypeScript SDK today.
The supported dependency story is CLI, MCP, public schemas, import manifests,
and the thin trusted-process Python command dispatcher documented below. Add a
domain SDK only after a concrete downstream use case proves that those surfaces
are insufficient.

### Python Import Stability Layers

| Layer | What is stable | Use when | Not a promise |
| --- | --- | --- | --- |
| Stable automation surfaces | Documented CLI commands, MCP tool names/input schemas, documented `--json` fields, and public schemas in [public-core-boundary.md](public-core-boundary.md) | Downstream callers, agent hosts, CI, and user scripts need integration that survives releases | A general Python SDK or stability for helper-module internals |
| Trusted-process runtime helpers | Documented package owners such as `aippocampus_runtime.hooks.*`, `aippocampus_runtime.onboarding.*`, `aippocampus_runtime.artifacts.*`, `aippocampus_runtime.sync.encrypted.admin`, and `aippocampus_runtime.cli.facade.run_command` | Repo-owned tools, plugin packaging, local diagnostics, and trusted operators need in-process execution without subprocess output pollution | Compatibility outside the documented owner module, raw private diagnostics as public schemas, or use across an untrusted process boundary |
| Internal helper imports | No compatibility promise; imports may move as the runtime package replaces flat scripts | Maintainers are refactoring inside this repository with tests in the same change | Downstream API stability |

The current in-process composability helper is
`aippocampus_runtime.cli.facade.run_command(capture_output=True)`. It gives
trusted Python callers a `CommandResult` while preserving the same command
names, JSON shapes, and return-code policy as the public CLI. It is a command
dispatcher/result API, not a domain SDK.

`aippocampus_runtime.public` is deferred. Add it only when a concrete downstream
use case cannot be served cleanly by CLI, MCP, public schemas, import manifests,
or `run_command`, and after that use case defines a smaller stable contract than
"everything under `aippocampus_runtime`".

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
- Semantic result-cache and semantic-cue-cache reports are trusted-local
  diagnostics. They may be public-safe in content, but their helper-level field
  shapes are additive implementation details unless a facade command documents
  them.
- Debug output, trace fields, timing metrics, and local absolute paths.
- Research notes under `docs/research/`.
- External provider pricing, rate limits, model IDs, and cache behavior.
- Hosted, managed, enterprise, or commercial service behavior.

Private memory artifacts are never public API. Raw rollouts, clean-source
exports, registry data, sync bundles, vault exports, generated indexes, and
thread anchors remain private user data unless their owner intentionally
publishes them.
