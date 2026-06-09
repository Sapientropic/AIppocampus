# Memory Pain Fixture Report

Evidence date: 2026-05-30.

Calibration update: 2026-06-09.

This report summarizes the public-safe fixture evidence added for #27 and used
to satisfy #28. It is a demo/report for AIppocampus claim boundaries, not a
competitor scorecard or leaderboard.

## Source Map

- Taxonomy: [`docs/research/memory-system-pain-taxonomy.md`](../../research/memory-system-pain-taxonomy.md)
- Benchmark plan: [`docs/evidence/benchmarks/memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md)
- Gate runner: [`benchmarks/aippocampus/benchmark_memory_decision_gate.py`](../../../benchmarks/aippocampus/benchmark_memory_decision_gate.py)
- Payload runner: [`benchmarks/aippocampus/benchmark_payload_fidelity.py`](../../../benchmarks/aippocampus/benchmark_payload_fidelity.py)
- Tests:
  [`tests/aippocampus/test_benchmark_memory_decision_gate.py`](../../../tests/aippocampus/test_benchmark_memory_decision_gate.py)
  and
  [`tests/aippocampus/test_benchmark_payload_fidelity.py`](../../../tests/aippocampus/test_benchmark_payload_fidelity.py)

## What Was Demonstrated

The synthetic Track A/C benchmark surface now emits a `memory_pain_fixtures`
summary, an `auto_hook_pollution_fixtures` report for #986's transcript /
write-path pollution boundary, and a `memory_hygiene_fixtures` report for
#990's multi-turn stale/update/delete/dedup boundary. It also emits
`note_memory_drift_fixtures` for #987's hand-edited/generated Markdown memory
drift boundary. The covered public-safe families are:

- `write_time_pollution`
- `recalled_context_feedback_loop`
- `fabricated_profile_no_source`
- `transient_task_state`
- `deterministic_vs_fuzzy_memory`
- `metadata_round_trip`
- `large_document_no_foreground_llm`
- `invalid_structured_extraction`
- `compaction_continuity`
- `markdown_note_memory_drift`

The fixture prompts are synthetic and default reports do not emit raw prompt
text, raw context, snippets, registry exports, local paths, tokens, or cookies.

## Positive Demo Case

The existing exact-quote synthetic case still exercises source-backed recall:
the gate benchmark returns `evidence`, and the payload benchmark verifies that
the expected clean-source line is present. This demonstrates that AIppocampus
can surface evidence when the prompt explicitly asks for a clean-source-backed
quote.

## Negative Demo Cases

The public memory-pain fixtures exercise inputs that look memory-like but are
not clean-source evidence:

- boot/system prompt restatement
- recalled context copied back into the prompt
- model-fabricated profile traits
- transient task state
- fuzzy preference hints
- metadata labels
- large-document ingestion pressure
- invalid structured extraction
- incomplete compaction continuity claims

The #986 auto-hook pollution report adds six synthetic transcript/write-path
cases: boot/system text, tool traces, recalled-context echoes, empty messages
with run ids, transient task state, and agent/host metadata. Each case is
bounded to `direction_only` or `ignore_or_blocked`, with zero durable writes,
zero bounded evidence, zero source-backed facts, and no raw event text in the
default report.

The #990 hygiene report adds six synthetic multi-turn rows covering current,
stale, superseded, duplicate, suppressed, and fuzzy-navigation surfaces.
Duplicate memories collapse in display/ranking while source provenance hashes
remain retained; stale or superseded rows do not outrank a later source-backed
correction as evidence; deleting/suppressing a note does not claim to delete
the original clean-source trail.

The #987 note-drift report adds six synthetic Markdown/note-backed cases:
stale `MEMORY.md` preference corrected by later clean source, unsourced
hand-edited topic notes, generated same-name summary merge, deleted/edited note
navigation with preserved clean source, source-backed note route to reopen, and
broken source-ref note. Unsourced or unreopenable notes stay navigation-only;
source-backed notes may route reopening but do not become exact evidence by
themselves.

In the 2026-05-30 local run, the gate benchmark reported 9 memory-pain cases,
0 unsupported-evidence false positives, and `live_llm_required=false`. The
payload benchmark reported 9 memory-pain cases, 0 privacy breaches, 0 evidence
without source, and 0 unsupported-evidence cases for the same fixture family.

On 2026-06-09, #996 recalibrated four source-free public pain prompts from
`should_scent` to `should_skip`: fabricated profile without source,
deterministic-vs-fuzzy memory as architecture prose, metadata round-trip with
an explicit no-memory boundary, and large-document foreground-LLM pressure.
The product boundary is that unsupported memory-like statements may become
scent only when they provide a route, old-thread deixis, or continuation intent;
otherwise the foreground hook should stay quiet. The same synthetic run
reported 188/188 correct Track A decisions, `evidence_false_positive_count=0`,
`over_escalation_count=0`, and
`harder_case_bank.natural_oral_evidence_false_negative_count=0`.

The gate report now emits `track_a_residual_calibration`, which groups the #996
residuals into source-free memory-pain statement reclassification, ordinary
code-surface suppression, false memory-word code surfaces, same-name
continuation scent, memory-write negation, and working-memory overlap. That
taxonomy is a deterministic synthetic calibration surface; it is not a live
semantic-model or real-history quality claim.

For #990, the same runner emits `memory_hygiene_fixtures`. The fixture report is
sanitized by default: it exposes status counts, selected evidence row ids,
duplicate-collapse/provenance metrics, and `cannot_claim` boundaries, but not
raw timeline text or source-ref values unless private debug is explicitly
enabled.

For #986, the same runner emits `auto_hook_pollution_fixtures`. It covers
transcript/write-path and lifecycle-like envelopes while preserving the claim
boundary that this is not a live hook-write quality measurement and not a
competitor behavior claim.

For #987, the same runner emits `note_memory_drift_fixtures`. The report is
sanitized by default: source refs are hashed, raw note/source text and local
paths are omitted, and private note text appears only when `--include-private-text`
is explicitly enabled.

## Reproduce

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_memory_decision_gate.py --json --output .tmp\memory-pain-gate-report.json
python benchmarks\aippocampus\benchmark_payload_fidelity.py --json --output .tmp\memory-pain-payload-report.json
python tools\aippocampus\run_tests.py --tier benchmark
```

The `.tmp` JSON outputs are local evidence artifacts. They should stay out of
git unless a future public corpus promotion deliberately creates a small,
audited, provenance-linked sample.

## Can Claim

- Public memory-system pain categories are represented by synthetic,
  public-safe boundary fixtures.
- Unsupported memory-like inputs are skipped or downgraded to scent-only
  instead of becoming source-backed evidence.
- Synthetic multi-turn hygiene fixtures distinguish current, stale,
  superseded, duplicate, suppressed, and fuzzy-navigation rows without
  promoting unsupported rows to evidence.
- Duplicate display/ranking can collapse while source provenance remains
  retained.
- Synthetic auto-hook pollution fixtures prove boot text, tool traces,
  recalled echoes, empty/run-id envelopes, transient task state, and host
  metadata remain below source-backed fact/evidence authority.
- Synthetic Markdown/note drift fixtures prove hand-edited or generated notes
  remain navigation-only without reopenable source support, and later clean
  source corrections outrank stale note summaries as evidence.
- Source-free memory-pain statements without route, source request, or
  continuation intent may be correctly skipped rather than surfaced as scent.
- The payload layer keeps the memory-pain fixture family free of privacy
  breaches and evidence-without-source failures in the tested path.
- Default benchmark reports are sanitized and aggregate-oriented.

## Cannot Claim

- No competitor superiority, leaderboard result, or equivalent adapter
  comparison.
- No live semantic-model quality claim.
- No real-history memory-pain quality claim.
- No real Track D runtime compaction-continuity proof. #66 adds a deterministic
  synthetic Track D runner, while this report's `compaction_continuity` fixture
  remains a boundary seed; neither proves correction, rejected route, accepted
  decision, and scope narrowing all survive a real compaction pipeline.
- No guarantee that every future generated summary, graph node, semantic
  sidecar, or vector neighbor is source truth.
- No live online-learning, physical source deletion, or full evidence drawer UX
  claim from the #990 synthetic hygiene report.
- No live AgentMemory/Mem0 behavior, full lifecycle write-path filter quality,
  or durable memory-write implementation claim from the #986 synthetic
  auto-hook pollution report.
- No full Obsidian/vault integration, no ban on user-authored notes, no claim
  that every note is exact evidence, and no live Markdown memory-quality claim
  from the #987 synthetic note-drift report.
