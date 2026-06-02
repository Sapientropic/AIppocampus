# High-Risk Answer Gates

This ADR defines the first deterministic answer-time gate for high-impact
AIppocampus knowledge use. It builds on the governed knowledge-source manifest,
claim-promotion, and update-lifecycle contracts without turning AIppocampus
into a doctor, lawyer, therapist, compliance engine, ranking system, or answer
generator.

## Decision

High-risk answer formation must pass through
`aippocampus_runtime.knowledge.answer_gate.evaluate_high_risk_answer_gate(...)`
before a governed knowledge claim is used as support for medical-like,
legal-like, therapy-like, financial-like, safety-critical, or similarly
high-impact conclusions.

The gate is a pure local policy function. It accepts:

- a governed knowledge registry payload;
- selected `claim_ids`;
- route evidence such as embedding hits or reopened source spans;
- request context such as domain, jurisdiction, date, and critical variables;
- required context keys chosen by the caller for the current high-risk domain.

It returns a deterministic report with `output_state`, `gate_codes`,
`cannot_claim`, `source_boundary`, `privacy`, `conflict_sets`, and
`cited_boundaries`. It does not fetch sources, write review records, call
external models, rank answers, or emit final natural-language advice.

## Output States

| State | Meaning |
| --- | --- |
| `source_reopen_required` | The selected claim only has routing evidence such as an embedding hit or semantic match. The source span must be reopened before answer use. |
| `missing_context_question` | Required jurisdiction, date, domain, or caller-declared critical variables are missing. Ask for the missing context before using the claim. |
| `human_review_required` | Lifecycle, source authority, conflict, privacy, or review state is unsafe for automated high-risk answer use. |
| `degrade_to_general_information` | The source/claim may be useful background, but applicability checks do not support the requested scoped answer. |
| `refuse_or_redirect` | The requested claim cannot be resolved or the gate cannot form a bounded answer contract. |
| `answer_with_cited_bounds` | The claim has reopened source-span evidence, active lifecycle status, applicable scope/date, cleared conflicts, and a privacy-safe boundary report. |

## Gate Order

The deterministic precedence is:

1. Resolve selected claims. Missing claim ids return `refuse_or_redirect`.
2. Check required request context. Missing context returns
   `missing_context_question` so the caller can ask a concrete follow-up instead
   of guessing.
3. Require reopened source-span evidence for every selected claim. Embedding
   hits, semantic matches, vector neighbors, model summaries, dream findings,
   and other generated sidecars remain navigation only.
4. Check claim applicability against request domain, jurisdiction, and
   effective date. Out-of-scope material degrades to general information.
5. Enforce private-source boundaries before external-model use. Private source
   text is not exportable without explicit permission.
6. Reuse `validate_knowledge_claim(..., high_stakes=True)` and
   `evaluate_knowledge_lifecycle(...)` for source eligibility, claim promotion,
   review/signature, supersession, and retraction state.
7. Surface unresolved conflict sets. Conflicting sources must remain visible and
   require review; the gate must not average or summarize them into fake
   consensus.
8. Only then return `answer_with_cited_bounds`.

This order is intentionally conservative but not maximalist. Asking for missing
context can happen before opening more source text; once context exists,
reopened source evidence is the proof boundary.

## Source And Privacy Boundary

`cited_boundaries` may include source ids, source anchors, authority level,
scope, effective date, evidence grade, and uncertainty notes. The gate report
must not include raw source text or claim text. Its `source_boundary` and
`privacy` blocks explicitly mark `source_text_exported: false` and
`claim_text_exported: false`.

This keeps source reopen as the proof step without making answer-gate reports a
new leakage surface. External-model routes must still pass through the existing
redaction and permission boundary before any private material is sent out of the
trusted local process.

## Conflict Policy

A selected claim with an uncleared `conflict_set_id` cannot support an automated
high-risk answer. The report must include the conflict set id and member claim
ids so a caller or reviewer can inspect the disagreement. The safe action is
`human_review_required`, not majority vote, averaging, or model-written
synthesis.

## Synthetic Example Shapes

Use public-safe synthetic fixtures for high-risk examples. The examples should
test gate behavior, not provide real domain advice:

| Example shape | Expected gate pressure |
| --- | --- |
| Aspirin-suitability-like health question | Missing patient/context variables or source authority returns `missing_context_question` or `human_review_required`; no professional medical claim is emitted. |
| Non-compete-clause-like legal question | Missing jurisdiction/effective date returns `missing_context_question`; conflicting or out-of-scope sources remain visible instead of becoming consensus. |
| Crisis-support-like boundary question | Private conversation source may support only bounded conversation-memory claims; urgent harm or professional-care conclusions require redirect/human-review policy outside this gate. |

## Non-Goals

- No professional certification or regulated advice claim.
- No live network watcher, source fetching, or background updater.
- No ontology, ranking, attribution, LLM judge, or expert-system layer.
- No public answer-generation API.
- No promotion of embeddings, semantic matches, summaries, triples, or dream
  findings into evidence.
- No export of private source text to external models by default.

## Verification

`tests/aippocampus/test_knowledge_answer_gate.py` uses public-safe synthetic
fixtures to prove:

- embedding hits alone cannot emit high-risk answers;
- missing jurisdiction/date/context variables trigger ask-or-degrade behavior;
- active reopened claims can emit only with cited boundaries and cannot-claim
  markers;
- conflicts remain visible and require review;
- private sources on external routes require an explicit permission boundary;
- reports do not include raw claim text.
