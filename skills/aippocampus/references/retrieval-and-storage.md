# Retrieval And Storage

This reference owns the memory surfaces and search contracts. Keep operational
details here instead of expanding `SKILL.md`.

## Clean Source

`scripts/build_clean_source.py` creates the daily-use source layer under
`.aippocampus/clean-source/`.

Clean source keeps:

- user messages
- assistant `final_answer` messages
- the last assistant commentary only when a turn has no final answer
- source session id, line spans, turn index, phase, timestamps, and hashes
- stable join keys such as `source_id`, `turn_id`, `message_id`, and
  `content_sha256`

Clean source drops:

- tool calls and tool outputs
- app/event envelopes
- injected instructions
- duplicate visible messages
- routine commentary when a final answer exists
- attachment carrier payloads that are not visible message text

This layer may omit noise, but it must not rewrite expression. Use
`search_clean_source.py` first for normal recall. Return to raw rollout for
forensic audit, missing tool output, storage accounting, or source repair.

Schema upgrades should be rebuildable. Do not put embeddings, DWM state, or
debug provenance into `messages.jsonl`; use sidecars joined by `message_id` or
`turn_id`.

## Local Index

`scripts/build_index.py` writes `.aippocampus/messages.jsonl`,
`.aippocampus/source_index.sqlite`, `.aippocampus/graph.json`, RAG-lite chunks,
and `.aippocampus/manifest.json`.

Default retrieval is local hybrid search:

- SQLite FTS5 trigram search for Chinese, mixed prose, and fuzzy literal clues.
- Anchor matching for durable titles, keywords, and preserved phrases.
- RAG-lite chunks for neighborhood recall before returning to source lines.
- Phase-aware scoring that boosts user messages and `final_answer`, while
  keeping commentary as lower-priority process evidence.
- Diversity ranking so later recaps do not crowd out original turns.

Use `--mode literal` only for chronological/debug behavior. Use `--diversity
none` when inspecting pure score order.

## Turn-Level RAG-Lite

RAG-lite chunks live in the same SQLite file. They store message spans, rollout
line spans, anchor titles, extractive summaries, local text, and sparse lexical
vectors.

When turn metadata is available, chunks prefer the user request plus
`final_answer`; commentary is fallback only when no final exists. Answers should
cite source message lines or anchors, not chunk summaries.

This is not a semantic embedding backend. Embeddings can be added later as an
optional adapter for very fuzzy queries or large corpora.

## Segmented Retrieval

For hundred-MB or GB threads, use segments:

- `build_segments.py` creates sealed `seg-0001/`, `seg-0002/`, etc. under
  `.aippocampus/segments/`.
- Each segment has its own `messages.jsonl` and `source_index.sqlite`.
- The segment manifest records source rollout size/mtime, anchor hash, byte
  spans, line spans, message spans, and index paths.
- `search_segments.py` fans queries out to segments, retrieves top candidates
  per segment, and merges global top-k with diversity penalties.

Segment-local ids collide by design. Treat `(segment_id, id, line)` as the hit
key.

## Global Registry

`scripts/registry.py` is the machine-wide discovery layer. It stores where
thread memories live; it is not a duplicate of every thread.

Default registry files under `$CODEX_HOME/aippocampus-registry/` include:

- `threads.json` and `threads.md`
- `associations.json`
- `concept_index.sqlite`
- `semantic_triggers.jsonl`
- `semantic_recall_cache.json`
- `working_memory.jsonl`
- `subconscious_edges.jsonl`, `subconscious_jobs.jsonl`,
  `promotion_candidates.jsonl`
- `subconscious_state.json` and `subconscious_scheduler.log`

Common commands:

- `python ...\registry.py register --cwd "$PWD" --build-index`
- `python ...\registry.py register-rollout --rollout "<rollout.jsonl>" --project "<label>"`
- `python ...\registry.py scan-sessions --dry-run`
- `python ...\registry.py list`
- `python ...\registry.py search "terms"`
- `python ...\registry.py search --metadata-only "terms"`

In a new thread, check the registry before saying old memory is unavailable.

## Associations And Concept Graph

`build_associations.py` reads registry rows and indexes to create prompt-hook
associations. Curated anchors and keywords are `verified`; automatically mined
final-answer terms are `staging`. Trivial utterances, repeated Goal/system text,
and injection noise should be filtered before they become triggers.

`build_concept_graph.py` creates a bounded concept graph. Depth-1 expansion may
use staging edges; depth-2 expansion is restricted to verified or
high-confidence edges and remains scent-only.

## Vault And Dashboard

`sync_vault.py` creates a human-readable memory surface, usually under
`AIPPOCAMPUS_VAULT` when set, otherwise `~/AIppocampus Memory`. Optional
Publish-like shell assets can be supplied with `AIPPOCAMPUS_STYLE_SOURCE`,
`AIPPOCAMPUS_SCRIPT_SOURCE`, `AIPPOCAMPUS_SITE_MARK`, and
`AIPPOCAMPUS_SITE_TITLE`. The older `CODEX_MEMORY_*` names are accepted only as
backward-compatible fallbacks. Generated content should stay inside `Threads/`,
`_dashboards/`, and the named CSS snippet. Do not overwrite user-authored vault
notes.

The dashboard may use vendored `assets/pixi-7.2.4.min.js` and
`assets/d3-7.9.0.min.js`; keep these as local assets so recall does not depend
on a network CDN.

## Graphify Bridge

`prepare_graphify_corpus.py` exports a prepared corpus under
`.aippocampus/graphify-corpus/`: anchors, index metadata, anchor graph, and
chunked transcript Markdown with source provenance.

Run the separate `graphify` skill only when the user wants deeper graph
analysis, community detection, or `GRAPH_REPORT.md`. Keep Graphify output under
the corpus folder's `graphify-out/`.

## Bundles

`export_bundle.py` produces portable thread-memory bundles. Bundles normally
include manifest, handoff, index files, graph, anchors, and raw rollout unless
`--no-raw` is used. `import_bundle.py` extracts the bundle and appends a pointer
to the current workspace's anchors.
