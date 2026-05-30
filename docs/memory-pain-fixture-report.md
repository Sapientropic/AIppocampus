# Memory Pain Fixture Report

Evidence date: 2026-05-30.

This report summarizes the public-safe fixture evidence added for #27 and used
to satisfy #28. It is a demo/report for AIppocampus claim boundaries, not a
competitor scorecard or leaderboard.

## Source Map

- Taxonomy: [`docs/research/memory-system-pain-taxonomy.md`](research/memory-system-pain-taxonomy.md)
- Benchmark plan: [`docs/memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md)
- Gate runner: [`benchmarks/aippocampus/benchmark_memory_decision_gate.py`](../benchmarks/aippocampus/benchmark_memory_decision_gate.py)
- Payload runner: [`benchmarks/aippocampus/benchmark_payload_fidelity.py`](../benchmarks/aippocampus/benchmark_payload_fidelity.py)
- Tests:
  [`tests/aippocampus/test_benchmark_memory_decision_gate.py`](../tests/aippocampus/test_benchmark_memory_decision_gate.py)
  and
  [`tests/aippocampus/test_benchmark_payload_fidelity.py`](../tests/aippocampus/test_benchmark_payload_fidelity.py)

## What Was Demonstrated

The synthetic Track A/C benchmark surface now emits a `memory_pain_fixtures`
summary. The covered public-safe families are:

- `write_time_pollution`
- `recalled_context_feedback_loop`
- `fabricated_profile_no_source`
- `transient_task_state`
- `deterministic_vs_fuzzy_memory`
- `metadata_round_trip`
- `large_document_no_foreground_llm`
- `invalid_structured_extraction`
- `compaction_continuity`

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

In the 2026-05-30 local run, the gate benchmark reported 9 memory-pain cases,
0 unsupported-evidence false positives, and `live_llm_required=false`. The
payload benchmark reported 9 memory-pain cases, 0 privacy breaches, 0 evidence
without source, and 0 unsupported-evidence cases for the same fixture family.

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
