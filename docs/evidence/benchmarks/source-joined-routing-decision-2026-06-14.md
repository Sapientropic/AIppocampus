# Source-Joined Routing Consumer Decision - 2026-06-14

This public-safe decision report covers GitHub #1370, #1372, and the #309
owner closeout boundary. It is a decision against default vector prefilter
adoption, not a promotion of semantic scores into evidence.

## Decision

- Default: `keep_text_first_source_joined_defaults_and_defer_vector_prefilter`.
- Normal recall: `text_first_lexical_structural`.
- Score fusion: `post_source_join_ranking_hint_only`.
- Vector prefilter: `disabled_by_default`.
- Local embedding adapter: `disabled_by_default`.

The runtime comment beside `ScoreFusionPolicy` records the implementation
boundary: vector and graph weights apply only after the source-join gate. They
do not enable source-free vector hits, local embedding adapters, foreground
model calls, or default vector prefiltering.

## Measured Consumer

Selected path:

- `recall_context -> recall_deepen`
- foreground packet source reopen from the recall navigation comparison fixture
- post-source-join `score_fusion.blend()` calibration as the vector/graph/rerank
  variant, not as a separate evidence authority

The decision builder is:

```powershell
python -m aippocampus_runtime.ops.source_joined_routing_decision --json
```

Focused verification is:

```powershell
python -m pytest tests\aippocampus\test_source_joined_routing_decision.py -q
```

The 2026-06-14 focused run reported:

- cases: `5`
- direct-search source-backed success rate: `1.0`
- direct-search average manual query invention count: `1.4`
- progressive source-reopen follow-through rate: `1.0`
- progressive fail-closed stale-handle count: `1`
- attention-router claim-without-source-reopen count: `0`
- source-ref rejoin rate: `1.0`
- semantic bridge lift count: `2`
- sentinel false-positive rate: `0.0`
- wrong-route drag from sentinel count: `0`
- wrong-stance collision count: `0`
- source-join gate reject count: `1`
- vector-disabled fallback count: `1`
- provider calls: `0`
- foreground embedding calls: `0`
- external model calls: `0`

Latency is recorded as observed local fixture timing in the JSON report. It is
useful for regression shape, not billing or product latency claims.

## Variant Readout

| Variant | Role | Decision |
|---|---|---|
| `text_direct_search_baseline` | Baseline `search_memory` consumer | Baseline only; it still requires manual query invention in vague cases. |
| `current_progressive_recall_consumer` | Agent-facing `recall_context -> recall_deepen` path | Keep as default-safe text-first source route consumer. |
| `attention_router_route_hint_consumer` | Navigation-only route ordering over recall-context routes | Allowed as route hinting; no claim before source reopen. |
| `source_joined_core_sentinel_pool` | Small verifier pool for vague/frontier cues | Allowed as navigation insurance only; candidates are not evidence. |
| `post_source_join_vector_graph_score_fusion` | Score fusion after source join | Allowed after source join; not a vector prefilter or source truth. |

## Guardrails

- Stable source join is required before score fusion.
- Source reopen is required before user-visible factual claims.
- Route hints, graph/topology hints, and vector scores are navigation hints
  only.
- Missing source joins are rejected before ranking.
- Unsupported provider, language, dimension, or vector paths degrade to lexical
  source reopen rather than reporting valid semantic quality.
- Foreground prompt hooks should not make embedding or LLM calls for this path
  by default.

## Public Output Boundary

The #1442 CodeQL follow-up keeps the CLI output on an allowlisted public report
projection. `source_joined_routing_decision` now rejects public JSON/Markdown
output if credential environment variable names, secret-like values, raw source
refs, provider payloads, or local paths are serialized. The report can still
state boolean boundary flags such as `raw_source_refs_serialized=false`; those
flags are not raw refs.

## Closeout

#1370 can close because the report selects a concrete recall consumer, compares
baseline/current/hint/rerank variants, and includes failure, latency, and cost
notes.

#1372 can close because the default/fallback/defer decision is recorded beside
the runtime scoring policy and in this dated evidence report.

#309 can close as a decision issue, not as vector/default promotion. Future
vector, LLM expansion, graph, or rerank experiments should be opened only as
new narrow product-gap issues with public replayable consumer evidence.

## Cannot Claim

- live answer-quality lift
- private-history generalization
- default vector-prefilter safety
- local embedding adapter quality
- universal semantic or graph retrieval quality
- score output as source truth
