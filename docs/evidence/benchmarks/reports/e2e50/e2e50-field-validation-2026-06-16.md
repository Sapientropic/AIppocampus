# E2E50 Field Validation, 2026-06-16

Status: private/local field-validation blocker recorded for #1981.

Command:

```powershell
python benchmarks\aippocampus\benchmark_e2e50_silent_constraint.py --field-validation --json
```

## Result

The runner now separates the public-safe E2E50 behavior pack from private/local
field validation:

- `public_contract_gate_ok=true`
- `field_validation_gate_ok=false`
- `field_case_count=7`
- `retained_control_case_count=7`
- `retained_case_shortfall=13`
- `negative_control_count=1`
- `behavior_scored_case_count=6`
- `public_fixture_only_case_count=50`
- `private_text_leak_count=0`
- `raw_ref_or_local_path_leak_count=0`

This records the blocker rather than hiding it. The retained/control field-case
target is not met, and the sanitized readiness summary does not preserve a
field-family breakdown, so private/local E2E50 behavior lift remains unclaimed.

## Boundaries

This report can say the public-safe contract pack remains independently
scorable and private/local scarcity is no longer the main public benchmark
blocker.

It cannot claim private-history behavior lift, representative E2E50 quality,
live-host behavior lift, or semantic-judge quality.
