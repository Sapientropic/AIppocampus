# PersonaMem Readiness Gate

Role: benchmark-readiness boundary for PersonaMem / PersonaMem-v2.
Status: current design gate for #1159; not a benchmark result.

PersonaMem-style benchmarks are the right future test for source-supported
personalization, but they should stay staged until AIppocampus has the profile
surface they are meant to evaluate. Running the full benchmark before that
would mostly measure source retrieval plus reader improvisation, not durable
profile memory.

## Readiness Decision

Do not run a full PersonaMem or PersonaMem-v2 result as an AIppocampus quality
claim until a Ficus-style personal-impression layer exists on top of the
source-backed AIppo contract path.

Today AIppocampus has:

- source-backed recall and source-reopen routes;
- AIppo working-contract fixtures for low-risk workflow guidance;
- foreground profile-like-detail suppression and source-reopen boundaries;
- evidence docs that separate retrieval, answer generation, privacy, and cost.

That is enough to plan PersonaMem, and enough for a tiny diagnostic pilot. It
is not enough to claim personalization quality.

## Required Product Capabilities

A full PersonaMem run becomes meaningful only after these capabilities exist
and have their own deterministic tests:

| Capability | Required boundary |
| --- | --- |
| Source-supported profile extraction | Candidate preferences or traits must cite source refs and preserve uncertainty. |
| Ficus-style impression lifecycle | Impressions need status such as candidate, challenged, stale, superseded, ripe, or masked. |
| Privacy and hard-mask policy | Sensitive or over-personalized details must stay masked unless an explicit profile permits use. |
| Conflict and currentness handling | Newer corrections must beat stale impressions; conflicting evidence should request reopen or review. |
| Response adaptation contract | The benchmark must measure when an impression changes the answer, not just whether retrieval found text. |
| Baseline separation | No-memory, source-retrieval-only, AIppo/Ficus profile, and oracle context arms must stay separate. |

AIppo working contracts can guide low-risk task behavior after source support.
They are not user-profile truth. Ficus-style impressions, when implemented,
should follow the same source-backed discipline but carry stronger privacy and
lifecycle gates.

## Minimal Diagnostic Pilot

A pre-readiness pilot may exist, but it must be labeled diagnostic-only.

Suggested shape:

- 3-5 public-safe synthetic or public-dialogue cases;
- one stable preference, one updated preference, one challenged/stale
  preference, one privacy-mask case, and one no-personalization control;
- no private history and no raw benchmark corpus committed;
- fixed reader/evaluator metadata if a model is used;
- report fields for profile extraction, source support, adaptation, privacy
  behavior, latency, token/cost, and reader dependency.

The pilot may test schema, report shape, and obvious red lines. It must not be
used as a PersonaMem score, a broad personalization claim, or evidence that
source-backed retrieval alone solves profile memory.

## Metrics To Keep Separate

PersonaMem reports should not collapse profile quality into one memory score.
At minimum, report:

- `profile_extraction_supported_rate`;
- `source_ref_coverage`;
- `stale_or_challenged_preference_error_rate`;
- `privacy_mask_violation_count`;
- `personalization_response_delta`;
- `reader_dependency_notes`;
- `retrieval_latency_ms` and `reader_latency_ms`;
- token and cost estimates for retrieval, profile construction, and answering.

Miss taxonomy should distinguish retrieval miss, source-visible but profile
miss, stale profile used, privacy mask failure, response adaptation miss,
evaluator mismatch, and reader hallucination.

## Can Claim

- PersonaMem is staged behind AIppo/Ficus profile-readiness.
- A pre-readiness pilot, if added later, can validate schema and red-line
  behavior only.
- AIppocampus has documented what profile capabilities must exist before a full
  PersonaMem result is meaningful.

## Cannot Claim

- PersonaMem or PersonaMem-v2 score.
- Personalization quality from source retrieval alone.
- User profile truth from AIppo working contracts, Dream material, summaries,
  semantic sidecars, or model-organized impressions.
- Privacy-safe profile use without the hard-mask and lifecycle gates above.
- Broad life-wide memory quality, hosted profile behavior, or SOTA.

## Next Implementation Link

The next useful product slice is not a benchmark run. It is a small
source-backed impression compiler with:

- source refs for each candidate impression;
- lifecycle/currentness states;
- explicit privacy masks;
- a source-reopen or review path before foreground use;
- deterministic fixtures proving stable, updated, challenged, masked, and
  no-personalization cases.

Only after that layer exists should this track graduate from readiness gate to
benchmark harness.
