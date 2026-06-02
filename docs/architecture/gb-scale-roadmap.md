# GB/TB-scale storage and long-thread roadmap

This roadmap keeps aippocampus useful when a Codex Desktop thread grows from
hundreds of MB to multi-GB, and when the whole registry grows from GB to TB
through many threads, other agent runtime imports, and multi-device sync. It is
a planning contract; implementation status is called out explicitly so future
agents do not mistake desired layers for finished behavior.

## Current baseline

- Raw rollout JSONL is the source of truth.
- Generated clean source, `source_index.sqlite`, graph metadata, and optional
  segment indexes default to the global thread store:
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/...`.
- `thread-anchors.md` is an optional private/export anchor input, not a public
  repo baseline file. The root file is gitignored.
- The monolithic stable `source_index.sqlite` remains the compatibility path.
  Current main indexes are also copied to `versions/source_index-*.sqlite` and
  selected by `source_index.pointer.json`, which falls back to last-known-good
  if the current version is missing.
- `$CODEX_HOME/aippocampus-registry/threads/<thread>/index/segments/manifest.json`
  can describe sealed segment indexes built by `build_segments.py`.
  Project-local `.aippocampus/segments/` is explicit compatibility/debug
  output only.
- `search_segments.py` fans a query out across segment SQLite indexes and
  merges top-k hits with source diversity.
- `graph.json` is a lightweight anchor graph.
- The global registry discovers old thread memories from new threads.
- `storage_capacity_report.py` reports aggregate clean-source bytes, generated
  index bytes, semantic sidecar bytes, current sync-policy bytes, index
  amplification, worst-case SQLite fanout, and planned registry-metadata query
  fanout without reading clean-source message bodies. This is the first
  registry-scale observability layer for issue #4.

## Active track

Issue #4 is accepted as a near-term architecture track, not a far-future
optimization note. The umbrella is now split into implementation slices so the
remaining work is visible instead of hidden behind one broad issue:

- [#11](https://github.com/Sapientropic/AIppocampus/issues/11):
  content-addressed clean-source chunks, delta sync, and explicit generated
  cache export policy.
- [#12](https://github.com/Sapientropic/AIppocampus/issues/12): registry query
  planner, fanout budget, and fallback behavior before segment-level SQLite
  fanout.
- [#13](https://github.com/Sapientropic/AIppocampus/issues/13): synthetic
  multi-GB scale smoke, thresholds, and amplification reporting without private
  data. First CI-safe simulator lives at
  `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py`.
- [#14](https://github.com/Sapientropic/AIppocampus/issues/14): Windows writer
  discipline, interrupted rebuild recovery, and last-known-good index
  preservation. Segment rebuilds now use a same-directory single-writer lease
  plus stale-lock recovery before publishing new SQLite shards.
- [#111](https://github.com/Sapientropic/AIppocampus/issues/111): runtime writer
  coordination for multi-session, multi-agent, cross-device, and
  cross-platform operation. Main index publishing now uses a shared
  same-directory writer lease, versioned index pointer, last-known-good
  fallback, and SQLite backup/WAL stable refresh instead of replacing a live
  `source_index.sqlite` file. Sync/import/export now have explicit generated
  cache rules: default sync excludes SQLite/pointer/versioned caches, target
  repair resolves only target-local generated caches, and portable export/import
  reports pointer-resolved current SQLite when a bundle carries one.

Completed foundation:

- `storage_capacity_report.py` measures aggregate source/cache/sync size and
  worst-case and planned fanout without reading private message bodies.
- The default sync bundle policy does not copy generated SQLite indexes as
  mandatory portable source; SQLite, FTS, graph, and semantic/vector sidecars
  remain rebuildable local caches unless a command explicitly exports them.
- `sync_bundle.py` now writes clean-source JSONL through a top-level
  content-addressed chunk store. The sync manifest carries
  `clean_source_delta.kind=content_addressed_clean_source_chunks`; each logical
  clean-source file records size, whole-file SHA-256, and ordered chunk entries
  with `clean-source-chunks/sha256/<prefix>/<sha256>.chunk` paths. Pull
  rehydrates the logical clean-source files before target-device path repair.
  Raw rollout transfer remains opt-in, and generated cache export remains an
  explicit separate mode.
- Repeated pushes reuse unchanged chunk objects because chunk paths are
  content-addressed and live outside the cleared managed `registry/` and
  `raw-rollouts/` bundle directories. Stale unreferenced chunks may remain in a
  local sync folder, but only files named in the current manifest are uploaded,
  verified, or pulled.
- `storage_capacity_report.py --planner-query ... --fanout-budget ...` exposes
  a first registry-metadata query plan: worst-case SQLite handles, candidate
  thread count, planned thread count, planned handles, fallback reason, and
  budget exhaustion. It narrows using registry/thread metadata first, then still
  joins results back to stable source ids.
- `aippocampus storage gc --dry-run` starts the storage governance bridge: it
  reports protected source bytes, reclaimable rebuildable/review bytes, and
  candidate safety preconditions from capacity data plus existing retention JSON
  without reading message bodies or deleting files. Apply mode remains deferred.

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
   - Status: `search_segments.py` owns the first segment merge. The first
     cross-signal contract now lives in
     `skills/aippocampus/scripts/retrieval_score_fusion.py`; it keeps exact
     text recall text-heavy, allows vector-heavy question-tracking contexts and
     graph-heavy theme contexts, and refuses candidates that cannot join back to
     stable source ids or source refs.

4. Tiered lexical depth
   - L0: document ids / line ranges only.
   - L1: term frequencies for BM25-style lexical rank.
   - L2: selected token locations for snippets and phrase/proximity scoring.
   - L3: RAG-lite chunks for neighborhood recall.
   - L4: TurboVec compressed vector index for semantic recall.
     Protocol interface (`QuestionVectorIndex`: add, search, remove, write)
     starts in `aippocampus_runtime.question.vector_index` with a small local
     JSON-backed implementation. `question_vector_index.py` remains the
     compatibility shim. It is an adapter boundary only:
     vector neighbors carry stable source ids and remain hints until clean-source
     evidence is re-opened. TurboVec can replace the local implementation when
     scale warrants, without changing the caller contract. Future coverage can
     include question_tracking vectors, concept graph node embeddings, and
     clean-source chunk embeddings. TurboVec's data-oblivious quantization (no
     retraining on incremental adds) and kernel-level filtered search
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

7. Registry-scale storage and sync policy
   - Treat raw/audit source and clean source as canonical source surfaces.
   - Treat SQLite, FTS, vector, graph, and semantic sidecars as rebuildable
     local caches unless a command explicitly exports them.
   - Sync source by content-addressed chunks and manifests instead of copying
     large generated indexes or whole clean-source files by default.
   - Add a registry-level query planner that narrows candidate threads, days,
     and segments before opening SQLite files.
   - Status: first content-addressed clean-source chunk/delta sync is
     implemented in `sync_bundle.py`; first registry-metadata query planner and
     fanout budget reporting are implemented in `storage_capacity_report.py`.
     Synthetic multi-GB threshold smoke is implemented in
     `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py`; segmented
     index rebuilds now have a single-writer lease and last-known-good recovery.
     Main indexes now have versioned pointer publishing for Windows locked-file
     fallback while preserving `source_index.sqlite` compatibility. Default
     sync keeps generated SQLite and pointer files out of the portable source
     set while still repairing target-local rebuilt cache locators.

## Near-term implementation order

1. Add byte-source diagnostics so growth is measurable before optimizing. Done:
   `rollout_size_audit.py`.
   Registry-scale diagnostics are now started with `storage_capacity_report.py`,
   which measures aggregate clean source, generated indexes, sync footprint, and
   SQLite fanout without reading private message bodies.
2. Add segment manifest format while still writing the current monolithic index.
   Done: global `index/segments/manifest.json`, with project-local
   `.aippocampus/segments/` only when explicitly requested.
3. Add segment builder and query fanout. Done: `build_segments.py` and
   `search_segments.py`.
4. Add cross-segment top-k merge. Done: first diversity-aware merge in
   `search_segments.py`; continue tuning with real recall failures.
5. Add optional compressed raw archive and retention policy. Done:
   `cold_archive.py` plus `retention_report.py`; cleanup remains manual and
   evidence-first. A first dry-run-only governance bridge now lives behind
   `aippocampus storage gc --dry-run`; eviction apply mode still needs
   deterministic source/archive, lease, active-thread, and manifest checks.
6. Add vector index via Protocol interface. Done for the first local slice:
   `aippocampus_runtime.question.vector_index` defines `QuestionVectorIndex`
   and `LocalQuestionVectorIndex` with add / search / remove / write / load
   behavior; `question_vector_index.py` remains the compatibility shim. It is
   intentionally non-default and source-id-only; question tracking must still
   re-open clean source before accepting a link. TurboVec remains a later
   replacement when scale warrants. A first #138 evaluator in
   `question_index_sidecar.py` can build/reuse an optional SQLite question-index
   cache, detect missing or stale caches, and measure whether lookup candidates
   still join back to current source-backed question rows and source-ref keys;
   it does not make the sidecar a default tracking dependency or store question
   text in the row payload. Its adoption report keeps default prefiltering
   disabled when evidence is synthetic-only, when source-ref-key joins fail,
   when baseline strong-pair coverage is incomplete, or when current pair
   volume is below the cache threshold. The synthetic
   `smoke_question_tracking_scale.py` smoke reports quadratic pair-scan growth,
   sidecar coverage, adoption decision, and privacy boundaries without reading
   private registry content.
7. Add source chunking, delta sync, and registry query planning. Done for the
   first executable slice: local-folder/object-storage sync now moves
   clean-source JSONL through content-addressed chunks, and capacity reports now
   include planned fanout under a budget. The synthetic multi-GB capacity smoke
   models warning/blocker thresholds without creating large files. Segmented
   index rebuilds now use `.rebuild.lock` single-writer discipline, staged
   publish, and last-known-good restoration. Main indexes now use a
   `source_index.pointer.json` current/LKG pointer and stable SQLite backup
   refresh. Default sync excludes generated SQLite caches and pointer files;
   import/export reports pointer-resolved current SQLite for explicit bundles.
   Broader physical multi-device stress remains a release-readiness exercise,
   not a fast-tier claim.

## Cross-references

- Scoring fusion contract: `wukong-mining-notes.md` and
  `skills/aippocampus/scripts/retrieval_score_fusion.py`
- Cognitive runtime layers: `cognitive-runtime-architecture.md`
- Question tracking design: `question-tracking-subconscious.md`
- TurboVec evaluation: planned note, no standalone file yet. Current rationale
  lives in this roadmap plus `technical-differentiation-analysis.md`.

## Non-goals

- Do not make Graphify or embeddings required for normal recall.
- Do not store every token location for every raw tool output by default.
- Do not replace human-readable anchors with a machine-only graph.
- Do not treat summaries as truth; always preserve a route back to source lines.
