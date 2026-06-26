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
For the friction budget between ordinary personal recall, optional diagnostics,
and governed/high-risk controls, see
[product-profiles.md](../architecture/host/product-profiles.md).

## Ten-Minute Public Path

Use [ten-minute-public-path.md](ten-minute-public-path.md) when an external
user, agent host, or downstream script needs the smallest dependable
AIppocampus probe before learning this full stability contract.

This document remains the canonical API and dependency boundary. Stay here when
you are deciding which CLI, MCP, JSON, environment, or Python import surface a
tool should depend on. Use the short path for first-use and return here only
when integration or operator decisions need the larger contract.

## Which Layer Should I Depend On?

| Need | Depend on | Stable enough today | Do not depend on |
| --- | --- | --- | --- |
| No-clone probe or install smoke | PyPI `uvx aippocampus ...` and documented repository checks | Documented CLI command names, documented flags, return code success/failure, MCP tool names, and public-safe `--json` outputs where documented | Unreleased GitHub `uvx --from git+...` snapshots as stable release evidence; Codex-only scoped-provider status from the provider-matrix status command; unsigned binary paths beyond the dated Windows x64 evidence |
| Local operator status | `aippocampus health`, `aippocampus onboard --status`, and `memory_health` MCP | Documented status fields, additive JSON fields, source-intake quality diagnostics, and CLI JSON error classes | Human-readable prose, local absolute paths, or private registry internals |
| Agent continuity pull path | `aippocampus agent recall`, `agent background`, `agent aippo`, `agent deepen`, `agent explain`, `agent feedback`, and `do-not-use-here` | Documented command names, public-safe JSON envelope fields, compact foreground packet fields, reviewed background finding handles, explicit deepen/request handles, and low-authority feedback receipts or JSONL rows when explicitly chosen | Default foreground hooks, every-turn recall, public SDK stability, hosted API behavior, background findings as facts, feedback as source truth, or destructive forgetting |
| Agent-host read and setup tools | MCP `agent_recall`, `agent_aippo`, `agent_deepen`, `agent_explain`, `search_memory`, `recall_context`, `recall_deepen`, `latest_reply`, `get_turn_context`, `list_threads`, `register_thread`, `sync_status`, `memory_health`, `list_telepathy_handoffs`, and `deepen_telepathy_handoff` | Tool names, required input fields, additive output fields, JSON tool errors, public-safe path redaction, and compact foreground projections by default | Broad memory writes, `agent feedback` through MCP, Telepathy card create/release through MCP, hook install/uninstall, sync push/pull, arbitrary file ingest through MCP, or mutating setup calls without an explicit write-shaped argument |
| Provider-neutral import | `aippocampus import conversation --format generic-jsonl` | Generic JSONL required fields, validation diagnostics, canonical source refs, and import manifests | Markdown import as a public claim, role-ambiguous transcripts, host-private metadata as public identity, or internal registry modules as public CLI contracts |
| Script or CI integration | CLI `--json`, public schemas, and `aippocampus_runtime.cli.facade.run_command(capture_output=True)` inside a trusted Python process | Same command names, JSON shapes, and return-code policy as the public CLI | A broad Python or TypeScript domain SDK; helper-module internals under `skills/aippocampus/scripts/` |
| Agent-native fixture proposals | Linked architecture contracts such as `aippocampus_runtime.recall.agent_facade_contract`, `aippocampus_runtime.recall.agent_pull_gesture`, and `aippocampus_runtime.aippo.working_contract` | Current fixture-backed behavior and public-safe schema direction for trusted host experiments | Public SDK stability, hosted network endpoints, broad package internals, or claim-ready memory facts |
| Cross-device transfer | Documented local-folder, object-storage, and encrypted sync commands | Documented command names, flags, sync manifests, privacy refusal rules, and `AIPPOCAMPUS_*` configuration names | Raw plaintext rollout sync, provider credentials in logs, or managed hosted-service behavior |
| Research or roadmap work | Roadmap, evidence docs, benchmarks, and research notes | Evidence for the current implementation or design direction only | Public API stability for Dream, subconscious jobs, semantic caches, benchmark cache files, or cognitive-map artifacts |

## Copyable Agent Gesture

For an agent-facing first call, choose the narrow foreground pull path before
reading the full tool catalog:

| Situation | First tool | Then |
| --- | --- | --- |
| Fuzzy old context, unfinished work, handoff, correction, or preference | `agent_recall` or `recall_context` | Deepen the selected route before claims. |
| Exact phrase or distinctive wording | `search_memory` or `aippocampus search` | Reopen source before quoting or widening scope. |
| Latest closeout | `latest_reply` | Use `get_turn_context` if surrounding turns matter. |
| No route, stale registry, or missing source | `memory_health` or onboard/status card | Repair/setup only after explicit consent. |
| Route was wrong, noisy, or should be quiet here | feedback/control command | Treat it as low-authority scoped feedback, not source truth. |

Agent hosts that want one minimal source-backed continuity move should copy the
`source_backed_continuity_gesture_v1` workflow from
[`agent-native-recall-facade.md`](../architecture/recall/agent-native-recall-facade.md):

```text
detect continuity-sensitive task
  -> recall(query, context)
  -> use one compact MemoryPacket / AIppo activation packet
  -> deepen(route_id) before exact, public, disputed, stale/currentness,
     sensitive, or high-risk claims
  -> record lightweight outcome feedback
```

This is an agent behavior contract over existing local read tools, not a new
network API. Negative and anti-nag controls are part of the gesture: do not call
AIppocampus every turn, and do not treat AIppo activation or bounded summaries
as source evidence.

`aippocampus agent recall --attention-router-mode auto` belongs to this
agent continuity pull path. It may sort already emitted
reopenable routes only after the explicit-pull attention-router gate passes; it
is not a default hook, every-prompt recall path, hosted API behavior, or
source-truth upgrade.
Returned route labels, topics, and rank reasons are navigation previews only.

The first executable AIppo working-contract fixture lives at
`aippocampus_runtime.aippo.working_contract`. It is a host-facing proposal for
trusted local experiments: a compact activation packet may guide low-risk
planning, patch shape, and review posture, while source refs, support ledgers,
candidate provenance, and suppressed clauses remain behind deepen/explain. It
is not a public Python/TypeScript SDK, network API, or stable marketplace
format.

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
  `aippocampus mcp list-tools --json`.
- The source-event, clean-source chunk, source-ref, and import-manifest schemas
  documented in [public-core-boundary.md](public-core-boundary.md).
- The knowledge-source manifest and knowledge-claim record schemas documented
  in [public-core-boundary.md](public-core-boundary.md). These define source
  eligibility and claim promotion records, not a public knowledge-ingest,
  ranking, or answer-generation API.
- The Memory Evidence Drawer contract documented in
  [memory-evidence-drawer.md](../architecture/recall/memory-evidence-drawer.md) is the
  current contract for additive foreground explanation packets. Drawer JSON may
  explain why a route surfaced, expose source refs/reopen affordances, and
  declare suppress/correct/pin/deepen metadata; it is not a source-truth API,
  memory-write API, or confidence-as-authority layer.
- The high-risk answer gate policy documented in
  [high-risk-answer-gates.md](../architecture/host/high-risk-answer-gates.md) as a
  staged deterministic contract prototype and trusted local cannot-claim
  boundary, not as default foreground behavior, generated professional advice,
  or a public answer API.
- The Codex plugin package source under `plugins/aippocampus/`, including its
  MCP config and packaged skill surface.
- The documented local-folder, HTTP object-storage, and encrypted sync commands.
- The repository-level verification commands documented in `README.md` and
  [install-guide.md](install-guide.md).

The public API does not include every helper module or every script under
`skills/aippocampus/scripts/`.

Typed agent-skill capability manifests, including
`aippocampus_runtime.knowledge.capability_types` and the public-safe fixture
under `tests/fixtures/knowledge_sources/`, are an internal architecture
prototype unless a future public contract explicitly promotes a subset. They
constrain execution permissions and evaluation boundaries; they are not a
public answer API, public SDK schema, or source of factual authority.

## CLI Contract

The CLI contract applies to documented operator commands, especially:

- Personal/default path commands: `aippocampus health|search|onboard|export|import|update`.
- Advanced/operator commands remain public and discoverable, but do not need to
  run before first recall: `aippocampus doctor|mcp|smoke|logs|storage|telepathy|sync|object-sync|hooks|plugin`
- Diagnostic commands such as `aippocampus why-recall`, `aippocampus
  why-not-recall`, and `aippocampus observatory` are recovery/explanation
  tools, not first-recall setup steps. Use them when recall stayed silent,
  recall surfaced too much, a route was surprising, stale/private/conflict
  boundaries need explanation, or an operator wants route-readiness audit
  detail.
- `aippocampus continuity-domain produce|append|publish|report` as the
  explicit local producer, authoring, and snapshot-publish path for Contract v1
  continuity domains
- `aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json`
  as the preview-first explicit file import path; omit `--dry-run` only after
  replacing the example filename with a user-selected export and confirming the
  selected local history is safe to register
- `aippocampus doctor provider` as a no-model-call visibility diagnostic for
  optional external-model route key environment variables
- `aippocampus smoke recall-funnel "<cue>"` as a no persistent-write
  progressive recall diagnostic over `recall_context` / first reopenable
  `recall_deepen` plus the ordinary `agent recall -> agent deepen` path
- `aippocampus why-recall "<cue>" --json` and `aippocampus why-not-recall
  "<cue>" --json` as public-safe recovery/explanation diagnostics over
  `recall_context`, active locks, ambient cache, and semantic-gate state
- `aippocampus storage gc --dry-run` as the no-mutation storage governance plan
  over capacity data and existing retention JSON
- `aippocampus search "<cue>" --public` / `--metadata-only` as the
  public-safe compact search receipt for issue attachments, support reports, or
  other surfaces that need matched wording without local reopen details. It may
  emit capped matched snippets by design, but it must omit source refs, handles,
  message ids, and local identifiers. `--snippet-chars 0` is supported when
  automation wants normal match rows but no snippet text.
- `aippocampus export --redaction-profile public-export --no-raw` as the
  metadata-only public bundle path. It omits clean-source text, session refs,
  host session metadata, anchors, graph labels, raw rollouts, and searchable
  SQLite indexes. Use `raw-private` or `redacted-local` only for private
  searchable transfer bundles.
- `aippocampus telepathy create|list|deepen|release|diagnose` as the explicit
  local handoff-card lifecycle over the Telepathy packet contract. MCP exposes
  `list_telepathy_handoffs` and `deepen_telepathy_handoff` as read-only host
  tools; create/release through MCP is intentionally unsupported.
- `aippocampus logs status|rotate` as public-safe local log retention
  diagnostics and cleanup over artifact names and byte counts, not log contents
- `aippocampus warm status --json` as public-safe, read-only warm ambient queue
  status over counts and worker-evidence boundaries, without model calls,
  prompt text, provider payloads, or local paths
- `aippocampus health` human output as a bounded repair card. It may show the
  highest-priority copy-pasteable `Next:` commands from structured
  `recommended_actions`; automation should still use `--json`.
- `aippocampus storage gc --apply --class rebuildable --include-active` as the explicit
  path-level rebuildable-cache eviction path for retention-report-backed main
  SQLite caches and capacity-report-backed old source-index / segment
  generation directories whose reader-pin/TTL, current/LKG pointer, source,
  lease, and active-thread checks pass; capacity aggregates and source/review
  artifacts remain outside apply v1.
- `aippocampus mcp status|list-tools --json`
- `aippocampus hooks prompt status|install|uninstall`
- `aippocampus hooks lifecycle status|install|uninstall`
- `aippocampus plugin install --codex --verify` as the local Codex plugin
  happy path over package build, AIppocampus-owned local marketplace refresh,
  current Codex marketplace add/upgrade, versioned installed-cache refresh, MCP
  host reload, and `sync_status` probe; `--json` returns the public-safe
  success summary by default, while `--operator-json` exposes the full
  operator report for deep debugging. `--compact-json`, `--public`, and
  `--summary` remain explicit summary aliases; `aippocampus plugin uninstall
  --codex --dry-run` previews the paired rollback plan and `aippocampus plugin
  uninstall --codex` applies it.
- `aippocampus episode-arcs` as a compact foreground readout; add `--json`
  only for the aggregate local audit report.
- `plugins/aippocampus/build_plugin_package.py`
- documented plugin smoke commands

The personal/default path is intentionally not purpose-token gated. Purpose
tokens, mandatory review queues, policy reports, and other high-risk governance
controls follow the profile boundary in
[public-core-boundary.md](public-core-boundary.md#product-profile-boundary)
instead of becoming baseline CLI ceremony.

The clone-free PyPI `uvx` entrypoint is also a documented agent-facing
install/probe path:

```sh
uvx aippocampus --help
```

The GitHub `uvx --from git+...` form remains useful for unreleased main-branch
snapshots, but it is not the release evidence path.

Flat top-level runtime scripts are no longer a supported API layer. Python
callers should import package owners or use
`aippocampus_runtime.cli.facade.run_command(capture_output=True)` when they need
captureable in-process execution.

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
- Query-pattern enrichment report JSON is a no-write registry/import planning
  diagnostic. It may expose changed-generation counts, planned work item ids,
  cache reuse, invalidation counts, provider/privacy suppression, and aggregate
  consumption metrics, but it must not call a live model or expose raw source
  text, answer text, local paths, prompts, or secrets. The companion
  `query_pattern_routes.jsonl` sidecar is a trusted-local navigation cache:
  onboarding may publish default deterministic routes from registry/import
  metadata and reviewed `semantic_triggers.jsonl` rows during sidecar refresh,
  its writer filters stale source-generation digests, invalid local aliases, and
  privacy-blocked rows, and the prompt hook may consume matching rows as
  hot-path `scent` only. Reviewed seed triggers without explicit source refs may
  derive bounded registry route handles from matching registry metadata; that
  derived handle is still navigation-only. The publisher reserves route budget
  for reviewed semantic rows so default registry metadata cannot starve natural
  alias routes. Public publish reports expose counts and boundary flags, not
  alias text or source refs. Query-pattern route packets, hook debug summaries,
  and Observatory reports may expose alias-source aggregate counts and rates for
  `registry_metadata`, `reviewed_semantic`, `local_offline_generated`, and
  `external_model_generated` rows. Generated aliases are not evidence;
  foreground use still requires source reopen before any factual claim.
- `semantic_recall_gate.py --cache-report --json` is an additive trusted-local
  operator diagnostic for the exact semantic result cache. Its public-safe
  projection may include counts, telemetry counters, value-class buckets, and
  hashed cache keys, but must not emit raw prompt text, cue text, source
  snippets, or local paths. Treat the report as cache economics and routing
  health only, not as a source-backed memory or downstream API schema.
- `why-recall` / `why-not-recall` JSON is a low-level explanation packet, not a
  recall answer. Stable automation fields are `kind`, `schema_version`, `mode`,
  `cue_hash`, `decision`, `searched_surfaces`, `surface_reports`, `reasons`,
  `route_ids`, `next_safe_action`, `cannot_claim`, and
  `privacy_boundary`. The command may inspect existing local artifacts and can
  run the semantic gate only when `--run-semantic-gate` is explicitly supplied.
  `why-not-recall` distinguishes true silence from surfaced-but-low-specificity
  routes, so a caller can choose between changing the cue and deepening an
  existing route.
  Default output must not emit the raw cue, raw source text, local paths, source
  snippets, prompts, tool payloads, or secrets. The Cognitive Observatory
  tracked in GitHub issue #576 may use this packet as a read-only "why this
  route" drilldown, but the packet is not a control plane and cannot establish
  source truth without source reopen.
- `aippocampus agent recall --json` is the default bounded foreground
  projection for logs, issue reports, and agent handoffs. It omits
  local-private handles and offers request-index deepen commands when local
  reopen is available. `--public` and `--compact-json` remain compatibility
  aliases for this default. Use `--detail full` only for explicit local
  diagnostics where private handles are acceptable.
- `aippocampus agent background "task cue" --json` is the foreground route for
  reviewed Dream/subconscious working-memory findings. Default JSON is a compact
  action card with a best-finding summary and one primary source-reopen action.
  Use `--detail full` or `--operator-json` for full finding lists, reader
  diagnostics, feedback actions, or action-hint materialization previews. These
  findings are navigation only and never source truth until source is reopened.
- `observatory --json` emits a public-safe, no-write Cognitive Observatory
  readout; `observatory --html --output <path>` renders the same sanitized
  readout as a static, no-script operator view. The first stable slice
  aggregates route-readiness/prewarm
  diagnostics, activation-surface authority, optional recall diagnostics, and
  sleep-cycle public summaries. A `--query-pattern-routes <json-or-jsonl>`
  input may add query-pattern route counts and active/suppressed buckets without
  emitting alias text. A `--cognitive-load-calibration <json>` input may add a
  #575 cognitive-load calibration summary with counts/rates only; both the
  private-history aggregate report and the public behavior-trace feedback
  fixture are projected as diagnostic metadata, not source truth. Source-ref
  hash samples, private text, command text, trace text, and paths are not passed
  through.
  Route-readiness, query-pattern, and cognitive-load rows are
  `navigation_only`; they can justify reopening source but cannot support
  factual claims, mutate owner surfaces, or control foreground hooks. The
  `control_authority_audit` block counts attempted activation/mutation requests
  as blocked diagnostics; it is not an API for applying those actions.
  `tools/aippocampus/smoke/smoke_cognitive_observatory_current_completeness.py`
  is the public-safe completeness smoke for the current read-only surface: it
  reports included and missing Observatory surfaces, stale/privacy/suppressed
  buckets, and blocked control attempts without serializing raw prompts, source
  payloads, source refs, thread handles, paths, provider payloads, or secrets.
  Its top-level `reader_contract` gives a compact operator view of included
  surfaces, missing optional surfaces, blocked/suppressed surfaces,
  `read_only` control-plane status, and safe next actions; each surface row
  separates supported, present-in-this-readout, and fixture-validated states.
  The readout also includes `campus_usefulness_panels` with `Useful Now`,
  `Wasted Motion`, `Quiet For A Reason`, and `Needs Ripening` buckets. These
  panels reuse existing diagnostics to make usefulness failures visible; they
  do not rank, activate, edit, or prove routes.
- `episode-arcs` without `--json` emits a compact foreground readout with scan
  counts, arc counts, next action, and claim boundary. `episode-arcs --json`
  emits the full aggregate-only, private-history Episode/Arc adjudication
  readout for #663. It scans local clean-source messages/events and reports
  counts, buckets, and claim boundaries for rejected-route chains. It
  must not emit source text, raw command text, source refs, source-ref hash
  samples, event ids, thread ids, local paths, or registry paths. Sequence
  packets remain navigation-only and current validity still requires source
  reopen.
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
- Verbose prompt-hook debug JSON may also include `foreground_context`
  aggregate metrics such as model-visible character/line counts,
  chars-per-candidate, weak-scent budget violations, debug-only field leak
  count, direction-only foreground budget violations, and whether
  Observatory/debug detail is available elsewhere. These metrics describe the
  projection width; they must not include raw foreground text, raw prompts, raw
  source snippets, route ids, source refs, local paths, or private aliases.
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
| `missing_prerequisite` | A required file, credential, provider, or local artifact is absent. | `missing_api_key`, `missing_file`, `input_not_found`, `missing_prerequisite` | `2` |
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
[provider-entrypoint-inventory.md](../architecture/host/provider-entrypoint-inventory.md).
General recall should use clean-source search, provider-aware onboarding, MCP
tools, or registry paths; raw Codex audit helpers are not generic
cross-agent-provider APIs.
The fixture-backed cross-agent read-path isolation boundary is documented in
[`cross-agent-recall-isolation.md`](../architecture/coordination/cross-agent-recall-isolation.md).
It proves deterministic hard-negative coverage for search/recall/deepen/cache
style surfaces, not enterprise multi-tenant authorization.

### Host Hook Boundary

Provider support is not host hook support. `aippocampus onboard --provider
claude-code`, `aippocampus import conversation --format generic-jsonl`, and MCP
registry operations prove transcript registration or clean-source access only.
They do not install, diagnose, or run host hooks.

Codex-only hook installers are exposed through `aippocampus hooks ...` and the
package owners under `aippocampus_runtime.hooks`.
Their JSON/status output includes `host_integration.host = "codex"` and
`host_integration.config_surface = "codex_hooks_json"`.

Claude Code hook contract status is exposed separately through
`aippocampus hooks claude-code status|dry-run|install|uninstall|smoke`.
`status` and `dry-run` are non-mutating. `install` and `uninstall` are explicit
operator commands that write only AIppocampus-owned `UserPromptSubmit` / `Stop`
handlers or remove those handlers again, while preserving unrelated Claude
settings and unrelated hooks. The surface runs isolated synthetic Claude-shaped
hook JSON without printing raw prompts, transcript paths, session ids, tool
payloads, or settings paths. It does not claim real-host firing,
`PostToolUse` / `PostToolBatch` payload capture, or compaction hook utility.

### Provider Conformance Boundary

The public provider conformance kit is
`benchmarks/aippocampus/benchmark_provider_conformance.py`. It is a development
contract for provider-normalized source behavior, not an end-user runtime API.
The kit verifies that provider suites keep ingestion, MCP/registry access, host
hooks, and configuration-mutating installers as separate status fields. Passing
one surface must not imply another; Claude Code's explicit hook installer proves
only the scoped settings mutation contract, not real host firing or memory
quality.

For new provider integrations, the kit should pass before public docs describe
the provider as supported. A passing suite can support claims about stable
session/thread identity, visible user/final assistant preservation, source-ref
presence, injected/system/tool demotion, sanitized reporting, and known
malformed-row error classes. It does not prove live host compatibility,
all-client drop-in behavior, AgentMemory behavior, or real cross-host continuity
quality.

## MCP Contract

The current MCP tool catalog is read-mostly and intentionally small. The public
tool names are:

- `search_memory`
- `agent_recall`
- `agent_aippo`
- `agent_deepen`
- `agent_explain`
- `recall_context`
- `recall_deepen`
- `recall_diagnostic`
- `latest_reply`
- `get_turn_context`
- `list_threads`
- `register_thread`
- `sync_status`
- `memory_health`
- `list_telepathy_handoffs`
- `deepen_telepathy_handoff`

For these tools:

- Tool names and required input fields are stable. Mutating setup tools may add
  explicit consent-shaped required fields when needed to prevent accidental
  writes.
- `agent_recall` and `recall_context` accept either `query` or `intent`;
  `agent_deepen` accepts either `handle` or `request_index`. The MCP catalog
  exposes these selector contracts as `required_any` so hosts can render useful
  forms without guessing.
- Optional input fields may be added.
- Output fields may be added.
- Tool errors use JSON payloads in MCP `content` text as documented in
  [install-guide.md](install-guide.md).
- `unsupported_mutation` is intentional. The MCP surface should not grow broad
  write APIs just to prove integration.
- Recall outcome feedback remains the explicit CLI/local JSONL lane today; MCP
  does not expose broad `agent feedback` writes.

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
- Retryable registry writer contention during `register_thread` returns
  `registry_writer_busy`, not a generic crash or broad memory-write failure.
- Tool results redact local paths by default. Local operators may request
  private locators only through documented `include_private_paths` fields.

`aippocampus update status --host-probe-report <json>` is the public readiness
bridge from host smokes back into the local status card. It may report
`agent_callable_status: "host_live_probe_ok_current_thread_unverified"` after a
sanitized Codex app-server or Claude Code MCP report proves tool listing plus a
real MCP tool call but the current foreground thread has not separately shown
the agent-native tools. That status is additive host-exposure evidence only; it
does not change the MCP tool schema, imply recall quality, prove current-thread
tool discovery, or promote retrieval/answer claims. Packaged plugin MCP config
uses `aippocampus mcp`; if that command is missing from PATH, status reports
repair options instead of treating the package artifact as foreground
agent-callable.

The plugin readiness portion of `aippocampus update status` is a local operator
contract, not a marketplace API. It may report `local_marketplace`,
`installed_cache`, `auto_detected_installed_cache_count`, and
`plugin_cache_recommended_actions` so an operator can see whether the repo
package, local marketplace copy, and Codex installed cache are separate and
current. `aippocampus update apply --surface plugin` rebuilds the repo-local
package; it refreshes marketplace/cache layers only when
`--plugin-marketplace-dir` or `--plugin-installed-dir` is supplied. Even then,
host reload or reinstall evidence is still separate from package freshness.
`aippocampus plugin install --codex --verify` is the higher-level local install
path that may perform the Codex local marketplace/cache refresh and host probe
directly; it does not enable Codex hooks or configure external-model keys. Use
`aippocampus plugin install --codex --verify --json` for a user-facing
public-safe summary with top-level success, tool count, action-required status,
next action, and warning counts/classes instead of full operator JSON. Use
`--operator-json` for the complete marketplace/cache/host-probe report.
`--compact-json`, `--public`, and `--summary` are equivalent summary aliases.

`recall_context` and `recall_deepen` are the progressive recall navigation
tools. `recall_context` accepts a fuzzy intent or query. Its default MCP result
is a compact foreground receipt: route labels, evidence level, source boundary,
and `routes[].foreground_action`, without raw opaque `aippo-nav:` handles,
source refs, or source windows. Request `detail=full` only for local diagnostic
or follow-through paths that need the short-lived route handle/source selector.
It does not return a final answer or factual memory claim. `recall_deepen`
consumes a route handle, source selector, route object, or ambient navigation
seed and opens the next source-backed layer when the handle is still fresh and
reopenable. Stale, malformed, or non-reopenable handles fail as MCP tool errors
instead of silently becoming evidence.

The minimal agent-native shape over these tools is documented in
[`agent-native-recall-facade.md`](../architecture/recall/agent-native-recall-facade.md):
`recall(query, context) -> MemoryPacket[]`,
`deepen(route_id) -> SourceRoute | SourceBackedEvidence | Blocked | CannotVerify`,
and `explain(route_id) -> WhyRecall | WhyNotRecall`. This is a small
host-facing contract proposal and fixture-backed architecture boundary, not a
public TypeScript/Python SDK, network API, or hosted-service promise. It keeps
full source refs, masks, votes, and proofs behind explicit deepen/explain
surfaces instead of dumping them into every foreground packet.
The sibling AIppo working-contract fixture uses the same boundary: foreground
activation is working posture only, not evidence, and exact/public/disputed or
high-risk claims still go through source reopen.

The first packaged foreground CLI path is:

```sh
aippocampus agent recall "continue the old decision" --json
aippocampus agent recall "continue the old decision" --attention-router --json
aippocampus agent recall "continue the old decision" --attention-router-mode auto --json
aippocampus agent aippo --task "coding issue closeout" --json
aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json
aippocampus agent recall "continue the old decision" --json --detail full
aippocampus agent deepen "<opaque recall handle or deepen:aippo...>" --json
aippocampus agent explain "<opaque recall handle or deepen:aippo...>" --json
aippocampus agent feedback "<route id>" --outcome source_reopen_success --json
```

`agent feedback` is deliberately shown as CLI-only. It may record low-authority
outcome feedback when the user or operator asks for it, but MCP hosts should
not infer an unlisted feedback-write tool from this example.

`agent recall` is a wrapper over the existing progressive
`recall_context -> recall_deepen` path. Human CLI output is compact by default;
CLI `--json` remains a local diagnostic surface. `--public` /
`--compact-json` returns a compact foreground projection with one canonical
`foreground_action`, small route receipts, and no local-private handles. MCP
`agent_recall` uses the same compact-default posture, with the actual MCP tool
name and request index, and keeps opaque follow-up handles out of the default
payload. Full local diagnostics are available in CLI `--json` or MCP
`detail=full`.
It must not inline source refs, message ids, source windows, head votes, masks,
or raw local paths into the foreground packet. `agent aippo` exposes only the narrow
project/workflow working-contract activation. `agent feedback` records or
returns calibration/routing evidence only; it cannot ripen a candidate-only,
Dream-only, or stale clause without source support.

`agent recall --attention-router` is an additive explicit sorting path. It may
reorder already emitted `recall_context` routes through the deterministic
attention router and reports `attention_router_navigation` diagnostics, but it
does not create new source authority, change default hook behavior, or remove
the requirement to use `agent deepen` before exact, current, disputed,
sensitive, or high-risk claims.
`--attention-router-mode auto` is the gated-adoption path: it checks the shared
public-safe promotion harness and enables router sorting only when that harness
allows default adoption. When the gate blocks adoption, recall keeps the
baseline order and reports blocker names under
`attention_router_navigation.policy`. Those blocker names may include
no-help/specificity diagnostics such as
`attention_router_no_help_cases_present`,
`attention_router_specificity_gate_not_satisfied`, and
`attention_router_bridge_reason_gate_not_satisfied`; consumers should treat
them as additive diagnostics, not fatal command errors.

For local diagnostic CLI recall output, pass `deepen_requests[].handle` to
`agent deepen`. `memory_packets[].deepen_route_id` is a display/correlation id,
not the copy-pasteable recall handle. When available, prefer the emitted
`deepen_requests[].copy_paste_command`; for compact public or MCP foreground
output, prefer the request-index path such as
`aippocampus agent deepen --request 1 --recall-selector <emitted-selector>
--json` or the MCP `foreground_action` object. `--last-recall` remains a
same-machine compatibility fallback, but it reads a mutable cache and should
not be taught as the primary foreground path when a selector is available.
When recall has narrowed the candidate route set but the user then remembers
exact wording, use `aippocampus search --from-last-recall "<exact phrase>"
--json` before broad `search --all`; the search remains route selection, and
the matching request still needs `agent deepen` before strong claims.
The usefulness gate treats missing copy-pasteable deepen targets, display-handle
misuse, broad search before recall, and safe route evidence demoted back to
`scent` as foreground usefulness failures rather than harmless diagnostics.

The foreground size, no-profile-dump, review-needed, and anti-nag budget for
those packets lives in
[`foreground-memory-ux-budget.md`](../architecture/recall/foreground-memory-ux-budget.md).
The companion source-reopen budget lives in
[`source-reopen-budget.md`](../architecture/source/source-reopen-budget.md); it
separates hot bounded-route orientation, warm selected-span verification, and
cold source-court reopen work, and keeps foreground timeout behavior
fail-open-without-claim.
Cross-agent read-path isolation fixtures live in
[`cross-agent-recall-isolation.md`](../architecture/coordination/cross-agent-recall-isolation.md)
and require scope filtering before a packet, route, source handle, cached
summary, or semantic sidecar becomes visible.

Contract v1 continuity domains use this same progressive path. `recall_context`
may return a `continuity_domain` route when a source-trailed working conclusion
matches the cue; the route is still navigation only. `recall_deepen` may then
open the domain brief and representative clean-source trail. Default context
packets must not expose the domain working conclusion body. The read surface
remains MCP/hook friendly: hooks and MCP read existing domain snapshots, but
prompt hooks do not author durable domain events while the user is typing.

Durable event writes have two trusted paths:

- Explicit operator/debug/backfill commands such as
  `aippocampus continuity-domain produce --append` or
  `aippocampus continuity-domain append`. `produce --dry-run` is public-safe by
  default and hashes/redacts domain labels unless local detail is explicitly
  requested. `produce --append` refreshes the existing query-pattern route
  sidecar before candidate generation; `produce --dry-run` does not write
  sidecars unless `--refresh-query-pattern-routes` is explicit.
- Opt-in subconscious job production:
  `--event-salience-gate --continuity-domain-salience-mode report|write_when_enabled`.
  `report` is no-write. `write_when_enabled` translates deterministic
  salience rows into continuity-domain events through the existing append and
  publish path, skips duplicate event ids, and exposes only counts/status in
  public job JSON. `--dry-run` and `--no-write` still suppress writes.

Reviewed, local-offline, external-model generated aliases, and deterministic
salience rows may supply candidate labels or lifecycle events only when their
source refs resolve back to registry clean source; they do not become evidence
owners. `recall_deepen` may follow registry-backed `thread_key` refs, but
blocked, stale, superseded, or retired domains remain non-reopenable as domain
briefs.

`recall_diagnostic` mirrors the CLI why/why-not diagnostic for agent hosts. It
returns cue hashes, reason codes, route ids, counts, safe next action, and
`cannot_claim` boundaries. It is a read-only observability tool; it must not
return raw cue text, raw source text, local paths, or a final memory answer.

`register_thread` is an explicit control-plane operation. It is not a general
memory-write API, and default/empty arguments must not write. Callers must pass
an explicit write shape such as `cwd`, `provider`, and `confirm_write: true`.
The default compact result returns a stable local fingerprint as
`thread_handle`; raw `session:<id>` provider keys are private diagnostic
identifiers, not foreground handles. Concurrent local agents may call it against
the same registry; registry metadata writes are serialized by the same-directory
registry writer lease described in the maintenance reference, while read-only
MCP tools remain lock-free.

### MCP Control-Plane Boundary

Control-plane registration means attaching an existing local conversation source
to the AIppocampus registry so later read tools can find source-backed memory.
For the current public MCP surface, `register_thread` may:

- create or update a registry thread record for the selected provider,
  workspace, and registry root after explicit `confirm_write`;
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
preview first with
`aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json`,
then register only after consent with
`aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl`
for a user-selected exported transcript. Internal registry modules may be used by trusted operators for repair, but they are not the public generic ingest contract.
`register_thread` is for attaching/building the selected current provider
session through the MCP control plane; it is not a generic arbitrary-file
ingest endpoint.

For Codex hook dogfood, registry-wide health may report
`pending_repair`, `stale_ledger_row`, or `blocked_or_unsupported` when the
prompt hook saw a thread but the registry has no durable clean-source entry for
it, or when the row must fail closed. The lightweight reconciliation path is a
trusted-operator fallback, not a public first-run or provider-neutral import
command:

```text
python3 -m aippocampus_runtime.registry.api reconcile-hook-seen --dry-run --json
```

Then rerun without `--dry-run` after reviewing the plan. The command reuses
provider rollout discovery and clean-source registration, defaults to
clean-source-only durability, and runs heavier SQLite/RAG-lite index rebuilds
only when `--build-index` is explicit. It does not treat hook output, warm cache
cards, or sanitized prompt traces as source-backed evidence.

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

New generic import examples should also be covered by the provider conformance
kit before they are promoted as public support. Keep the rows public-safe: the
kit may include fake secret/path strings to verify redaction, but the JSON
report must not emit those strings, raw rows, or absolute locators.

To register an explicit file without relying on provider discovery environment
variables:

```sh
aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --project "Project name" --dry-run --json
aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --project "Project name"
```

The first command validates and previews the target thread key without writing
clean-source artifacts or registry rows. The second command performs the local
registration.

## JSON And Schema Contracts

The stable public data schemas are owned by
[public-core-boundary.md](public-core-boundary.md):

- Canonical source event
- Clean-source chunk
- Source ref
- Knowledge source manifest
- Knowledge claim record
- Knowledge update event
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
the human-facing public matrix for environment configuration; the code-level
registry and no-write report live in
`aippocampus_runtime.config.registry` and `aippocampus doctor config --json`.
Install docs may show examples and the safe [`.env.example`](../../.env.example)
template may point here, but they should not mirror this whole list. "Public"
means documented and stable enough to configure. It does not mean the variable
value is safe to publish.

Remaining host/path compatibility and retired migration-only names are tracked in the
[legacy alias inventory](../architecture/ops/legacy-alias-inventory.md). New setup
docs should use the canonical names below and link that inventory only when
explaining a sunset or Codex-host fallback.

### Environment Configuration Matrix

| Variable / family | Group | Audience | Default / precedence | Sensitivity | Stability |
| --- | --- | --- | --- | --- | --- |
| `AIPPOCAMPUS_REGISTRY_DIR` | Storage and discovery | End users, agents, operators | Exact registry root; first registry lookup choice | Local private path | Public configuration |
| `AIPPOCAMPUS_HOME` | Storage and discovery | End users, agents, operators | Uses `AIPPOCAMPUS_HOME/registry` after exact registry vars | Local private path | Public configuration |
| `CODEX_HOME` | Codex install and legacy storage | Codex users and hook installers | Skill/home discovery; generated registry fallback when no `AIPPOCAMPUS_*` storage var is set | Local private path | Compatibility fallback, not the preferred non-Codex storage API |
| `AIPPOCAMPUS_GENERIC_IMPORT_DIR` | Generic JSONL onboarding | Integrators testing provider-neutral import | Optional default import file/dir when CLI args omit a source | Local private path | Public convenience configuration |
| `AIPPOCAMPUS_VAULT`, `AIPPOCAMPUS_STYLE_SOURCE`, `AIPPOCAMPUS_SCRIPT_SOURCE`, `AIPPOCAMPUS_SITE_MARK`, `AIPPOCAMPUS_SITE_TITLE` | Vault projection | Local operators publishing their own memory view | Optional; CLI defaults apply when unset | Local path/content branding may be private | Public operator configuration |
| `AIPPOCAMPUS_OBJECT_STORE_URL`, `AIPPOCAMPUS_OBJECT_PREFIX`, `AIPPOCAMPUS_OBJECT_PROVIDER`, `AIPPOCAMPUS_OBJECT_BUCKET`, `AIPPOCAMPUS_OBJECT_REGION`, `AIPPOCAMPUS_OBJECT_ACCOUNT_ID` | Object-storage sync | Operators configuring HTTP, S3-compatible, R2, or GCS XML sync | CLI flags override; provider defaults apply where documented | Endpoint/account/prefix may reveal infrastructure | Public sync configuration |
| `AIPPOCAMPUS_OBJECT_STORE_TOKEN`, `AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID`, `AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY`, `AIPPOCAMPUS_OBJECT_SESSION_TOKEN` | Object-storage credentials | Operators configuring managed object storage | Read only when the selected provider needs credentials | Secret credential material | Public variable names; values must never be logged or published |
| `AIPPOCAMPUS_AGE_BIN`, `AIPPOCAMPUS_AGE_KEYGEN_BIN` | Encrypted sync tooling | Operators whose GUI shell does not inherit `PATH` | Preferred before `PATH` lookup for the relevant `age` binary | Local executable path | Public operator configuration |
| `AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS`, `AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT`, `AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY`, `AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS`, `AIPPOCAMPUS_SEMANTIC_GATE` | Hook budgets, aggregate skip telemetry, and semantic recall | Local operators tuning hook latency, false-negative calibration, and semantic gating | Built-in conservative budgets; aggregate skip telemetry enabled by default and disabled with `0` / `false` / `off` / `no` | Timing policy and aggregate skip counts may reveal local workflow shape; raw prompt text must not be logged | Public operator configuration |
| `AIPPOCAMPUS_SEMANTIC_TIMEOUT`, `AIPPOCAMPUS_SEMANTIC_TEMPERATURE`, `AIPPOCAMPUS_SEMANTIC_CACHE_TTL`, `AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT`, `AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT` | Semantic recall diagnostics | Trusted local operators and repo tests | Used by semantic recall helpers when explicit config is absent | May affect private prompt/model behavior | Diagnostic/operator configuration; prefer explicit config in new integrations |
| `AIPPOCAMPUS_WARM_RECALL_TIMEOUT`, `AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT`, `AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS`, `AIPPOCAMPUS_WARM_RECALL_BACKGROUND`, `AIPPOCAMPUS_DETACHED_WARM_TIMEOUT`, `AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_SCOUTS`, `AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_DELAY` | Warm ambient recall limits | Local operators tuning background recall cost and latency | Built-in defaults; explicit CLI/config should own product tuning | Timing/concurrency policy may reveal local workflow shape | Public operator configuration for limits only |
| `AIPPOCAMPUS_DEEPSEEK_API_KEY`, `AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL`, `AIPPOCAMPUS_DEEPSEEK_PRO_MODEL`, `AIPPOCAMPUS_DEEPSEEK_BASE_URL` | Optional DeepSeek route | Operators enabling optional external-model work | DeepSeek defaults where unset; provider-native env names are not built-in fallbacks | API key is secret; base URL/model may reveal provider choice | Public optional route configuration; external-model features remain optional |
| `AIPPOCAMPUS_OPENAI_COMPAT_ROUTE`, `AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER`, `AIPPOCAMPUS_OPENAI_COMPAT_MODEL`, `AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL`, `AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV`, `AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING`, `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT`, `AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING`, `AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT`, `AIPPOCAMPUS_OPENAI_COMPAT_REASONING_CONTENT_HANDLING`, `AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND` | Optional OpenAI-compatible route | Operators testing provider portability | Only active when a complete compatible route is configured; DeepSeek-only extensions are omitted unless the route explicitly opts in | API-key variable name and base URL may reveal provider setup; referenced key value is secret | Public optional route configuration |
| `AIPPOCAMPUS_SUBCONSCIOUS_HOOK`, `AIPPOCAMPUS_SUBCONSCIOUS_CONCURRENCY`, `AIPPOCAMPUS_SUBCONSCIOUS_JOB_CONCURRENCY`, `AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB`, `AIPPOCAMPUS_CONTINUITY_DOMAIN_PRODUCTION` | Subconscious/background jobs and opt-in continuity-domain production | Trusted local operators and repo-maintenance smokes | Conservative defaults; continuity-domain production defaults to `off` and accepts `report` or `write_when_enabled` only after the runner is configured | May reveal private background-work policy and local continuity-maintenance policy | Diagnostic/operator configuration, not a broad hosted-service API |
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
- `aippocampus doctor config --json` reports registered `AIPPOCAMPUS_*`
  configuration names, owners, stability buckets, defaults, sensitivity, and
  presence-only effective state. It is no-write and never prints values, local
  paths, provider endpoints, account IDs, buckets, raw prompts, source snippets,
  registry rows, rollout paths, or hook/debug payloads.
- `aippocampus doctor provider --json` checks whether the selected model
  route's API-key environment variable is visible to the current process and a
  child process. This is a presence-only check: it does not read or validate the
  key value, so it cannot prove the key is non-empty, correct, or unexpired. It
  does not read `.env` files, credential stores, or keychain entries, it never
  prints key values, and it does not claim to inspect a previously started Codex
  Desktop hook process. JSON output names this surface `provider_env`; use
  `--provider-env-var` to override the selected route variable name for local
  diagnostics.
- `aippocampus doctor provider --discover-credential-sources --credential-dotenv <path> --json`
  is an alternate operator diagnostic for cases where a key exists outside the
  current process environment or the user explicitly chooses a private file. It
  reads only user-specified `.env` files and the current process env, reports
  public candidate shape and optional validation status, omits local paths by
  default, and never prints secret values. It does not change runtime behavior
  or install hook wrappers. `--validate-credentials` may probe the selected
  route's models endpoint, but only over HTTPS or loopback HTTP.
- `aippocampus onboard provider-key --plan|--apply|--undo --target codex-hooks`
  is the explicit provider-key bridge surface. If `doctor provider` can already
  see the selected env var in the current and child process, the normal plan is
  `--source visible-env-key --provider-env-var <NAME>`; apply records only the
  env-var source metadata and restart boundary. Apply writes only a local
  AIppocampus-owned hook wrapper plus manifest and updates Codex hook commands
  to call that wrapper; secret values are never printed, hashed, validated,
  or written to public JSON, `hooks.json`, or the manifest. Supported alternate
  source names are `explicit-dotenv`, `macos-keychain`,
  `windows-credential-manager`, and `linux-secret-service`; each requires
  explicit locator flags and is outside normal provider doctor discovery. This
  prepares future/restarted Codex hook processes only, and they are ready only
  when launched from an environment with the same variable visible.
- `aippocampus health --json` and
  `aippocampus onboard --status --json` expose path-free `legacy_aliases`
  diagnostics for remaining host/path compatibility. New setup examples should still use
  the canonical `AIPPOCAMPUS_*` names and link the legacy inventory only when
  explaining sunset or Codex-host behavior.

Registry storage precedence remains explicit:

1. `AIPPOCAMPUS_REGISTRY_DIR`: exact registry root.
2. `AIPPOCAMPUS_HOME/registry`: provider-neutral AIppocampus home.
3. `CODEX_HOME/aippocampus-registry`, or the default Codex home path if no
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
| Trusted-process runtime helpers | Documented package owners such as `aippocampus_runtime.hooks.*`, `aippocampus_runtime.onboarding.*`, `aippocampus_runtime.artifacts.*`, `aippocampus_runtime.registry.api`, `aippocampus_runtime.sync.encrypted.admin`, and `aippocampus_runtime.cli.facade.run_command` | Repo-owned tools, plugin packaging, local diagnostics, and trusted operators need in-process execution without subprocess output pollution | Compatibility outside the documented owner module, raw private diagnostics as public schemas, or use across an untrusted process boundary |
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
- Internal retrieval helpers under `aippocampus_runtime.recall`; their outputs
  are policy diagnostics and ranking hints, not stable public schemas or source
  truth.
- Typed capability manifest helpers under
  `aippocampus_runtime.knowledge.capability_types`; their fixture and tests
  prove the current internal execution-boundary prototype, not a public
  capability-manifest schema.
- High-risk answer-gate helpers under
  `aippocampus_runtime.knowledge.answer_gate`; their fixture and tests prove the
  staged deterministic contract prototype, not live high-risk answer coverage.
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
