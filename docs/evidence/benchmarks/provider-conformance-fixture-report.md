# Provider Conformance Fixture Report

Status: implemented public-safe contract-smoke fixture for GitHub #988, as a
child slice of the provider conformance kit in GitHub #981.

This report records the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_provider_conformance.py`. The runner uses the
checked-in synthetic fixture at
`benchmark_corpus/provider_conformance/fixture.json` to exercise provider /
session identity, cross-provider source-reopen routes, copied-summary
downgrades, injected host content demotion, and MCP drop-in metadata shape.

It is not a live Claude Code, Codex, Cursor, Gemini CLI, or AgentMemory
compatibility result.

## What It Covers

- same repository and same entity label across distinct provider/session ids
- a correction authored in one provider and consumed as a route by another
- provider A with a reopenable source ref versus provider B with only a copied
  summary
- host system/tool content demoted below durable user memory
- MCP output with source-ref/reopen affordance contrasted with a blob-only
  payload

The blob-only MCP case is expected to emit
`provider_conformance.mcp_missing_source_ref_affordance`; this is a provider
conformance failure, not a generic retrieval miss.

## Metrics

The report exposes sanitized aggregate counters:

- `provider_count`
- `source_reopen_route_count`
- `navigation_only_artifact_count`
- `injected_content_demoted_count`
- `mcp_evidence_drawer_ready_count`
- `same_name_conflation_failure_count`
- `failure_code_counts`

Default output omits raw provider logs, raw memory blob text, source-ref
values, absolute paths, and secret values.

## Command

```powershell
python benchmarks\aippocampus\benchmark_provider_conformance.py --json
python -m unittest tests.aippocampus.test_benchmark_provider_conformance
```

## Canonical Files

- Runner: `benchmarks/aippocampus/benchmark_provider_conformance.py`
- Fixture: `benchmark_corpus/provider_conformance/fixture.json`
- Mirror tests: `tests/aippocampus/test_benchmark_provider_conformance.py`
- Provider inventory:
  `docs/architecture/provider-entrypoint-inventory.md`

## Cannot Claim

- live provider adapter quality
- all-client drop-in support
- AgentMemory behavior
- the full provider conformance kit
- real cross-host continuity quality
- MCP memory blobs as source truth
