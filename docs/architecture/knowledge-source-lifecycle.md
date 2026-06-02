# Knowledge Source Lifecycle

This ADR defines the first deterministic lifecycle contract for governed
knowledge sources. It extends the public knowledge-source manifest and claim
record schemas without introducing a live watcher, professional review system,
or regulated-compliance workflow.

## Decision

Knowledge-source updates are append-only lifecycle events. A new source version,
retraction, or rollback pointer must not overwrite the older source row. Runtime
consumers derive an effective status from source manifests plus update events,
while the original source ids remain auditable.

The runtime owner is `aippocampus_runtime.knowledge.schema`. It exposes pure
validators and evaluators only:

- `validate_knowledge_source_manifest(...)`
- `validate_knowledge_claim(...)`
- `validate_knowledge_update_event(...)`
- `evaluate_knowledge_lifecycle(...)`
- `validate_knowledge_registry(...)`

These helpers return reports with blockers and effective statuses. They do not
fetch remote sources, mutate clean source, write review records, or rank
answers.

## Lifecycle States

Source manifests use these states:

| State | Meaning |
| --- | --- |
| `quarantined` | Stored for audit, but missing enough provenance/scope/integrity to become candidate evidence. |
| `candidate` | Usable for navigation or review queues, not activated truth. |
| `review_required` | A discovered update or changed version exists, but high-stakes activation still needs review/signature. |
| `reviewed` | Reviewed source material that may support activation if other eligibility checks pass. |
| `active` | Eligible source material for promoted claims, subject to scope and conflict checks. |
| `superseded` | Older source version remains auditable but loses activation eligibility. |
| `retracted` | Source remains auditable but cannot support activated claims. |
| `retired` | Source is intentionally inactive without being deleted. |
| `rollback_available` | A rollback pointer exists for audit/recovery, but rollback is not automatic activation. |

The effective lifecycle status can be stricter than the manifest status. For
example, an `active` claim over a source becomes ineffective if an append-only
event later marks that source as superseded or retracted.

## Update Event Record

The public event schema is `aippocampus.knowledge_update_event.v1`.

```json
{
  "schema_version": "aippocampus.knowledge_update_event.v1",
  "event_id": "kevt-guideline-superseded",
  "old_source_id": "ksrc-guideline-2025",
  "new_source_id": "ksrc-guideline-2026",
  "diff_type": "superseded",
  "impact_scope": ["synthetic-safety"],
  "affected_claims": ["claim-old-span"],
  "requires_review": true,
  "review_status": "reviewed",
  "reviewer": "synthetic-reviewer:source-governance",
  "review_signed_at": "2026-06-01T00:00:00Z",
  "activated_at": "2026-06-01T00:00:00Z",
  "rollback_source_id": "ksrc-guideline-2025",
  "created_at": "2026-06-01T00:00:00Z"
}
```

Required semantics:

- `event_id` is stable and append-only.
- `old_source_id`, `new_source_id`, and `rollback_source_id` must resolve when
  the selected `diff_type` needs them.
- `affected_claims` is always present. It may be empty for an added source with
  no existing promoted claims.
- `impact_scope` names the affected domain or jurisdiction scope; it is not a
  model summary of the change.
- High-stakes events that request activation require `review_status:
  "reviewed"`, `reviewer`, `review_signed_at`, and `activated_at`.
- Candidate-only updates may be valid audit events while still carrying
  `update_review_required` as an activation blocker.

## Effective Claim Policy

Lifecycle evaluation projects claim status without rewriting the claim row:

- an activated claim over a superseded source becomes effectively
  `superseded`;
- an activated claim over a retracted source becomes effectively `blocked`;
- a candidate update affecting an existing active claim creates visible
  lifecycle context, but it does not silently replace the active claim;
- old source versions remain present in `source_ids_preserved`, and
  `deleted_source_ids` stays empty in the deterministic evaluator.

This keeps the source-backed boundary intact: AIppocampus can say a claim is
from source X, that source X was superseded by source Y, and that a reviewer
activated Y. It must not infer that Y is true merely because an ingest job or a
model-generated diff found it.

## Rollback

Rollback is an auditable pointer, not an automatic restoration. A rollback event
can point back to a previous source id, but high-stakes activation still goes
through the same review/signature gate. This prevents rollback from becoming a
shortcut around supersession, retraction, or conflict policy.

## Non-Goals

- No live network watcher or scheduled updater.
- No model-generated diff activation.
- No reviewer identity, permission, or electronic-signature system.
- No medical, legal, therapy, or regulated-use certification claim.
- No deletion of old source history during normal lifecycle handling.
- No public knowledge-ingest or answer-generation API.

## Verification

The public-safe fixture
`tests/fixtures/knowledge_sources/public_safe_registry.json` includes synthetic
added, changed, superseded, and retracted source versions. The deterministic
tests in `tests/aippocampus/test_knowledge_source_schema.py` prove:

- old source ids remain auditable after supersession;
- candidate updates cannot activate high-stakes knowledge without review;
- activated claims are downgraded when their source is superseded or retracted;
- update activation requires reviewer/signature metadata.
