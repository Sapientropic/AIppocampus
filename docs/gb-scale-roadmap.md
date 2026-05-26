# GB-scale long-thread roadmap

This roadmap keeps aippocampus useful when a Codex Desktop thread grows
from hundreds of MB to multi-GB. It is a planning contract; implementation
status is called out explicitly so future agents do not mistake desired layers
for finished behavior.

## Current baseline

- Raw rollout JSONL is the source of truth.
- Generated clean source, `source_index.sqlite`, graph metadata, and optional
  segment indexes default to the global thread store:
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/...`.
- `thread-anchors.md` is an optional private/export anchor input, not a public
  repo baseline file. The root file is gitignored.
- The monolithic `source_index.sqlite` stores normalized visible messages,
  FTS5 trigram search, and periodic RAG-lite chunks.
- `$CODEX_HOME/aippocampus-registry/threads/<thread>/index/segments/manifest.json`
  can describe sealed segment indexes built by `build_segments.py`.
  Project-local `.aippocampus/segments/` is explicit compatibility/debug
  output only.
- `search_segments.py` fans a query out across segment SQLite indexes and
  merges top-k hits with source diversity.
- `graph.json` is a lightweight anchor graph.
- The global registry discovers old thread memories from new threads.

## Target architecture

1. Raw archive layer
   - Keep raw rollout immutable and citeable.
   - Add compressed cold copies for old segments when size becomes painful.
   - Never delete raw data by default; pruning must be explicit.
   - Status: first implementation in `retention_report.py` and
     `cold_archive.py`. Live rollout rewriting is intentionally not
     implemented, because Codex Desktop owns the active session file.

2. Segment index layer
   - Split indexes by time, checkpoint, or byte budget instead of letting one
     SQLite file grow forever.
   - Suggested initial budget: 64-128 MB raw rollout per segment, matching the
     practical lesson from search engines that shard size should remain small
     enough for fast rebuild and easy replacement.
   - Store a segment manifest with source byte range, line range, message range,
     anchor digest, and index capabilities.
   - Status: implemented in `build_segments.py`.

3. Query fanout and top-k merge
   - Registry chooses candidate threads.
   - Thread manifest chooses candidate segments.
   - Each segment returns scored hits and chunk hits.
   - A merge layer reranks across segments using source diversity, early-source
     preference, anchor proximity, recency, role, and exact phrase signals.
   - This merge layer is the same scoring fusion contract described in
     `wukong-mining-notes.md` — a single `blend()` function with explicit
     policy, not scattered search logic.
   - Status: first implementation in `search_segments.py`.

4. Tiered lexical depth
   - L0: document ids / line ranges only.
   - L1: term frequencies for BM25-style lexical rank.
   - L2: selected token locations for snippets and phrase/proximity scoring.
   - L3: RAG-lite chunks for neighborhood recall.
   - L4: TurboVec compressed vector index for semantic recall.
     Protocol interface (`QuestionVectorIndex`: add, search, remove, write,
     load) from Phase 2, allowing numpy → TurboVec migration without pipeline
     changes. Covers question_tracking vectors, concept graph node embeddings,
     and clean-source chunk embeddings. TurboVec's data-oblivious quantization
     (no retraining on incremental adds) and kernel-level filtered search
     (allowlist-based six-axis routing) match AIppocampus's long-term scale and
     local-first constraints.

5. Cognitive state routing (Phase 3+)
   - Current fanout selects by thread + segment only. Question tracking adds
     six-axis filtering (what / where / heading / boundary / when / with_whom)
     that should be expressible at the fanout layer, not just post-hoc in the
     merge step.
   - TurboVec filtered search (allowlist at SIMD block granularity) can carry
     six-axis pre-filtering directly into the vector search kernel, avoiding
     the cost of scoring candidates that will be discarded.
   - Status: not yet implemented. Depends on question_tracking (Phase 2) and
     theme_emergence (Phase 3) producing stable source-backed signals first.

6. Maintenance policy
   - Rebuild stale active segments during hook/heartbeat.
   - Seal old segments after checkpoint capture.
   - Refresh Graphify corpus from sealed segment manifests, not raw ad hoc scans.
   - Run full Graphify only when concept navigation is worth the cost.

## Near-term implementation order

1. Add byte-source diagnostics so growth is measurable before optimizing. Done:
   `rollout_size_audit.py`.
2. Add segment manifest format while still writing the current monolithic index.
   Done: global `index/segments/manifest.json`, with project-local
   `.aippocampus/segments/` only when explicitly requested.
3. Add segment builder and query fanout. Done: `build_segments.py` and
   `search_segments.py`.
4. Add cross-segment top-k merge. Done: first diversity-aware merge in
   `search_segments.py`; continue tuning with real recall failures.
5. Add optional compressed raw archive and retention policy. Done:
   `cold_archive.py` plus `retention_report.py`; cleanup remains manual and
   evidence-first.
6. Add vector index via Protocol interface. Define `QuestionVectorIndex`
   protocol (add / search / remove / write / load). Phase 2 starts with numpy
   implementation; TurboVec replaces it when scale warrants. Triggered by
   question_tracking's cross-thread similarity matching — the fuzzy-query gap
   that lexical/RAG-lite recall cannot close.
   Status: protocol defined in `question-tracking-subconscious.md`; implementation
   pending.

## Cross-references

- Scoring fusion contract: `wukong-mining-notes.md`
- Cognitive runtime layers: `cognitive-runtime-architecture.md`
- Question tracking design: `question-tracking-subconscious.md`
- TurboVec evaluation: planned note, no standalone file yet. Current rationale
  lives in this roadmap plus `technical-differentiation-analysis.md`.

## Non-goals

- Do not make Graphify or embeddings required for normal recall.
- Do not store every token location for every raw tool output by default.
- Do not replace human-readable anchors with a machine-only graph.
- Do not treat summaries as truth; always preserve a route back to source lines.
