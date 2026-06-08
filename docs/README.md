# AIppocampus Docs

This folder is the public documentation map for AIppocampus. Runtime contracts
for the installable skill live under `skills/aippocampus/references/`; this
folder carries product direction, architecture, guides, evidence, planning, and
research notes.

Start here instead of scanning every Markdown file in the tree.

## Ordinary User Start

For a first recall moment, start with
[`guides/public-api.md#ten-minute-public-path`](guides/public-api.md#ten-minute-public-path)
or [`guides/install-guide.md#first-recall-path`](guides/install-guide.md#first-recall-path).
Those paths check the package, inspect the selected provider, register local
history only after the user is ready, and then search for one source-backed
snippet. MCP, hooks, sync, Dream, benchmark, and release evidence pages are
agent-host, operator, research, or maintainer surfaces; they are not required
before ordinary users see value.

The default product language is import, recall, and carry the source forward.
Use [`roadmap.md#product-layers`](roadmap.md#product-layers) and
[`guides/public-core-boundary.md#core-complexity-budget`](guides/public-core-boundary.md#core-complexity-budget)
before promoting a heavier mechanism into the ordinary user path.

## First Stops

- Product requirements: [`roadmap.md`](roadmap.md).
- Real user-visible continuity examples:
  [`evidence/magic-moments.md`](evidence/magic-moments.md).
- Narrow coding-agent product lane:
  [`guides/coding-agent-memory.md`](guides/coding-agent-memory.md).
- Community evidence and field-report intake:
  [`evidence/community-field-reports.md`](evidence/community-field-reports.md).
- Evidence lane map: [`evidence/README.md`](evidence/README.md).
- Current claim boundary: [`evidence/readiness/stage-0-5-readiness.md`](evidence/readiness/stage-0-5-readiness.md).
- Proof-slice maturity board:
  [`evidence/readiness/proof-slice-maturity.md`](evidence/readiness/proof-slice-maturity.md).
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
- Product profile boundary:
  [`architecture/product-profiles.md`](architecture/product-profiles.md).
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

`architecture/` holds system design, runtime boundaries, implementation maps,
inventories, and active design tracks. Start with
[`architecture/README.md`](architecture/README.md), which classifies each file
by role so current contracts, maps, inventories, and research notes do not look
equally authoritative before you open them.

Most readers should begin with
[`architecture-overview.md`](architecture/architecture-overview.md),
[`product-profiles.md`](architecture/product-profiles.md), and
[`cognitive-runtime-architecture.md`](architecture/cognitive-runtime-architecture.md).
Maintainers should use [`runtime-script-map.md`](architecture/runtime-script-map.md)
and the inventories linked from the folder index, especially
[`legacy-alias-inventory.md`](architecture/legacy-alias-inventory.md) before
touching legacy environment or path aliases.
Keep [`path-identity.md`](architecture/path-identity.md) and
[`clean-source-redaction-profiles.md`](architecture/clean-source-redaction-profiles.md)
directly reachable here because they anchor broader regression families across
runtime path identity and clean-source redaction behavior.

### Guides

`guides/` is for user-facing setup, public boundaries, and operational how-to
material. Start with [`guides/README.md`](guides/README.md) when choosing
between install, API, coding-agent, ecosystem, release, and community paths.

- [`install-guide.md`](guides/install-guide.md) - public skill, MCP, plugin, hook, and local-sync install paths.
- [`coding-agent-memory.md`](guides/coding-agent-memory.md) - narrow
  source-backed continuity lane for Codex/Claude-style agent work, with demo
  path, evidence drawer, and recommendation boundary.
- [`claude-code-mcp.md`](guides/claude-code-mcp.md) - Claude Code MCP setup, provider onboarding states, and privacy boundary.
- [`public-api.md`](guides/public-api.md) - 10-minute dependency path plus supported CLI, MCP, JSON, environment-variable, SDK, and Python import stability boundary.
- [`safe-environment.md`](guides/safe-environment.md) - `.env.example`, plugin MCP env inheritance, and isolated-runtime deferral/substitute smoke boundary.
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
evidence, and claim boundaries. Start with [`evidence/README.md`](evidence/README.md)
to choose between current claims, product/human evidence, benchmark maps, and
dated ledgers. Keep raw JSON reports and private case packs out of git. The
root keeps only navigation and small cross-cutting evidence pages; most
detailed evidence pages are grouped by purpose: `readiness/`, `benchmarks/`,
`dream/`, and `question/`.

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
- [`dream-private-large-history-diagnostic-2026-06-04.md`](evidence/dream/dream-private-large-history-diagnostic-2026-06-04.md) - sanitized #158/#164 private-history Dream diagnostic evidence and root-cause notes.
- [`dream-live-shadow-ab-2026-05-30.md`](evidence/dream/dream-live-shadow-ab-2026-05-30.md) - live shadow A/B dream-worker reminder evidence.
- [`question-extraction-axis-coverage-2026-05-31.md`](evidence/question/question-extraction-axis-coverage-2026-05-31.md) - #153 question extraction axis coverage evidence.

### Planning

`planning/` holds active handoff material, follow-up RFCs, and positioning
drafts. Start with [`planning/README.md`](planning/README.md); treat this folder
as useful context, not the final claim boundary.

- [`next-iteration-plan.md`](planning/next-iteration-plan.md) - short handoff for upcoming development slices.
- [`agent-discoverability-release.md`](planning/agent-discoverability-release.md) - agent-readable context, one-command install, MCP Registry, and recommendation snippet release plan.
- [`standalone-binary-packaging.md`](planning/standalone-binary-packaging.md) - follow-up plan for Python-free binary tooling candidates and cross-platform smoke matrix.
- [`encrypted-sync-follow-up-rfc.md`](planning/encrypted-sync-follow-up-rfc.md) - follow-up issue/RFC for encrypted sync device-key UX and plaintext-to-encrypted migration.
- [`technical-differentiation-analysis.md`](planning/technical-differentiation-analysis.md) - strategic hypothesis draft. Treat claims as positioning until externally sourced.

### Research

`research/` is the index and evidence map for speculative research notes. These
notes are not runtime contracts. Long-range ideas that should be preserved but
not treated as active roadmap or open issue work belong in
[`research/seeds/`](research/seeds/).

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
