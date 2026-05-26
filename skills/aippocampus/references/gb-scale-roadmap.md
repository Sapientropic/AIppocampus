# GB-scale long-thread roadmap

This roadmap keeps aippocampus useful when a Codex Desktop thread grows
from hundreds of MB to multi-GB. It is a planning contract; implementation
status is called out explicitly so future agents do not mistake desired layers
for finished behavior.

## Current baseline

- Raw rollout JSONL is the source of truth.
- `thread-anchors.md` is the compact human-readable recall map.
- `source_index.sqlite` stores normalized visible messages, FTS5 trigram search,
  and periodic RAG-lite chunks.
- `.aippocampus/segments/manifest.json` can now describe sealed
  segment indexes built by `build_segments.py`.
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
   - Status: first implementation in `search_segments.py`.

4. Tiered lexical depth
   - L0: document ids / line ranges only.
   - L1: term frequencies for BM25-style lexical rank.
   - L2: selected token locations for snippets and phrase/proximity scoring.
   - L3: RAG-lite chunks for neighborhood recall.
   - L4: optional embeddings for fuzzy recall when the user remembers a feeling
     but not the words.

5. Maintenance policy
   - Rebuild stale active segments during hook/heartbeat.
   - Seal old segments after checkpoint capture.
   - Refresh Graphify corpus from sealed segment manifests, not raw ad hoc scans.
   - Run full Graphify only when concept navigation is worth the cost.

## Near-term implementation order

1. Add byte-source diagnostics so growth is measurable before optimizing. Done:
   `rollout_size_audit.py`.
2. Add segment manifest format while still writing the current monolithic index.
   Done: `.aippocampus/segments/manifest.json`.
3. Add segment builder and query fanout. Done: `build_segments.py` and
   `search_segments.py`.
4. Add cross-segment top-k merge. Done: first diversity-aware merge in
   `search_segments.py`; continue tuning with real recall failures.
5. Add optional compressed raw archive and retention policy. Done:
   `cold_archive.py` plus `retention_report.py`; cleanup remains manual and
   evidence-first.
6. Add optional embedding adapter only after lexical/RAG-lite recall shows a real
   fuzzy-query gap.

## Non-goals

- Do not make Graphify or embeddings required for normal recall.
- Do not store every token location for every raw tool output by default.
- Do not replace human-readable anchors with a machine-only graph.
- Do not treat summaries as truth; always preserve a route back to source lines.
