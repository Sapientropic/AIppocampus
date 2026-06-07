# huichen/wukong mining notes

Role: research seed.

Source: https://github.com/huichen/wukong

Recommendation for aippocampus: mine concepts, do not adopt the code.
wukong is a dormant (2021) Go full-text search engine. Its concepts are
valuable but AIppocampus now has three search layers that cover the same
ground without a custom engine.

## Current search layers (2026-05)

| Layer | Tool | Capability |
|---|---|---|
| Exact text | SQLite FTS5 (already in use) | BM25, phrase queries, snippet generation |
| Semantic vector | TurboVec (Phase 2 target) | Compressed vector search, filtered allowlists |
| Relational graph | concept graph (already in use) | Shared-neighbor traversal, theme clustering |

No custom search engine needed. The first scoring fusion layer now exists in
`skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`: it blends signals from
all three after candidates join back to stable source ids or source refs.

## Concepts still worth mining

1. Index depth policy
   - Translate `DocIdsIndex / FrequenciesIndex / LocationsIndex` into
     `line-only / BM25-ish frequency / selected location` index modes.
   - Not all clean source needs token-level location indexing. Use the
     cheapest depth that supports the current recall requirement.

2. Scoring contract (first slice implemented)
   - `retrieval_score_fusion.py` defines a `blend()` function that combines
     FTS5/BM25-like text scores, optional vector scores, and concept graph
     proximity into a single ranked result.
   - Weights should be context-dependent: text-heavy for exact recall,
     vector-heavy for question tracking, graph-heavy for theme emergence.
   - Keep ranking policy explicit in one place, not scattered across search
     code.
   - Scores are ranking hints only. Candidates without stable source ids,
     message/turn ids, or source refs are skipped instead of becoming ranked
     memory evidence.

3. Incremental indexing
   - Batch new messages in hook/heartbeat and seal old segments after
     checkpoint capture. The subconscious scheduler already handles this
     pattern.

4. Persistent rebuild semantics
   - Keep raw normalized message data as the replayable source so changes
   in tokenizer, stop words, scoring, or chunking can rebuild indexes.
   - This is already the clean source philosophy: source is truth, indexes
   are derived.

## Concepts no longer needed

- Segment and shard sizing: SQLite handles this internally. TurboVec has
  its own serialized format. No custom sharding required.
- Custom inverted index: SQLite FTS5 provides this.
- Token proximity scoring: concept graph edges and embedding similarity
  provide a more robust proximity signal than token positions.

## Scoring fusion layer

```python
def score(query: str, candidates: list[FindingId],
          context: PhaseContext) -> list[RankedResult]:
    text = fts5_bm25(query, candidates)
    vector = turbovec.search(embed(query), k, allowlist=candidates)
    graph = concept_graph.proximity(candidates)
    weights = dynamic_weights(context)  # text-heavy vs vector-heavy etc
    return blend(text, vector, graph, weights)
```

This is the wukong "custom scoring interface" adapted for AIppocampus's
three-layer search. One function, explicit policy, no custom engine. The first
implementation is internal policy, not a public Python API: callers should
continue to tolerate additive fields and must re-open clean source before
treating a ranked hit as evidence.

## Follow-up questions

- Which scoring blend weights work best for real question_tracking vs
  theme_emergence vs ambient recall traffic?
- Should TurboVec filtered allowlists replace SQL WHERE for candidate
  pre-filtering, or should both coexist?
