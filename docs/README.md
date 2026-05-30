# AIppocampus Docs

This folder holds product direction, architecture notes, dated evidence, and
research context for the public AIppocampus repository. Runtime contracts for
the installable skill live under `skills/aippocampus/references/`.

The installable skill body is intentionally slim: tests live in
`tests/aippocampus/`, benchmark runners in `benchmarks/aippocampus/`, and
repository smoke/docs-maintenance tools in `tools/aippocampus/`.

## Authority Map

- Current product requirements: `roadmap.md`.
- Current public-core license and adapter boundary:
  `public-core-boundary.md`.
- Current public API and stability boundary: `public-api.md`.
- Current Stage 0-5 claim boundary: `stage-0-5-readiness.md`.
- Dated verification ledger: `public-readiness-verification.md`.
- Runtime skill contracts: `skills/aippocampus/SKILL.md` and
  `skills/aippocampus/references/`.
- Exploratory research: `research/README.md`.

Keep long rules, status matrices, and command logs in one authoritative place.
Other docs should link to that place and add only local context.

## Stable Product Direction

- `roadmap.md` - north star, staged roadmap, and release criteria.
- `stage-0-5-readiness.md` - current evidence matrix for completing roadmap
  stages 0 through 5; it is a status snapshot, not the canonical roadmap.
- `architecture-overview.md` - public map of runtime layers and boundaries.
- `runtime-script-map.md` - maintainer map for high-risk runtime scripts,
  entrypoints, callers, dependencies, and public/internal status.
- `public-core-boundary.md` - canonical Apache-2.0 public-core license,
  commercial extension, adapter, schema, and relicensing boundary.
- `public-api.md` - supported CLI, MCP, JSON, environment-variable, and Python
  import stability boundary.
- `install-guide.md` - public skill, MCP, plugin, hook, and local-sync install
  paths.
- `demo-scenarios.md` - public-safe demo flows using synthetic memory data.
- `privacy-security-checklist.md` - public-readiness privacy and security
  review checklist.
- `public-readiness-verification.md` - dated verification ledger. It preserves
  command evidence but is not the canonical status page.
- `memory-decision-benchmark-plan.md` - benchmark design for quiet-by-default
  recall decisions, source fidelity, and payload privacy.
- `memory-pain-fixture-report.md` - public-safe demo/report for memory-system
  pain fixtures and explicit claim boundaries.
- `encrypted-sync-v1.md` - design contract for end-to-end encrypted
  multi-device sync over local folders and object storage.
- `encrypted-sync-follow-up-rfc.md` - follow-up issue/RFC for encrypted sync
  device-key UX and plaintext-to-encrypted migration.
- `object-storage-providers.md` - S3/R2/GCS XML provider setup and
  provider-specific object-storage pitfalls.
- `next-iteration-plan.md` - short handoff for the next development slices.
- `未干的地图.md` - canonical Chinese origin essay; do not mirror its full text
  elsewhere.
- `the-unfinished-map.md` - English transcreation of the origin essay, written
  for English readers rather than as a literal translation.

## Architecture And Implementation Plans

- `cognitive-runtime-architecture.md` - layered runtime architecture and
  cognitive-map direction.
- `runtime-script-map.md` - current ownership/dependency map for installable
  runtime scripts.
- `architecture-debt-register.md` - lightweight large-runtime-script debt
  register and guard budgets.
- `gb-scale-roadmap.md` - long-thread indexing, segmenting, retention, and
  vector-index planning.
- `question-tracking-subconscious.md` - Phase 1 question extraction behavior
  plus Phase 2/3 question tracking and theme-emergence designs.

## Browser Extension (New Direction)

- `browser-extension-design.md` - browser extension concept: LLM-as-brain +
  extension-as-tool-server. Tool call architecture, Claude.ai + ChatGPT technical
  details, multi-agent architecture review (Kimi + Gemini), ChatGPT interception
  feasibility correction, reusable assets from CLI codebase, revised evolution
  path, competitive landscape. Treat external platform/project claims as
  research leads until re-verified from primary sources.

## Research And Positioning

- `research/README.md` - index and evidence map for speculative research notes;
  these notes are not runtime contracts.
- `technical-differentiation-analysis.md` - strategic hypothesis draft. Treat
  claims as positioning until externally sourced.
- `wukong-mining-notes.md` - scoring-fusion and mining notes for long-memory
  retrieval.

## Boundary

Do not place raw rollouts, generated indexes, private anchors, registry exports,
or local-machine paths in this docs folder. Generated memory artifacts belong
in the global `$CODEX_HOME/aippocampus-registry/threads/<thread>/...` store by
default, or in explicit local export/debug paths that stay gitignored.
Public benchmark-corpus scripts and curated samples live in
`benchmark_corpus/`. Keep local caches, generated outputs, benchmark reports,
and private exports out of git unless a future change deliberately promotes a
small public subset with provenance.
