# Learning-Loop Private Replay Readout - 2026-06-15

Role: public-safe operator readout from a local private-history run.

Input: one operator-selected local Codex rollout, exported through
`aippocampus_runtime.learning_loop.private_export` into sanitized behavior
events. The temporary export is a local-private artifact and is not committed.

## Result

- Replay status: `ok`
- Sanitized event count: 38
- Raw private text leak count: 0
- Local path leak count in export validation: 0
- Missing source-ref count in export validation: 0

## Comparable Metrics

| Metric | Value |
| --- | ---: |
| `repeated_failure_detection_recall` | 1.0 |
| `workflow_order_detection_count` | 1 |
| `context_reopen_before_action_rate` | 1.0 |
| `false_positive_nudge_rate` | 0.0 |
| `source_backed_guidance_changed_action_order_count` | 1 |
| `context_loss_to_reopen_source_count` | 1 |
| `effectiveness_ledger_row_count` | 1 |

The run produced one navigation-only effectiveness row with
`effectiveness_status = useful_signal` and no repeat failure after the hint.

## Boundaries

This readout supports that the private replay/export path works on real local
history without serializing raw rollout text, commands, stdout/stderr, source
snippets, or local paths.

It does not claim causal live behavior lift, broad private-history generality,
or that the guidance is source truth. Expected-red and one-off suppression are
covered by public deterministic fixtures for this slice; this particular local
sample did not contain those cases.
