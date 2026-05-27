# AIppocampus Docs

This folder holds product direction, architecture notes, and research context
for the public AIppocampus repository. Runtime contracts for the installable
skill live under `skills/aippocampus/references/`.

## Stable Product Direction

- `roadmap.md` - north star, staged roadmap, and release criteria.
- `stage-0-5-readiness.md` - current evidence matrix for completing roadmap
  stages 0 through 5; it is a status snapshot, not the canonical roadmap.
- `architecture-overview.md` - public map of runtime layers and boundaries.
- `install-guide.md` - public skill, MCP, plugin, hook, and local-sync install
  paths.
- `demo-scenarios.md` - public-safe demo flows using synthetic memory data.
- `privacy-security-checklist.md` - public-readiness privacy and security
  review checklist.
- `public-readiness-verification.md` - dated verification evidence for the
  current public-readiness slice.
- `memory-decision-benchmark-plan.md` - benchmark design for quiet-by-default
  recall decisions, source fidelity, and payload privacy.
- `next-iteration-plan.md` - short handoff for the next development slices.
- `未干的地图.md` - canonical Chinese origin essay; do not mirror its full text
  elsewhere.
- `the-unfinished-map.md` - English transcreation of the origin essay, written
  for English readers rather than as a literal translation.

## Architecture And Implementation Plans

- `cognitive-runtime-architecture.md` - layered runtime architecture and
  cognitive-map direction.
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
