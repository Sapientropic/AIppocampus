# Memory-System Pain Taxonomy

Role: exploratory research and fixture source map.
Status: public issue / user-feedback taxonomy checked 2026-05-30; use as input
for public-safe fixtures, not as a current competitor scorecard.

Checked date: 2026-05-30.

This note turns public Mem0, Graphiti/Zep, Letta, and Hacker News feedback into
AIppocampus validation categories. It is not a competitor scorecard. Each item
is treated as public issue evidence or user feedback, not as a universal claim
about the referenced project.

## Rolling Public Incident Corpus

Cadence: 3-day rolling sweep while AIppocampus is in public-readiness and
benchmark-hardening mode; manual runs are also appropriate before upgrading a
benchmark or readiness claim.

Scope: public metadata and short failure-class summaries only. Do not collect
raw user secrets, private traces, full issue bodies, or competitor scorecards.
Each row should keep enough shape to build a synthetic negative-control check:
`repo`, `issue`, `checked_date`, `status`, `symptom`, `trigger`,
`affected_surface`, `agent_or_user_visible_failure`,
`AIppocampus_equivalent_risk`, `existing_guard_or_issue`, and
`synthetic_check_candidate`.

Checked date: 2026-06-17.

| Source | Public symptom class | AIppocampus equivalent risk | Existing guard or issue |
|---|---|---|---|
| [rohitg00/agentmemory#843](https://github.com/rohitg00/agentmemory/issues/843) | Data loss on restart / shutdown-flush ordering. | Interrupted write or missing last-known-good recovery. | #2197 interrupted writes; sync/update rollback work. |
| [rohitg00/agentmemory#926](https://github.com/rohitg00/agentmemory/issues/926) | MCP save/recall path silently drops `project`. | Scope propagation loss across MCP / CLI / plugin boundaries. | Registry/sync path contracts and foreground recovery-card tests. |
| [rohitg00/agentmemory#930](https://github.com/rohitg00/agentmemory/issues/930) | Multi-byte UTF-8 corruption on large import / observe payloads. | Import/source-cleaning round trip can corrupt multilingual clean source. | Clean-source UTF-8 fixtures and material-class sanitizer contract. |
| [rohitg00/agentmemory#911](https://github.com/rohitg00/agentmemory/issues/911) | Remember skill stores user secrets verbatim. | Secret-like content enters durable memory or public projection. | Public-safe redaction, self-note rejection, source material classification. |

## Source Signals

| Source | Public signal | Status when checked |
|---|---|---|
| [Mem0 #4573](https://github.com/mem0ai/mem0/issues/4573) | Audit report claiming most stored entries were junk. | Open, updated 2026-05-16 |
| [Mem0 #4099](https://github.com/mem0ai/mem0/issues/4099) | Empty message payload reportedly created hallucinated memories. | Open, updated 2026-03-24 |
| [Mem0 #3009](https://github.com/mem0ai/mem0/issues/3009) | Fact extraction reportedly returned empty results inconsistently. | Closed, updated 2026-03-19 |
| [Mem0 #4926](https://github.com/mem0ai/mem0/issues/4926) | Request for type-aware retrieval and deterministic persistent memory. | Open, updated 2026-05-09 |
| [Mem0 #5055](https://github.com/mem0ai/mem0/issues/5055) | Metadata key round-trip issue in the TypeScript SDK. | Open, updated 2026-05-04 |
| [Graphiti #1516](https://github.com/getzep/graphiti/issues/1516) | Large episode ingestion latency and request for skip-extraction. | Open, updated 2026-05-28 |
| [Graphiti #1262](https://github.com/getzep/graphiti/issues/1262) | Bulk ingestion latency report. | Open, updated 2026-02-23 |
| [Graphiti #1275](https://github.com/getzep/graphiti/issues/1275) | Node resolution reported as O(n) context growth at scale. | Open, updated 2026-02-26 |
| [Graphiti #760](https://github.com/getzep/graphiti/issues/760) | Hallucination / invalid structured-output report. | Open, updated 2025-11-17 |
| [Graphiti #1193](https://github.com/getzep/graphiti/issues/1193) | Request for custom extraction and lower LLM costs. | Open, updated 2026-02-04 |
| [Letta #3270](https://github.com/letta-ai/letta/issues/3270) | Sliding-window compaction reportedly performed a full wipe. | Open, updated 2026-05-22 |
| [Letta #3242](https://github.com/letta-ai/letta/issues/3242) | Redundant compaction passes from inflated token estimate. | Open, updated 2026-05-26 |
| [Letta #3279](https://github.com/letta-ai/letta/issues/3279) | Summarizer context-limit issue during compaction. | Open, updated 2026-05-25 |
| [Letta #3116](https://github.com/letta-ai/letta/issues/3116) | Request for archival-memory deduplication and consolidation. | Open, updated 2026-05-15 |
| [HN item 46891715](https://news.ycombinator.com/item?id=46891715) | User discussion distinguishing fact storage from learned patterns. | Live page checked 2026-05-30 |
| [AIppocampus #987](https://github.com/Sapientropic/AIppocampus/issues/987) | Hand-edited Markdown memories, topic notes, and generated summaries can drift away from clean source. | Internal issue opened 2026-06-08 |

## Pain Categories

| Pain category | Public evidence | AIppocampus status | Validation implication |
|---|---|---|---|
| Write-time pollution | Mem0 #4573, #4099 | Implemented public-safe fixture: prompt-only and auto-hook pollution reports keep boot text, tool traces, empty/run-id messages, transient task state, and recalled-context echoes below source evidence. | Keep transcript/write-path pollution fixtures as authority-boundary checks, not live competitor or full lifecycle write-path claims. |
| Extraction omission or inconsistency | Mem0 #3009 | Designed/partly implemented: source-backed recall can still open clean source when extraction misses. | Benchmarks should separate extraction quality from retrieval over source rows. |
| Deterministic memory vs fuzzy recall | Mem0 #4926, HN discussion | Implemented boundary: retained durable summaries, ambient scent, and source-backed evidence are separate surfaces. | Fixtures should check deterministic/persistent preferences are not merged with fuzzy contextual hints. |
| Metadata/provenance round-trip | Mem0 #5055 | Implemented principle: stable source ids and privacy boundaries are required in reports; not every route is fully covered. | Tests should reject outputs that lose source ids or mutate caller-defined metadata semantics. |
| Eager LLM extraction cost and scale | Graphiti #1516, #1262, #1275, #1193 | Implemented public-safe fixture: the Track B `graph_extraction_boundary` arm models 5KB/50KB canonical docs without foreground graph extraction. | Keep reporting the graph arm as source-index fallback, not graph-memory speed or superiority. |
| Invalid structured extraction | Graphiti #760 | Implemented public-safe fixture: unsupported relations and malformed/duplicate entity rows are downgraded to navigation while clean source remains the evidence route. | Keep generated graph facts advisory unless a source row is reopened. |
| Compaction continuity failure | Letta #3270, #3242, #3279 | Partly implemented in deterministic compaction/lifecycle tests; real long-session Codex smoke remains open in #45. | Fixtures should prove correction, rejected route, accepted decision, and scope narrowing survive simulated compaction. |
| Archival deduplication and consolidation | Letta #3116 | Implemented public-safe fixture: the memory-decision report includes stale/update/delete/dedup hygiene rows that collapse duplicate display without collapsing source provenance. | Keep deduplication as display/routing hygiene; it is not a truth source or physical source deletion mechanism. |
| Editable note-backed memory drift | AIppocampus #987 | Implemented public-safe fixture: the memory-decision report includes Markdown/note drift rows where unsourced or unreopenable notes stay navigation-only, source-backed notes route to reopen, and later clean-source corrections outrank stale notes. | Keep hand-authored and generated notes as navigation layers unless the source trail is reopened or bounded clean-source evidence is available. |
| Pattern learning beyond fact storage | HN item 46891715 | Research/designed: question tracking, frontier markers, and journey tracking target behavior patterns, but Phase 2 is not complete. | Do not claim learned user patterns until source-backed question tracking and correction evidence exist. |

## Negative Cases For Fixtures

These inputs look memory-like but should not become source-backed memory:

- System or boot prompt restating project rules without a user-owned event.
- A recalled memory copied back into the prompt with no new source evidence.
- Empty or near-empty messages that trigger a fabricated profile.
- Transient task state such as "currently running tests" or "waiting for CI".
- A model-generated user trait that is not tied to clean-source support.
- Metadata keys that fail a round trip or lose caller-defined names.
- Large documents that would require foreground LLM extraction before basic
  source-backed retrieval can work.
- Compaction summaries that omit a correction, accepted decision, or rejected
  route while still pretending continuity is complete.
- Hand-edited Markdown notes, topic notes, or generated summaries that lack a
  reopenable source ref.
- Note edits or deletions that remove navigation and then accidentally rewrite
  or delete the original clean-source trail.

## Claim Boundary

- Implemented means current code, tests, benchmark output, or public docs already
  exercise the behavior.
- Designed means the architecture describes the behavior, but implementation or
  proof is still pending.
- Research means the idea is a candidate direction and must not be marketed as a
  current capability.
- Out of scope means AIppocampus should not claim ownership of that system-level
  behavior without becoming a full agent runtime or competitor adapter.

Current AIppocampus claims should stay narrow: source-backed truth, sanitized
reporting, advisory navigation layers, and explicit cannot-claim fields. The
fixtures in #27 should convert this taxonomy into public-safe tests before any
demo or readiness claim is upgraded.
