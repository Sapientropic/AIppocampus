# Source Intake Health

Role: current contract.
Status: fixture-backed health contract for #1127.

Source-backed recall depends on source quality being observable. Host hooks are
a convenience path, not the only source path, and a completed ingest must not be
treated as proof that clean source is complete, reopenable, or pollution-free.

The runtime owner is
`aippocampus_runtime.source.source_intake_health`. `aippocampus health` exposes
the report under `clean_source.source_intake`.

## Checked Failure Families

The report covers:

- missing, disabled, or stale-version hook paths;
- truncated clean source;
- duplicated source events;
- raw tool payload pollution;
- local-path and secret-like leakage counts;
- missing final-answer or user-turn coverage when the manifest declares
  expected counts;
- broken or unreopenable source refs;
- registry versus clean-source materialization mismatch;
- derived-summary versus user-facing read-path mismatch;
- degraded restart durability status.

The report is public-safe: it emits counts, statuses, and reason codes only. It
does not echo raw private text, raw tool payloads, local paths, secret values,
or host payloads.

## Fallback Posture

When source intake degrades, the correct posture is:

```text
hook path -> source health check -> generic import fallback -> manual reopen/audit path
```

That keeps hooks useful without making them a single point of truth. A degraded
report should guide repair and fallback, not silently promote polluted or
incomplete material into source-backed claims.

## Status And Metrics

The primary status is:

```text
source_quality_status = ok | degraded
```

Representative metrics include:

```text
hook_available
hook_version_status
source_truncation_detected_count
polluted_source_event_count
broken_source_ref_count
registry_clean_source_mismatch_count
derived_summary_mismatch_count
generic_import_fallback_available
```

When degraded, `cannot_claim` includes boundaries such as:

```text
source_backed_claims_safe_when_intake_degraded
host_hooks_are_stable_forever
ingestion_success_means_source_quality_ok
```

## Claim Boundary

Passing this contract supports:

```text
AIppocampus can detect major source-intake fragility and provide fallback
posture.
```

It does not support any host integration being stable forever, live external
systems having the same bugs, or source-backed claims being safe while source
health is degraded.
