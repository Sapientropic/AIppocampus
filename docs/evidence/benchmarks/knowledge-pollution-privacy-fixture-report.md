# Knowledge Pollution And Privacy Fixture Report

Status: implemented public-safe contract-smoke fixture for GitHub #517.

This report records the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_knowledge_pollution.py`. The runner tests
knowledge pollution, stale/source authority failures, privacy partition leaks,
and one repo-internal `CapabilityContract` prototype for synthetic
contract-review assistance.

## What It Covers

- pollution families: stale guideline, old law/effective-date mismatch,
  source-looking fake authority, prompt injection inside source text,
  low-authority override, and model-summary-as-truth
- privacy families: medical-memory to legal review, therapy-memory to work
  advice, contract secret to external tool route, and cross-case context bleed
- required metrics:
  `contamination_escape_rate`, `stale_source_harm_rate`,
  `authority_override_rate`, `privacy_partition_leak_rate`,
  `source_reopen_required_violation_count`, and `unsupported_claim_rate`
- extra diagnostics:
  `source_prompt_injection_escape_rate` and
  `model_summary_as_truth_rate`
- contract-review prototype behavior:
  source-backed bounded risk flags, missing-context questions, source-reopen
  enforcement, and cannot-claim boundaries

## Public-Safe Boundary

All fixture rows are synthetic and checked in under
`tests/fixtures/knowledge_sources/`. The default report emits case ids, source
ids, claim ids, hashes, gate codes, and metrics. It does not emit raw input
text, source text, private conversation text, external-tool payload text, or
local absolute paths.

The contract-review prototype is not legal advice, legal certification,
clinical advice, therapy advice, or proof of real contract-review quality. It
only proves that the prototype can ask for missing context, require reopened
sources, refuse unsafe partitions, and emit bounded source-backed risk flags on
synthetic public-safe data.

## Command

```powershell
python benchmarks\aippocampus\benchmark_knowledge_pollution.py --json
python -m unittest tests.aippocampus.test_benchmark_knowledge_pollution
```

## Canonical Files

- Runner: `benchmarks/aippocampus/benchmark_knowledge_pollution.py`
- Runtime prototype:
  `skills/aippocampus/scripts/aippocampus_runtime/knowledge/capability_contract.py`
- Capability fixture:
  `tests/fixtures/knowledge_sources/public_safe_capability_contracts.json`
- Source/claim registry:
  `tests/fixtures/knowledge_sources/public_safe_registry.json`
- Mirror tests:
  `tests/aippocampus/test_benchmark_knowledge_pollution.py`

## Cannot Claim

- broad answer-generation quality
- real legal or contract-review quality
- privacy safety for arbitrary private records
- typed capability taxonomy completeness
- public API stability for capability contracts
- live external-model behavior
