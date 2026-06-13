# Source-Side Factual Recall

Role: current contract.

AIppocampus may preserve local factual retrieval handles for source material the
user already gave to an agent. Those handles are part of the memory-continuity
promise: strict public redaction must not starve the local runtime of the facts
needed to route back to source.

This contract separates three boundaries:

- local continuity memory may keep source-derived factual aliases and compact
  retrieval handles;
- public reports, committed artifacts, and cloud/provider outputs stay
  aggregate or sanitized;
- factual claims still require source reopen or source-open evidence.

## Artifact Shape

The runtime-local artifact is `source-factual-aliases.jsonl`, usually beside a
clean-source `messages.jsonl`. It is built by
`aippocampus_runtime.source.factual_aliases` and consumed by the prompt hot-path
candidate funnel when a registry entry points at either
`paths.source_factual_aliases_jsonl` or a clean-source messages file with the
default sibling artifact present.

The benchmark source-evidence adapter also builds a richer in-memory/cache
surface in `benchmarks/aippocampus/source_evidence/standard_public.py`; that
surface follows the same navigation-only boundary but is not the only local
artifact contract.

For each source line, the local cache may store:

- stable source refs and line/session fingerprints;
- source-derived route terms;
- `factual_alias_terms`, such as deterministic relation aliases from source
  wording (`stored` -> `kept`, `drawer` -> `location`);
- `answer_bearing_terms` for rows that look like value, preference, currentness,
  contact, location, name, or other factual statements;
- semantic-scope terms when a separate semantic-scope sidecar exists;
- manifest fields for cache policy, builder id, source fingerprint, provider
  call counts, coverage counts, and no-raw-text public boundaries.

The factual alias builder is deterministic and source-local. It must not use
gold answers, expected lines, miss taxonomies, query-time provider calls, or
private-history-only evidence for public claims.

## Hot Path

The hot path can use factual aliases in two places:

- `prompt_recall_hot_path.run_hot_path_funnel()` may match local
  `source-factual-aliases.jsonl` rows and return a navigation-only source ref
  before bounded FTS fallback;
- `search_source_semantic_cache` may match query terms against cached
  profile-level factual aliases before candidate truncation;
- `run_source_semantic_cache_line_reranker` may use factual-alias overlap to
  rank source-visible candidates.

Both stages report provider calls as zero. The output is still a source
candidate route, not an answer. Foreground agents must reopen clean source
before using the selected line as evidence.

## Reporting

Public-safe benchmark reports should distinguish:

- source-index and local artifact cache hits/misses/rebuilds;
- provider prefix-cache telemetry, if any, from AIppocampus local cache reuse;
- factual-alias profile counts and term counts;
- factual-alias evidence coverage;
- factual-alias candidate coverage;
- gold candidate factual-alias/query-overlap counts for fixture or benchmark
  rows where expected source refs are known;
- regressions, latency, and remaining miss families.

Reports must not serialize raw private text, raw local paths, credentials,
secrets, or answer strings into committed output.

## Issue Boundary

This is the source-side factual artifact and hot-path bridge requested by
#1424, #1425, and #1426. It does not close broader LongMemEval or live-history
quality tracks by itself; those require public or shareable benchmark evidence
that candidate coverage, fused top-k, latency, cache behavior, and regressions
improve without weakening source-reopen boundaries.
