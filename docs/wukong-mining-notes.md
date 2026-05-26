# huichen/wukong mining notes

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

No custom search engine needed. What IS needed is a scoring fusion layer
that blends signals from all three.

## Concepts still worth mining

1. Index depth policy
   - Translate `DocIdsIndex / FrequenciesIndex / LocationsIndex` into
     `line-only / BM25-ish frequency / selected location` index modes.
   - Not all clean source needs token-level location indexing. Use the
     cheapest depth that supports the current recall requirement.

2. Scoring contract (most valuable concept)
   - Define a `blend()` function that combines FTS5 BM25, TurboVec vector
     scores, and concept graph proximity into a single ranked result.
   - Weights should be context-dependent: text-heavy for exact recall,
     vector-heavy for question tracking, graph-heavy for theme emergence.
   - Keep ranking policy explicit in one place, not scattered across search
     code.

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

## Scoring fusion layer (design target)

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
three-layer search. One function, explicit policy, no custom engine.

## Follow-up questions

- When should exact text search take priority over vector search?
  (Hypothesis: when the user quotes their own earlier words verbatim.)
- Which scoring blend weights work best for question_tracking vs
  theme_emergence vs ambient recall?
- Should TurboVec filtered allowlists replace SQL WHERE for candidate
  pre-filtering, or should both coexist?
