# Cognitive Observatory Current Completeness - 2026-06-14

This public-safe smoke closes #1443 as a replayable current/local fixture for
the read-only Cognitive Observatory. It checks that the current observability
surface is complete enough to inspect, while preserving the boundary that the
Observatory cannot mutate recall ranking, activation order, or foreground hooks.

## Command

```powershell
python tools\aippocampus\smoke\smoke_cognitive_observatory_current_completeness.py `
  --json `
  --output docs\evidence\benchmarks\reports\cognitive-runtime\cognitive-observatory-current-completeness-2026-06-14.json
```

Focused verification:

```powershell
python -m pytest tests\aippocampus\test_cognitive_observatory_current_completeness.py -q
```

## Fixture

The local/current fixture exercises these surfaces together:

- route readiness
- activation authority
- recall diagnostics
- query-pattern route summaries
- cognitive-load calibration summary
- sleep-cycle public summaries
- Campus usefulness panels

It also includes stale, missing, privacy-blocked, and suppressed buckets plus
attempted activation/control-plane mutations. Those attempted mutations are
counted only as blocked diagnostics.

## Result

The report now starts with a top-level reader contract so a fresh agent can
inspect current usefulness without reading the full diagnostic object:

- `included_surfaces`: the seven surfaces present in this fixture
- `missing_optional_surfaces`: empty for this run
- `blocked_or_suppressed_surfaces`: stale, privacy-blocked, and suppressed
  buckets grouped by surface
- `control_plane_status`: `read_only`
- `recommended_next_actions`: source reopen before claims, read-only
  inspection, and opt-in repair for missing/suppressed surfaces

| Metric | Value |
|---|---:|
| Expected surfaces | 7 |
| Included surfaces | 7 |
| Missing surfaces | 0 |
| Stale bucket count | 21 |
| Privacy-blocked bucket count | 17 |
| Suppressed bucket count | 26 |
| Blocked control attempts | 1 |
| Attempted foreground-hook mutations | 1 |
| Live ranking / hook mutations | 0 |
| Raw leak flags | 0 |

The negative projection test also passes an older fixture that lacks the
`cognitive_load_calibration` surface and verifies the completeness report marks
that surface as missing instead of silently claiming complete coverage.
Each surface row separates `surface_supported`,
`surface_present_in_this_readout`, and `surface_validated_by_fixture`, so an
absent optional surface cannot look like successful live/current coverage.

## Can Claim

- A public-safe current completeness projection exists for #1443.
- The current Observatory fixture accounts for each expected surface as either
  included or explicitly missing.
- The public report distinguishes supported, present-in-this-readout, and
  fixture-validated surface states.
- Stale, missing, privacy-blocked, and suppressed buckets are visible in the
  diagnostic projection.
- Attempted activation/order/hook mutations are counted as blocked diagnostics
  and do not alter live recall ranking or hook behavior.

## Cannot Claim

- Cognitive Observatory is a control plane.
- Observatory rows can change activation order, live recall ranking, or
  foreground-hook behavior.
- Observatory summaries are source truth without source reopen.
- Live user-visible quality lift.
- Public evidence from private raw history.

## Public Boundary

The committed report does not serialize raw prompts, raw source text, source
refs, thread/message handles, local paths, provider payloads, credentials, or
private-history rows.
