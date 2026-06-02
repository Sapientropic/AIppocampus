# AIppocampus Docs

This folder is the public documentation map for AIppocampus. Runtime contracts
for the installable skill live under `skills/aippocampus/references/`; this
folder carries product direction, architecture, guides, evidence, planning, and
research notes.

Start here instead of scanning every Markdown file in the tree.

## First Stops

- Product requirements: [`roadmap.md`](roadmap.md).
- Real user-visible continuity examples:
  [`evidence/magic-moments.md`](evidence/magic-moments.md).
- Community evidence and field-report intake:
  [`evidence/community-field-reports.md`](evidence/community-field-reports.md).
- Current claim boundary: [`evidence/readiness/stage-0-5-readiness.md`](evidence/readiness/stage-0-5-readiness.md).
- Benchmark and smoke evidence map: [`evidence/benchmark-evidence-map.md`](evidence/benchmark-evidence-map.md).
- Dated verification ledger: [`evidence/readiness/public-readiness-verification.md`](evidence/readiness/public-readiness-verification.md).
- Public API 10-minute path and install surface:
  [`guides/public-api.md`](guides/public-api.md) and
  [`guides/install-guide.md`](guides/install-guide.md).
- Agent-readable context and recommendation boundary: [`agent-context.md`](agent-context.md).
- Public-core license and adapter boundary: [`guides/public-core-boundary.md`](guides/public-core-boundary.md).
- Ecosystem support matrix and claim boundary:
  [`guides/ecosystem-integration-matrix.md`](guides/ecosystem-integration-matrix.md).
- Architecture overview and metaphor claim boundaries:
  [`architecture/architecture-overview.md`](architecture/architecture-overview.md#metaphor-discipline).
- Exploratory research index: [`research/README.md`](research/README.md).

Keep long rules, status matrices, and command logs in one authoritative place.
Other docs should link to that place and add only local context.

## Folder Map

### Agent Context

[`agent-context.md`](agent-context.md) is the compact truth pack for agents that
need to decide whether to recommend, install, compare, or invoke AIppocampus.
It pairs with the root [`llms.txt`](../llms.txt), [`AGENTS.md`](../AGENTS.md),
[`CLAUDE.md`](../CLAUDE.md), and MCP [`server.json`](../server.json).

### Architecture

`architecture/` holds system design, runtime boundaries, and implementation
maps.

- [`architecture-overview.md`](architecture/architecture-overview.md) - public map of runtime layers, boundaries, and claim-bounded metaphors.
- [`cognitive-runtime-architecture.md`](architecture/cognitive-runtime-architecture.md) - layered runtime architecture and cognitive-map direction.
- [`runtime-script-map.md`](architecture/runtime-script-map.md) - maintainer map for high-risk runtime scripts, recall flow, entrypoints, callers, and tests.
- [`project-planning-automation.md`](architecture/project-planning-automation.md) - boundary between issue intake triage and recurring roadmap drift audits.
- [`provider-entrypoint-inventory.md`](architecture/provider-entrypoint-inventory.md) - classified inventory of remaining Codex-specific and provider-aware runtime entrypoints.
- [`architecture-debt-register.md`](architecture/architecture-debt-register.md) - lightweight large-runtime-script debt register and guard budgets.
- [`gb-scale-roadmap.md`](architecture/gb-scale-roadmap.md) - long-thread indexing, segmenting, retention, vector-index, and scale planning.
- [`encrypted-sync-v1.md`](architecture/encrypted-sync-v1.md) - end-to-end encrypted multi-device sync design contract.
- [`question-tracking-subconscious.md`](architecture/question-tracking-subconscious.md) - question extraction, tracking, and theme-emergence designs.
- [`wukong-mining-notes.md`](architecture/wukong-mining-notes.md) - scoring-fusion and mining notes for long-memory retrieval.
- [`browser-extension-design.md`](architecture/browser-extension-design.md) - browser extension concept and platform research leads.

### Guides

`guides/` is for user-facing setup, public boundaries, and operational how-to
material.

- [`install-guide.md`](guides/install-guide.md) - public skill, MCP, plugin, hook, and local-sync install paths.
- [`claude-code-mcp.md`](guides/claude-code-mcp.md) - Claude Code MCP setup, provider onboarding states, and privacy boundary.
- [`public-api.md`](guides/public-api.md) - 10-minute dependency path plus supported CLI, MCP, JSON, environment-variable, SDK, and Python import stability boundary.
- [`dependency-contract.md`](guides/dependency-contract.md) - runtime, optional integration, benchmark, dev, release, and CI caching dependency taxonomy.
- [`public-core-boundary.md`](guides/public-core-boundary.md) - Apache-2.0 public-core license, adapter, schema, third-party asset, and relicensing boundary.
- [`ecosystem-integration-matrix.md`](guides/ecosystem-integration-matrix.md) - ecosystem support status by host family, with smoke status and overclaim boundaries.
- [`demo-scenarios.md`](guides/demo-scenarios.md) - public-safe demo flows using synthetic memory data.
- [`privacy-security-checklist.md`](guides/privacy-security-checklist.md) - public-readiness privacy and security checklist.
- [`release-checklist.md`](guides/release-checklist.md) - repeatable release, tag, coverage, and public-boundary gates.
- [`community-channel-launch.md`](guides/community-channel-launch.md) - go/no-go checklist and moderation/privacy boundary before linking a general community channel.
- [`object-storage-providers.md`](guides/object-storage-providers.md) - S3/R2/GCS XML provider setup and object-storage pitfalls.

### Evidence

`evidence/` is for benchmark design, smoke maps, dated verification, product
evidence, and claim boundaries. Keep raw JSON reports and private case packs
out of git. The root keeps only navigation and small cross-cutting evidence
pages; most detailed evidence pages are grouped by purpose: `readiness/`,
`benchmarks/`, `dream/`, and `question/`.

- [`magic-moments.md`](evidence/magic-moments.md) - short, claim-bounded
  second-user live-use examples that show the felt product value before the
  benchmark wall.
- [`community-field-reports.md`](evidence/community-field-reports.md) -
  public-safe community report intake, curation rules, and Discussion category
  setup boundary.
- [`benchmark-evidence-map.md`](evidence/benchmark-evidence-map.md) - first-stop map for benchmark runners, smoke evidence surfaces, corpus records, and dated-result owners.
- [`benchmarks/design/README.md`](evidence/benchmarks/design/README.md) - benchmark design rationale hub for evaluation philosophy, track-family boundaries, and external comparison analysis.
- [`stage-0-5-readiness.md`](evidence/readiness/stage-0-5-readiness.md) - current evidence matrix for roadmap stages 0 through 5; it is a status snapshot, not the canonical roadmap.
- [`public-readiness-verification.md`](evidence/readiness/public-readiness-verification.md) - dated verification ledger. It preserves command evidence but is not the canonical status page.
- [`longmemeval.md`](evidence/benchmarks/longmemeval.md) - LongMemEval sources, dataset checksums, dedicated runner commands, retrieval-only results, and claim boundaries.
- [`memory-decision-benchmark-plan.md`](evidence/benchmarks/memory-decision-benchmark-plan.md) - benchmark design for quiet-by-default recall decisions, source fidelity, and payload privacy.
- [`memory-pain-fixture-report.md`](evidence/benchmarks/memory-pain-fixture-report.md) - public-safe demo/report for memory-system pain fixtures and explicit claim boundaries.
- [`dream-live-shadow-ab-2026-05-30.md`](evidence/dream/dream-live-shadow-ab-2026-05-30.md) - live shadow A/B dream-worker reminder evidence.
- [`question-extraction-axis-coverage-2026-05-31.md`](evidence/question/question-extraction-axis-coverage-2026-05-31.md) - #153 question extraction axis coverage evidence.

### Planning

`planning/` holds active handoff material, follow-up RFCs, and positioning
drafts. Treat it as useful context, not the final claim boundary.

- [`next-iteration-plan.md`](planning/next-iteration-plan.md) - short handoff for upcoming development slices.
- [`agent-discoverability-release.md`](planning/agent-discoverability-release.md) - agent-readable context, one-command install, MCP Registry, and recommendation snippet release plan.
- [`standalone-binary-packaging.md`](planning/standalone-binary-packaging.md) - follow-up plan for Python-free binary tooling candidates and cross-platform smoke matrix.
- [`encrypted-sync-follow-up-rfc.md`](planning/encrypted-sync-follow-up-rfc.md) - follow-up issue/RFC for encrypted sync device-key UX and plaintext-to-encrypted migration.
- [`technical-differentiation-analysis.md`](planning/technical-differentiation-analysis.md) - strategic hypothesis draft. Treat claims as positioning until externally sourced.

### Research

`research/` is the index and evidence map for speculative research notes. These
notes are not runtime contracts.

### Archive

`archive/` holds historical, superseded, or one-off working material. Start from
[`archive/README.md`](archive/README.md) before using anything there as
evidence. Archived notes are not current contracts.

### Origin Essays

- [`未干的地图.md`](未干的地图.md) - canonical Chinese origin essay; do not mirror its full text elsewhere.
- [`the-unfinished-map.md`](the-unfinished-map.md) - English transcreation of the origin essay, written for English readers rather than as a literal translation.

## Boundary

Do not place raw rollouts, generated indexes, private anchors, registry exports,
or local-machine paths in this docs folder. Generated memory artifacts belong in
the configured AIppocampus registry by default
(`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
`$CODEX_HOME/aippocampus-registry`), or in explicit local export/debug paths
that stay gitignored.

Public benchmark-corpus scripts and curated samples live in
`benchmark_corpus/`. Keep local caches, generated outputs, benchmark reports,
and private exports out of git unless a future change deliberately promotes a
small public subset with provenance.
