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
  Current main indexes are also copied to
  `generations/gen_*/source_index.sqlite` and selected by
  `source_index.pointer.json`, which falls back to last-known-good if the
  current generation is missing. Legacy `versions/source_index-*.sqlite`
  pointers remain readable for migration.
- `$CODEX_HOME/aippocampus-registry/threads/<thread>/index/segments/manifest.json`
  can describe sealed segment indexes built by `build_segments.py`.
  Project-local `.aippocampus/segments/` is explicit compatibility/debug
  output only.
- `search_segments.py` fans a query out across segment SQLite indexes, can cap
  executable segment fanout before opening SQLite shards, and reports
  planned/searched/skipped segment counts alongside merged top-k hits.
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
  same-directory writer lease, generation index pointer, last-known-good
  fallback, and SQLite backup/WAL stable refresh instead of replacing a live
  `source_index.sqlite` file. Sync/import/export now have explicit generated
  cache rules: default sync excludes SQLite/pointer/generation caches, target
  repair resolves only target-local generated caches, and portable export/import
  reports pointer-resolved current SQLite when a bundle carries one.

Completed foundation:

- `storage_capacity_report.py` measures aggregate source/cache/sync size and
  worst-case and planned fanout without reading private message bodies.
- The default sync bundle policy does not copy generated SQLite indexes as
  mandatory portable source; SQLite, FTS, graph, and semantic/vector sidecars
  remain rebuildable local caches unless a command explicitly exports them.
- `aippocampus_runtime.sync.bundle` now writes clean-source JSONL through a top-level
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
- `search_segments.py --fanout-budget ...` applies an executable per-thread
  segment budget before opening SQLite shards and reports planned, searched,
  skipped, and missing-index counts. `--full-fanout` remains the explicit
  diagnostics/benchmark path. Missing manifests or shard indexes now return
  structured `segments_unavailable` / `build_required` status unless
  `--build-segments` is explicitly requested.
- `aippocampus storage gc --dry-run` starts the storage governance bridge: it
  reports protected source bytes, reclaimable rebuildable/review bytes, and
  candidate safety preconditions from capacity data plus existing retention JSON
  without reading message bodies or deleting files. Capacity and health reports
  now expose main-index generation pointer status, current/LKG ids, old
  generation bytes, pointer load time, publish latency, and plan-only old
  generation GC candidates. `--apply --class rebuildable` still has a narrow
  path-level retention-report v1 for the main `source_index.sqlite` cache, with
  source/ref/lease/active-thread/pointer checks and an eviction manifest;
  capacity aggregates, old generation directories, and broader cache classes
  remain plan-only. If this bridge becomes the first Rust deterministic-core
  slice, it must follow the contract-replay gate in
  `docs/architecture/rust-deterministic-core.md`.

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
   - Status: `search_segments.py` owns the first segment merge, executable
     segment fanout caps, structured unavailable/build-required status, and
     explicit full-fanout diagnostics. The first cross-signal contract now lives in
     `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`; it keeps exact
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
     JSON-backed implementation. It is package-owner only and an adapter
     boundary:
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
     implemented in `aippocampus_runtime.sync.bundle`; first registry-metadata query planner and
     fanout budget reporting are implemented in `storage_capacity_report.py`.
     Executable per-thread segment fanout budgets are implemented in
     `search_segments.py`; report-only capacity planning and actual SQLite
     query planning are intentionally tracked as separate layers. Synthetic
     multi-GB threshold smoke is implemented in
     `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py`; segmented
     index rebuilds now have a single-writer lease and last-known-good recovery.
     Main indexes now have generation pointer publishing for Windows
     locked-file fallback while preserving `source_index.sqlite`
     compatibility. Main-index generation-aware health/capacity reporting and
     plan-only old generation GC candidates are implemented; actual generation
     cleanup still waits for a reader-pin/TTL contract. Segment generation
     directories and segment pointers remain later #581 slices. Default sync
     keeps generated SQLite and pointer files out of the portable source set
     while still repairing target-local rebuilt cache locators.

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
   `search_segments.py`; #375 adds a public-safe calibration fixture and
   report for the current default weights. Continue tuning with real recall
   failures, but keep before/after evidence in
   [`docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md`](../evidence/benchmarks/segmented-merge-policy-fixture-report.md).
5. Add optional compressed raw archive and retention policy. Done:
   `cold_archive.py` plus `retention_report.py`; cleanup remains manual and
   evidence-first. A first governance bridge now lives behind `aippocampus
   storage gc`: dry-run covers capacity plus existing retention evidence, and
   apply v1 covers path-level retention-report eviction of the main rebuildable
   SQLite cache with deterministic source/archive, lease, active-thread,
   pointer, and manifest checks. Segment/Graphify/cache-family expansion remains
   later work.
6. Add vector index via Protocol interface. Done for the first local slice:
   `aippocampus_runtime.question.vector_index` defines `QuestionVectorIndex`
   and `LocalQuestionVectorIndex` with add / search / remove / write / load
   behavior. It is intentionally package-owner only, non-default, and
   source-id-only; question tracking must still re-open clean source before
   accepting a link. TurboVec remains a later
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
   clean-source JSONL through content-addressed chunks, capacity reports now
   include report-only planned fanout under a budget, and `search_segments.py`
   can enforce an actual segment fanout budget before SQLite opens. The
   synthetic multi-GB capacity smoke models warning/blocker thresholds without
   creating large files. Segmented index rebuilds now use `.rebuild.lock`
   single-writer discipline, staged
   publish, and last-known-good restoration. Main indexes now use a
   `source_index.pointer.json` current/LKG generation pointer and stable SQLite
   backup refresh. Capacity/health now report main-index generation GC
   candidates without deleting them; actual cleanup still waits for
   reader-pin/TTL semantics, and segment generation directories remain a later
   slice. Default sync excludes generated SQLite caches and pointer files;
   import/export reports pointer-resolved current SQLite for explicit bundles.
   Broader physical multi-device stress remains a
   release-readiness exercise, not a `quick` or `pr` tier claim.

## Cross-references

- Scoring fusion contract: `wukong-mining-notes.md` and
  `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`
- Cognitive runtime layers: `cognitive-runtime-architecture.md`
- Question tracking design: `question-tracking-subconscious.md`
- TurboVec evaluation: planned note, no standalone file yet. Current rationale
  lives in this roadmap plus `technical-differentiation-analysis.md`.

## Non-goals

- Do not make Graphify or embeddings required for normal recall.
- Do not store every token location for every raw tool output by default.
- Do not replace human-readable anchors with a machine-only graph.
- Do not treat summaries as truth; always preserve a route back to source lines.
