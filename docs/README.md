# AIppocampus Docs

This folder holds product direction, architecture notes, and research context
for the public AIppocampus repository. Runtime contracts for the installable
skill live under `skills/aippocampus/references/`.

## Stable Product Direction

- `roadmap.md` - north star, staged roadmap, and release criteria.
- `next-iteration-plan.md` - short handoff for the next development slices.
- `the-unfinished-map.md` - origin essay; do not mirror its full text elsewhere.

## Architecture And Implementation Plans

- `cognitive-runtime-architecture.md` - layered runtime architecture and
  cognitive-map direction.
- `gb-scale-roadmap.md` - long-thread indexing, segmenting, retention, and
  vector-index planning.
- `question-tracking-subconscious.md` - Phase 1 question extraction behavior
  plus Phase 2/3 question tracking and theme-emergence designs.

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
