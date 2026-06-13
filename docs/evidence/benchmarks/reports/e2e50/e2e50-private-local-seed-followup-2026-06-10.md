# E2E50 Private / Local Seed Follow-up - 2026-06-10

Status: closes #1086 as a sanitized blocker/progress report, not as a
completed private-history E2E50 pack.

This note records the current private/local E2E50 seed state after the public
20-case scaffold in #994. It does not publish private text, thread ids, message
ids, raw source refs, local paths, or candidate rows.

## Command Shape

The follow-up used the scanner's historical wide candidate window plus the
new sanitized annotation-summary path:

```powershell
python tools\aippocampus\smoke\smoke_e2e50_seed_candidates.py --json --min-turns 30 --max-turns 120 --early-turns 15 --later-start-turn 30 --min-candidates 20 --max-candidates 100 --annotation <ignored-local-manual-annotation-json> --output .tmp\e2e50-private-local-followup-20260610.json
```

The ignored local annotation artifact is the existing private clean-source
review summary from the 2026-06-04 Dream/E2E50 diagnostic. The command output
remains local and ignored.

Machine-readable readiness replay:
`docs/evidence/benchmarks/reports/e2e50/e2e50-private-annotation-readiness-2026-06-10.json`.

The replay feeds the sanitized scanner `annotation_summary` into
`benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py` so the public
20-case scorer and the private/local annotation blocker can be read from one
hash/count-only report:

```powershell
python benchmarks\aippocampus\benchmark_e2e50_silent_constraint.py --private-annotation-summary .tmp\e2e50-private-local-followup-20260610.json --output docs\evidence\benchmarks\reports\e2e50\e2e50-private-annotation-readiness-2026-06-10.json
```

The benchmark replay does not accept raw private annotation rows directly; the
scanner remains the owner for reducing local review rows to aggregate counts.

## Candidate Discovery

The current wide scan is no longer candidate-count blocked:

| Field | Value |
| --- | ---: |
| Candidate scan status | `sufficient_candidate_seeds` |
| Candidate count | 23 |
| Requested minimum candidates | 20 |
| Registry threads scanned | 1,571 |
| Message rows scanned | 17,045 |
| Event rows scanned | 91,034 |
| Long threads in configured range | 49 |
| Compaction-observed threads | 226 |
| Signal-bearing threads | 1,436 |
| Bad message rows | 0 |
| Bad event rows | 0 |

This is candidate discovery only. The stricter 45-70 turn window still found
only 8 candidates in the same local registry, so the candidate pool should be
read as a wide-window private/local discovery surface, not as a stable
representative E2E50 pack.

## Annotation Summary

The reviewed local annotation set is still the blocker:

| Field | Value |
| --- | ---: |
| Annotation status | `private_annotation_blocked` |
| Locally reviewed candidates | 17 |
| Retained/control cases | 7 |
| Behavior seed cases | 6 |
| Required retained/control cases | 20 |
| Retained/control shortfall | 13 |
| Required negative controls | 1 |
| Negative-control shortfall | 0 |
| Private text exported | false |

Annotation category counts:

| Category | Count |
| --- | ---: |
| Gold | 4 |
| Calibration | 2 |
| Negative control | 1 |
| Source-visible / no-op | 0 |
| Duplicate | 3 |
| Rejected | 7 |
| Blocker | 0 |
| Unknown | 0 |

Blocker class counts:

| Class | Count |
| --- | ---: |
| Retained candidate | 6 |
| Subagent or goal-context noise | 5 |
| Duplicate candidate | 3 |
| High later remention | 1 |
| Source-visible / no-op | 1 |
| Negative control | 1 |

## Interpretation

The old 17/20 candidate-count blocker is narrowed: current private/local
candidate discovery can produce at least 20 sanitized candidates under the
wide scan used by the original diagnostic.

The remaining blocker is annotation quality and retained-case count. Local
source review has only 7 retained/control cases against the 20-case private
target. The set does include at least one negative control where the correct
behavior is not to remember, but it still does not support a completed
private-history 20-case pack.

The benchmark readiness replay records the same blocker as
`private_annotation_readiness.gate_ok=false`, with
`blocker_codes=["private_annotation_not_retained",
"private_retained_case_shortfall"]`.

This report coexists with the public-safe 20-case scaffold from #994. The
public scaffold proves a shareable contract shape; this private/local report
shows the real-history annotation pool is still not large enough for private
behavior-quality claims.

## Can Claim

- The E2E50 private/local scanner now has a sanitized annotation-summary path.
- The E2E50 case-pack scorer can consume that sanitized summary and report the
  private annotation readiness blocker without emitting annotation rows.
- Current wide private/local candidate discovery can find 23 candidate seeds
  while emitting only hash/count-style output.
- Existing private/local annotation evidence has source-safe category and
  blocker counts, including one no-remember negative control.
- The remaining private/local blocker is 7 retained/control cases against the
  20-case target, not merely a missing public scaffold.

## Cannot Claim

- Completed private-history 20-case or 50-case E2E50 quality.
- Private real-history behavior lift.
- Representative E2E50 sample quality.
- Live host behavior lift.
- Semantic judge quality.
- That the public synthetic 20-case scaffold proves private-history behavior.
