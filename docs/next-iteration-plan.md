# Next Iteration Plan

This is the short handoff for the next development slice after the current
technical-debt baseline. It points to canonical docs instead of duplicating
their full contracts.

## Current Baseline To Preserve

- Public repo boundary: no raw rollouts, registry exports, private anchors,
  generated indexes, or local paths in Git.
- Default generated artifacts live under
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/...`.
- `.aippocampus/` remains explicit compatibility/export/debug output only.
- External-model paths must pass through shared redaction before leaving the
  process.
- Segment rebuilds must preserve the last-known-good manifest and segment dirs
  when a rebuild fails.

## Recommended Next Slices

1. Public readiness hardening
   - Source: `roadmap.md`, Stage 1 and Stage 7.
   - Add install/demo docs, privacy checklist, and public example bundle with
     no private data.
   - Verify by docs health, full tests, and secret/local-path scan.

2. Question tracking Phase 2
   - Source: `question-tracking-subconscious.md`.
   - Implement `question_tracking` only after Phase 1 `question_extraction`
     output has enough source-backed examples.
   - Start deterministic: group existing `question_candidate` findings, add
     dependency ordering, then add model confirmation for borderline links.

3. Vector index protocol
   - Source: `gb-scale-roadmap.md` and `wukong-mining-notes.md`.
   - Define the `QuestionVectorIndex` protocol with a simple local
     implementation before evaluating TurboVec.
   - Keep vectors optional and join every result back to stable source ids.

4. MCP access layer
   - Source: `roadmap.md`, Stage 4.
   - Start read-mostly: `search_memory`, `latest_reply`, `get_turn_context`,
     `list_threads`, and `memory_health`.
   - Keep mutating tools narrow and explicit.

5. Cross-device sync bundle
   - Source: `roadmap.md`, Stage 3.
   - Design around clean source, manifests, registry rows, concept graph
     sidecars, semantic triggers, and working memory.
   - Keep raw rollout sync opt-in and clearly labeled.

## Do Not Start With

- A generic vector database rewrite.
- A cloud service dependency.
- Phase 3 `theme_emergence` or predictive replay before Phase 2 produces stable
  links.
- Any change that treats summaries, findings, or vector neighbors as truth
  without clean-source refs.
