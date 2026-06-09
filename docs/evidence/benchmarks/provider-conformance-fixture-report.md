# Provider Conformance Kit Report

Status: implemented public-safe provider conformance kit v1 for GitHub #981,
retaining the GitHub #988 synthetic acceptance cases.

This report records the evidence boundary for
`benchmarks/aippocampus/benchmark_provider_conformance.py`. The runner uses the
checked-in fixture at `benchmark_corpus/provider_conformance/fixture.json` to
exercise provider/session identity, cross-provider source-reopen routes,
copied-summary downgrades, injected host content demotion, MCP drop-in metadata
shape, real normalizer ingestion for `generic-jsonl` and `claude-code`, and
sanitized provider failure examples.

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
- real `generic-jsonl` normalization of user/final assistant rows, including
  stable session/thread identity and actionable malformed-row diagnostics
- real `claude-code` normalization of visible user/final assistant rows while
  ignoring summary/system-like rows
- explicit surface-status separation for ingestion, MCP/registry access, host
  hooks, and configuration-mutating installers
- public-safe failure examples for orphan assistant rows, unstable sessions,
  injected-content pollution, missing source-reopen affordance, and secret/path
  leakage

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
- `provider_suite_count`
- `provider_suite_pass_count`
- `provider_failure_example_count`
- `provider_failure_example_pass_count`

Default output omits raw provider rows, raw provider logs, raw memory blob text,
source-ref values, absolute paths, and secret values.

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
- real cross-host continuity quality
- MCP memory blobs as source truth
- that ingestion support implies host hooks or settings mutation
- that scoped hook smoke implies persistent MCP or real-host firing
