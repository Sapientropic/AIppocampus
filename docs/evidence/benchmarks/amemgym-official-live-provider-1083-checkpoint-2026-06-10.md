# AMemGym Official Live-Provider Checkpoint Audit - 2026-06-10

Role: dated closeout note for #1083.
Status: closes the requested "run or precise blocker" follow-up by using the
checkpoint/resume support from #1052 against the existing live-provider partial
outputs. This note does not add an AMemGym score.

## Source And Run Boundary

- Official upstream commit: `AGI-Eval-Official/amemgym@ffcd18857a3e2b2c61f00730ebdec676e27d3e87`.
- Dataset/config: full public `v1.base`, 20 public user items,
  `item_ids_sha1=4de568295e151638`.
- Existing ignored outputs: the 2026-06-06 OpenRouter Native attempt described
  in the AMemGym benchmark note. Raw official rows, model transcripts, local
  absolute paths, and provider credentials remain uncommitted.
- Audit command shape: the operator supplied the existing ignored upstream,
  dataset, config, agent config, and output directories to
  `benchmark_amemgym_official.py`, then ran only `--run random --resume` with
  `--checkpoint` and an ignored JSON summary output.
- Provider audit mode: `--provider default` was used for the audit pass so the
  bridge would not rewrite the already-generated OpenRouter agent config. The
  audited live outputs remain the previous OpenRouter Native partial attempt.

The resume audit intentionally did not restart `overall` or `upperbound`; doing
so would resume a long live-provider run with unclear cost and duration. It
only verified that the bridge can recognize completed official artifacts,
write a public-safe checkpoint, and preserve partial phase states without
promoting them into a score.

## Observed State

The checkpoint/resume audit generated at `2026-06-10T07:57:17Z` reported
`status=partial_official_outputs`, `ok=true`, and
`fixed_arm_execution.status=partial_resumable_outputs`.

| Surface | State | Counts |
| --- | --- | --- |
| `overall` | partial | 6 of 20 user items complete; 7 result files; 760 of 770 observed score leaves in the partial output tree. |
| `upperbound` | partial | 38 of 882 choice evaluations complete; one result file; no complete utilization metrics file. |
| `random` | complete | One random metrics file present; `official_random=0.23076190476190475`. |

The `--resume` pass skipped the complete `random` surface with
`reason=resume_existing_complete_output`. It wrote a public-safe checkpoint with
content hash `e0189ccaa3760522`.

Cost and latency remain bounded to what the public-safe bridge can honestly
report:

- `provider_cost_status=unavailable`
- `unavailable_reason=provider_usage_metadata_not_extracted_from_official_outputs`
- `latency_status=process_elapsed_only`
- audit process elapsed time: about 3.6s
- live-provider elapsed time for the older partial attempt: roughly two hours,
  as recorded in the 2026-06-09 blocker note

## Interpretation

The #1052 support works as an audit/recovery shell: it can preserve a public
phase-state checkpoint, skip complete surfaces, and prevent subset or partial
outputs from becoming a full `v1.base` claim.

It does not remove the live-provider blocker:

- Complete `overall`, `upperbound`, and `random` outputs are still required
  before `Overall`, `UB`, `Random`, or normalized `Memory` can be interpreted.
- The existing live-provider fixed arm still lacks complete `overall` and
  `upperbound` surfaces.
- The bridge has no stable public provider-token or billing extraction path
  from the official outputs.
- Re-running `overall` / `upperbound` would be an intentional long live-provider
  operation, not a safe cleanup command.
- Native/RAG/AWI/AWE parity arms should remain deferred until one pinned live
  fixed arm is complete and reviewed.

## Closeout Decision

Issue #1083 is closed as a precise blocker/progress report, not as completed
scoring.
The remaining work is not ambiguous issue cleanup; it is an external dependency
and operator-cost decision. A future issue or dated run should reopen the live
score only when an operator is ready to run the full fixed arm to completion
and review the resulting public-safe report.

Before any AMemGym live-provider Current Claim Snapshot row is added, produce a
later dated note with:

- the upstream commit and dataset/config identifiers;
- pinned provider/model identity and command shape;
- complete `overall`, `upperbound`, and `random` outputs for the fixed arm;
- sanitized `Overall`, `UB`, `Random`, normalized `Memory`, and cost/latency or
  explicit unavailable-provider-field reason;
- no committed raw official rows, model transcripts, local absolute paths,
  provider credentials, or raw billing payloads;
- a parity-arm decision after the fixed arm passes review.
