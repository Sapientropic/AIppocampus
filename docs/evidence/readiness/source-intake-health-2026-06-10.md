# Source Intake Health Evidence - 2026-06-10

Role: dated evidence.
Status: reproducible public-safe fixture run for #1127.

## What Ran

```powershell
python -m pytest tests\aippocampus\test_source_intake_health.py -q
python -m pytest tests\aippocampus\test_aippocampus_health.py -q
python -m ruff check skills\aippocampus\scripts\aippocampus_runtime\source\source_intake_health.py tests\aippocampus\test_source_intake_health.py tests\aippocampus\test_aippocampus_health.py
python -m mypy skills\aippocampus\scripts\aippocampus_runtime\source\source_intake_health.py tests\aippocampus\test_source_intake_health.py
```

## Can Claim

- `aippocampus health` exposes a `clean_source.source_intake` JSON block.
- The fixture detects stale/missing hook status, truncation, duplicate rows,
  tool-payload pollution, local-path/secret-like counts, broken refs,
  registry/materialization mismatch, derived-summary/read-path mismatch, and
  degraded restart durability.
- The report emits statuses, counters, fallback posture, and cannot-claim
  boundaries without raw private text, local paths, secret values, or raw tool
  payloads.

## Cannot Claim

- Host APIs or hooks are stable forever.
- Live AgentMemory behavior was reproduced.
- Private real-history source intake quality has been proven.
- Source-backed claims are safe when `source_quality_status = degraded`.
