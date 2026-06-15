# Schema Field Profiles

Role: current contract.

Last checked: 2026-06-03.

This note defines the field-budget discipline for AIppocampus schemas. It is a
profile and projection rule, not a new universal record schema.

The goal is to keep rich provenance available without forcing every manifest,
source row, capability contract, activation packet, prompt context, and
benchmark report to carry every possible field. Clean source and source refs
remain the truth boundary; profiles only decide which fields a consumer should
see or require.

## Profile Vocabulary

| Profile | Required shape | Optional shape | Intended consumer |
| --- | --- | --- | --- |
| `identity_minimal` | Stable id, source pointer, content hash, created/updated time. | None by default. | Joins, dedupe, portable fixture identity, and minimal round-trip checks. |
| `retrieval_runtime` | `identity_minimal`. | Retrieval keys, source refs, reopen hint, modality, privacy class. | Candidate selection and source reopen. |
| `foreground_action_card` | `decision`, `why`, `next_action`, `claim_boundary`. | `route_label`, `route_family`, one local-private callable handle or short action token. | Working foreground agents that need the next safe move before audit details. |
| `governance_extended` | `identity_minimal`. | Authority, review, lifecycle, privacy, conflict, supersession, signature, access policy. | Review, lifecycle, sync, and audit surfaces. |
| `diagnostic_metrics` | `identity_minimal` plus diagnostics. | Metrics, cost, latency, ROI, benchmark fields. | Operator reports and benchmarks. |
| `high_risk_required` | `identity_minimal` plus authority, review, lifecycle, privacy, conflict, and source-reopen policy. | Jurisdiction, effective-date, human-review, and access-policy boundaries. | High-risk answer gates and similarly strict call sites. |

Unknown fields are ignored by stable readers unless the selected profile makes
them mandatory. Projection should drop fields outside the active profile instead
of allowing experimental metadata to become prompt-visible by accident.

The runtime helper
`aippocampus_runtime.schema_profiles` owns the tiny deterministic projection
and validation API for this vocabulary:

- `project_record_for_profile(record, profile)` emits only named profile fields
  in stable order.
- `validate_profile_record(record, profile)` checks required fields and reports
  ignored extras without making them errors.

These helpers are deliberately small. Domain owners such as knowledge sources,
multimodal manifests, capability contracts, and sync bundles still own their
specific schemas and validators.

## Minimal Vs Extended Example

The public-safe knowledge registry fixture
`tests/fixtures/knowledge_sources/public_safe_registry.json` is the current
rich-record example.

For a knowledge-source row, an `identity_minimal` projection is the portable
join/integrity surface:

| Profile field | Knowledge-source source |
| --- | --- |
| `schema_version` | fixture row `schema_version` |
| `record_id` | fixture row `source_id` |
| `source_ref` | a source pointer such as `{kind: "knowledge_source", source_id}` |
| `content_hash_sha256` | fixture row `content_hash_sha256` |
| `created_at` | row or registry ingest timestamp |
| `updated_at` | row or registry update timestamp |

The same row may also carry governance fields such as authority, review,
lifecycle, privacy, conflict, supersession, signature, effective-date, and
access-policy data. Those belong in `governance_extended` or
`high_risk_required` projections, not in the minimal record required for
ordinary recall.

Diagnostics such as cost, latency, hit/miss, ROI, benchmark gates, or failed
prewarm counts belong in `diagnostic_metrics` or an owner-specific report
sidecar. They must not become clean-source fields or ordinary prompt context
only because they were useful during evaluation.

## Sidecar Placement

Prefer sidecars, nested optional records, or explicit profile projections when
a field is operational, diagnostic, lifecycle-oriented, benchmark-only,
experimental, model-generated, or high-risk specific.

Use clean source for source text, stable source keys, source refs, line spans,
timestamps, and hashes. Do not move source truth into summaries, sidecars,
diagnostics, labels, or model-organized findings. Those layers can route back
to source, but they cannot replace source reopen.

Model-visible packets should project only the fields needed for the current
decision. For example, a prompt-time recall card usually needs source refs,
reopen hints, and privacy-safe boundaries. It usually does not need lifecycle
signatures, benchmark latency, or high-risk jurisdiction fields.

For explicit agent recall and MCP foreground use, the first surface is
`foreground_action_card`. It answers four questions: whether to use the route,
why it matters, what to do next, and what not to claim yet. Audit-only fields
such as `metrics`, `red_lines`, `policy_boundary`, `cannot_claim`,
`attention_router_navigation`, `macro_navigation`, and full
`memory_packets` / `deepen_requests` stay available in JSON diagnostics, but
they must not enter the action card.

## Field Addition Rule

Adding a durable field requires a short owner note before it becomes a stable
surface:

| Requirement | Question to answer |
| --- | --- |
| Owner | Which module or document owns the field meaning? |
| Consumer | Which runtime, test, doc, or report reads it? |
| Lifecycle | Is it source truth, derived, reviewable, temporary, supersedable, or rebuildable? |
| Privacy classification | Can it appear in public fixtures, prompts, MCP payloads, sync bundles, or only local private reports? |
| Projection policy | Which profile includes it, and which profile must drop it? |

If those answers are not known, keep the field in an experimental sidecar or a
local diagnostic report until a real consumer proves it should become stable.

## Cannot Claim

This discipline only controls field width and projection. It does not prove:

- product quality;
- high-risk correctness;
- professional certification;
- live recall quality;
- semantic-sidecar quality;
- source truth without source reopen.

The shared `cannot_claim` markers are:

- `field_completeness_is_not_product_quality`;
- `wide_metadata_does_not_replace_source_reopen`.

Keep `cannot_claim` close to the claim it protects:

- runner JSON should carry active run-level or track-local `cannot_claim`
  entries when a reader could over-read that run;
- selected profile metadata may include its default `cannot_claim` list because
  it explains the active report surface;
- nested validation or rerun-guidance blocks should add only their local
  boundary and point back to the parent report/evidence owner for inherited
  run-level claims;
- inactive profile ladders, docs maps, and fixture indexes should prefer counts
  plus a canonical docs pointer instead of mirroring every caveat list;
- long repeated caveat lists belong in the owning evidence or methodology page,
  not in every runner, test fixture, and navigation document.

## Verification

`tests/aippocampus/test_schema_profiles.py` proves the narrow contract:

- an `identity_minimal` record round-trips without governance, diagnostic, or
  high-risk fields;
- `retrieval_runtime` accepts an ordinary recall record without high-risk
  extras;
- `high_risk_required` can require authority/review/lifecycle/privacy/conflict
  and source-reopen policy without widening ordinary recall;
- `diagnostic_metrics` stays separate from high-risk projection.
