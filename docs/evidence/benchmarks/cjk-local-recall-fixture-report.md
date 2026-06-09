# CJK Local Recall Fixture Report

Date: 2026-06-09.

This public-safe fixture measures a small local-retrieval quality slice for
Chinese and mixed Chinese/code cues. It is a deterministic regression fixture,
not a broad Chinese recall benchmark.

Command:

```powershell
python benchmarks\aippocampus\benchmark_fts5_recall.py --public-cjk-fixture --json
```

## Fixture Shape

The fixture builds a temporary local SQLite/RAG-lite index from synthetic public
messages and reports ten cases:

- exact Chinese phrase recall
- two-character CJK cue recall
- mixed Chinese plus code/tooling cue
- deictic cue such as "上次" / "那个" plus a specific source clue
- mild paraphrase with overlapping lexical anchors
- compact CJK cue without spaces that requires shorter CJK chunks
- mixed English / project-symbol cue
- negative generic cue that should not wake unrelated rows
- negative project-symbol neighbor cue
- negative semantic-alias gap that should not be filled by lexical search

The comparison modes are:

- `fts5_trigram`: SQLite FTS5 trigram over current split query terms.
- `hybrid_without_rag_chunks`: current lexical FTS plus LIKE fallback without
  RAG-lite chunks.
- `production_hybrid`: current default lexical-structural local retrieval with
  RAG-lite enabled.
- `cjk_aware_sidecar`: measured-only lightweight CJK query chunks over the
  local hybrid path. This is not semantic evidence or a default scoring weight.

## 2026-06-09 Result

The expanded checked-in fixture passed with an explicit default-path gap:

- `cjk_aware_sidecar`: 7/7 positive top-5 hits; 0 negative false positives.
- `production_hybrid`: 6/7 positive top-5 hits; 0 negative false positives.
  The miss is the compact no-space CJK cue, which the measured sidecar
  recovers.
- `hybrid_without_rag_chunks`: 6/7 positive top-5 hits; 0 negative false
  positives.
- `fts5_trigram`: 3/7 positive top-5 hits; 0 negative false positives.
- All three negative controls produced 0 false positives across the measured
  modes.

The default gap is intentional evidence, not a hidden failure: FTS5 trigram
alone is still weak for two-character and compact Chinese cues, while the
measured sidecar shows the smallest local-first query-chunk path that can
recover the compact case without adding a tokenizer, embedding model, or
external service.

## Claim Boundary

Can claim:

- The default local lexical-structural path is measured against a focused
  public CJK fixture.
- The fixture distinguishes exact, short-cue, mixed-code, deictic, paraphrase,
  compact no-space, mixed project-symbol, and negative-control behavior.
- Lightweight CJK sidecar terms can recover the expanded fixture's compact
  CJK cue as measured navigation/search terms.

Cannot claim:

- broad Chinese recall quality
- full semantic Chinese search from trigram FTS alone
- that the current production hybrid handles every compact CJK cue
- dense vector retrieval as a default path
- private-history CJK quality
- a requirement for heavyweight tokenizers, embeddings, GPU, or external vector
  databases
