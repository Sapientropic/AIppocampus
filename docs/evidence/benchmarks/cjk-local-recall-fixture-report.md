# CJK Local Recall Fixture Report

Date: 2026-06-07.

This public-safe fixture measures a small local-retrieval quality slice for
Chinese and mixed Chinese/code cues. It is a deterministic regression fixture,
not a broad Chinese recall benchmark.

Command:

```powershell
python benchmarks\aippocampus\benchmark_fts5_recall.py --public-cjk-fixture --json
```

## Fixture Shape

The fixture builds a temporary local SQLite/RAG-lite index from synthetic public
messages and reports six cases:

- exact Chinese phrase recall
- two-character CJK cue recall
- mixed Chinese plus code/tooling cue
- deictic cue such as "上次" / "那个" plus a specific source clue
- mild paraphrase with overlapping lexical anchors
- negative generic cue that should not wake unrelated rows

The comparison modes are:

- `fts5_trigram`: SQLite FTS5 trigram over current split query terms.
- `hybrid_without_rag_chunks`: current lexical FTS plus LIKE fallback without
  RAG-lite chunks.
- `production_hybrid`: current default lexical-structural local retrieval with
  RAG-lite enabled.
- `candidate_cjk_sidecar`: measured-only lightweight CJK query chunks. This is
  not default behavior.

## 2026-06-07 Result

The checked-in fixture passed:

- `production_hybrid`: 5/5 positive top-5 hits; 0 negative false positives.
- `hybrid_without_rag_chunks`: 5/5 positive top-5 hits; 0 negative false
  positives.
- `fts5_trigram`: 2/5 positive top-5 hits; 0 negative false positives.
- `candidate_cjk_sidecar`: 5/5 positive top-5 hits; 0 negative false
  positives.

## Claim Boundary

Can claim:

- The default local lexical-structural path is measured against a focused
  public CJK fixture.
- The fixture distinguishes exact, short-cue, mixed-code, deictic, paraphrase,
  and negative-control behavior.
- Lightweight CJK sidecar terms can be measured before any default behavior
  change.

Cannot claim:

- broad Chinese recall quality
- full semantic Chinese search from trigram FTS alone
- dense vector retrieval as a default path
- private-history CJK quality
- a requirement for heavyweight tokenizers, embeddings, GPU, or external vector
  databases
