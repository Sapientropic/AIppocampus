# Multimodal Answer Gate

Role: current contract.

Status: public-safe answer-time gate prototype for GitHub #543 and the #528
multimodal source-backed recall track.

This contract defines the small candidate packet that sits after multimodal
candidate recall/provider routing and before answer generation. The packet is a
bounded evidence input to an answerer, not an answer and not source truth.

## Runtime Owner

The deterministic evaluator lives at
`skills/aippocampus/scripts/aippocampus_runtime/model/multimodal_answer_gate.py`.
The public-safe fixture lives at
`tests/fixtures/multimodal_sources/public_safe_answer_gate.json`, with coverage
in `tests/aippocampus/test_multimodal_answer_gate.py`.

This gate depends on:

- the #531 corpus-style retrieval fixture:
  `docs/evidence/benchmarks/reports/multimodal/multimodal-corpus-fixture-report.md`;
- the #532 conversational media-ingest fixture:
  `docs/evidence/benchmarks/reports/multimodal/conversational-media-ingest-fixture-report.md`;
- the #533 supplied-pool/NIAH fixture:
  `docs/evidence/benchmarks/reports/multimodal/multimodal-niah-evidence-pool-report.md`;
- the #541 source manifest:
  `docs/architecture/source/multimodal-source-manifests.md`;
- the #542 provider-routing contract:
  `docs/architecture/host/multimodal-provider-routing.md`.

## Candidate Packet

A candidate packet declares:

- `packet_id`;
- `join_reasons`;
- selected and rejected candidate sources;
- source ids, media types, origin policies, source anchors, and captured times;
- whether the original source anchor has been reopened;
- whether a background source was explicitly selected or onboarded;
- whether the selected source supports the requested detail;
- conflict-set authority/finality fields for receipt, invoice, email, and
  document/payment evidence.

Current join reasons are:

- `temporal_window`;
- `entity_reference`;
- `place_event`;
- `document_payment_relation`;
- `source_authority_precedence`.

These reasons explain why candidates are adjacent. They do not authorize an
answer.

## Gate Rules

The gate blocks or abstains when:

- a visual/video/document claim uses a candidate without reopening the original
  source anchor;
- background filesystem media appears without explicit selection or onboarding;
- task-scoped media use performs a hidden durable memory write;
- the requested visual/document detail is not visible or source-backed;
- a conflicting amount/document source is selected against later, final, or
  stronger-authority evidence.

When conflicting receipt, invoice, email, or payment evidence is present, the
gate expects source-authority precedence to favor the later/final/stronger
source when policy allows it. If the packet cannot justify that choice, it must
return a review state rather than averaging or guessing.

## Metrics

The #543 smoke reports the #528 answer-time metrics that #531-#533 do not own:

- `source_reopen_required_violation_count`;
- `background_scan_violation_count`;
- `hidden_durable_write_violation_count`.

Policy-blocked background media is counted as a background scan violation, not
double-counted as a missing source-reopen violation. That keeps the metrics
diagnostic instead of inflated.

## Non-Goals

- No full-device indexing.
- No face-recognition identity graph.
- No live vision provider call by default.
- No answer generation.
- No promotion of join/rerank output into source truth.

## Verification

The public-safe fixture covers:

- personalized reference with reopened image evidence;
- conflicting amount where the final receipt beats an earlier email estimate;
- cross-modal event join across image and calendar/event sources;
- unsupported-detail abstention when related media exists but the detail is not
  visible or source-backed;
- a visual claim without source reopen;
- unselected background media;
- hidden durable write during task-scoped media use.

Reports expose sanitized ids, hashes, join reasons, blocker codes, and metrics.
They do not emit raw media bytes, raw prompt text, local paths, or hidden-write
payloads.
