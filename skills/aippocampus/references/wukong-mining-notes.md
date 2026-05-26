# huichen/wukong mining notes

Source: https://github.com/huichen/wukong

Recommendation for aippocampus: reference and rewrite, do not vendor or
depend on wukong directly.

## Why it is useful

- It is a compact full-text search engine with clear concepts: inverted index,
  BM25, token proximity, custom scoring fields, online add/remove, persistent
  storage, and sharding.
- Its `DocIdsIndex`, `FrequenciesIndex`, and `LocationsIndex` split is a useful
  model for memory-index depth. Store only the data needed for a given recall
  capability.
- Its docs discuss shard tradeoffs and persistent shard sizing, which map well
  to multi-GB Codex rollout indexes.
- Its custom scoring interface is a good pattern for keeping ranking policy
  explicit rather than scattering weights across search code.

## Why not direct adoption

- It is a Go library for a full-text search engine, not a Codex Desktop memory
  skill.
- Last observed push in the evaluated repository evidence was 2021.
- Local `go test ./...` during evaluation passed `core` and `storage` but failed
  in `engine` through a fatal uninitialized-engine path.
- Directly embedding it would add language/runtime complexity while duplicating
  SQLite FTS and current Python helpers.

## Concepts to mine later

1. Index depth policy
   - Translate `DocIdsIndex / FrequenciesIndex / LocationsIndex` into
     `line-only / BM25-ish frequency / selected location` index modes.

2. Scoring contract
   - Define a small scoring interface around exact match, FTS rank, chunk rank,
     anchor proximity, source diversity, recency, role, and checkpoint signals.

3. Segment and shard sizing
   - Prototype 64-128 MB raw-rollout segments, then benchmark rebuild and query
     fanout on real Codex threads.

4. Token proximity
   - Add selected phrase/proximity scoring for anchors, headings, and user
     messages before considering full token-location indexing.

5. Incremental indexing
   - Batch new messages in hook/heartbeat and seal old segments after
     checkpoint capture.

6. Persistent rebuild semantics
   - Keep raw normalized message data as the replayable source so changes in
     tokenizer, stop words, scoring, or chunking can rebuild indexes.

## Follow-up questions

- Should segment boundaries follow raw bytes, message count, checkpoint anchors,
  or all three?
- Which parts of tool output should enter lexical search, and which should stay
  raw-only?
- When should selected token locations be worth the extra index size?
- What score blend best returns an early original statement plus a recent
  operational summary?
