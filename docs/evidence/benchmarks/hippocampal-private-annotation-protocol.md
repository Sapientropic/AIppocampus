# Hippocampal Private Real-History Annotation Protocol

Status: protocol for a future private pilot, not a committed dataset or public
quality claim.

Source issue: #232.
Parent plan:
[`hippocampal-recall-plan.md`](reports/hippocampal/hippocampal-recall-plan.md).

This protocol defines how to create a small private real-history validation set
for H1 pattern completion and H2 pattern separation after the synthetic runner
and scoring contract are stable. It keeps private material local while allowing
a sanitized dated report to publish aggregate outcomes and cannot-claim
boundaries.

## Proceed Gate

Run this private pilot only after the synthetic fixture external validity gate
has enough signal:

- the public-safe synthetic H1/H2 runner and report schema are stable;
- hard-negative scoring catches near-neighbor lures, unsupported speech,
  superseded currentness, and surface paraphrase lures;
- reports stay sanitized by default and preserve `cannot_claim` boundaries;
- synthetic misses are not dominated by one author's phrasing style;
- the D/I matrix exposes sparse cells as `diagnostic_only` instead of hiding
  them inside one aggregate.

The private pilot is a validation slice. It must not become the first place
where schema, scoring, or privacy rules are invented.

## Sampling Plan

Start with 20 scenes. Annotation time estimate: 15-30 minutes per scene,
including source reopen, distractor search, label entry, and review.

Each scene should include:

- themes discussed at least three times, so the target is not a one-off phrase;
- cross-thread decision evolution, especially where stance or framing changed;
- at least one naturally degraded recall prompt from the user, not only an
  author-invented query;
- at least one realistic distractor that could fool lexical or embedding-only
  search;
- enough clean-source context for a reviewer to verify target, distractor, and
  forbidden-claim labels without relying on summaries.

Reject scenes that require exposing sensitive private text in a public report,
that cannot be reopened from clean source, or where the target/distractor
boundary cannot be explained without leaking the content itself.

## Truth-Source Independence

The tested recall system must not generate its own truth labels.

Allowed truth sources:

- primary human annotation from reopened clean source;
- frozen hand-authored synthetic labels for schema and scorer validation;
- model-generated candidate phrasings only after human acceptance;
- independent reviewer confirmation before a private pilot row becomes a
  scored case.

Disallowed primary truth sources:

- AIppocampus recall output being used as the target label;
- semantic sidecars alone being treated as source truth;
- an LLM generating expected refs and then judging whether the same output was
  correct;
- summaries, dream findings, cognitive portraits, or memory candidates without
  reopened source refs.

## Label Fields

Private annotation rows stay local or in a gitignored pack. Use portable field
names so a sanitized report can be generated without copying private text.

| Field | Required | Public report form |
| --- | --- | --- |
| `protocol_version` | yes | exact value |
| `scene_id_hash` | yes | hash only |
| `case_id_hash` | yes | hash only |
| `degradation_level` | yes | `D0`-`D6` |
| `interference_level` | yes | `I0`-`I5` |
| `theme_family` | yes | coarse public-safe bucket |
| `natural_prompt_origin` | yes | `user_prompt`, `reviewer_paraphrase`, or `synthetic_control` |
| `target_ref_hashes` | yes | hash/count only |
| `distractor_ref_hashes` | yes | hash/count only |
| `expected_decision` | yes | `evidence`, `scent`, or `skip` |
| `ambiguity_policy` | yes | `single_target`, `multi_candidate_scent`, or `skip_on_ambiguity` |
| `forbidden_claims_sanitized` | yes | category labels only |
| `truth_source` | yes | reviewer/frozen-fixture class, never raw text |
| `reviewer_role_ids` | yes | role labels, not personal identity |
| `adjudication_status` | yes | status enum |
| `cannot_claim` | yes | public-safe strings |
| `privacy_scan_status` | yes | pass/fail summary |

Raw private text, local paths, private registry details, private thread titles,
and unsanitized snippets must not enter committed artifacts.

## Reviewer And Adjudication Flow

Use at least two roles:

- annotator: selects candidate scenes, writes initial labels, and records why
  target and distractor refs differ;
- reviewer: reopens clean source independently and accepts, edits, or rejects
  the labels.

Use an adjudicator when there is disagreement about target refs, expected
decision level, distractor realism, or forbidden claims. The adjudicator may be
the maintainer for a 20-scene pilot, but the report must say that the pilot had
single-maintainer adjudication if no independent reviewer was available.

Disagreement handling:

- `accepted`: reviewer confirms the target/distractor boundary from source;
- `accepted_with_edits`: reviewer changes labels while preserving the scene;
- `needs_more_context`: source refs are real but the case pack is too thin;
- `rejected_ambiguous`: target and distractor cannot be separated safely;
- `rejected_privacy`: the case cannot be sanitized for public aggregate use;
- `diagnostic_only`: useful failure discovery, not part of headline metrics.

No row should become headline evidence until it is at least `accepted` or
`accepted_with_edits`.

## Sanitized Dated Report Template

Publish only a dated aggregate report. The report may include hashes and counts
when needed for repeatability, but not raw private text.

```json
{
  "report_id": "hippocampal-private-h1h2-YYYY-MM-DD",
  "protocol_version": "hippocampal_private_annotation_v1",
  "run_date": "YYYY-MM-DD",
  "scene_count": 20,
  "case_count": 0,
  "accepted_scene_count": 0,
  "diagnostic_scene_count": 0,
  "degradation_distribution": {},
  "interference_distribution": {},
  "review_status_counts": {},
  "metrics": {
    "recall_accuracy_by_degradation": {},
    "separation_accuracy_by_interference": {},
    "confabulation_rate": null,
    "privacy_breach_count": 0
  },
  "cannot_claim": [
    "public benchmark quality",
    "full private-history recall quality",
    "human-review generality beyond this pilot",
    "live model quality unless the dated run used live models"
  ],
  "privacy_boundary": {
    "contains_raw_private_text": false,
    "contains_local_paths": false,
    "contains_unsanitized_snippets": false,
    "contains_private_registry_details": false
  }
}
```

If a report needs examples, use synthetic analogues or category-level
descriptions. Do not publish paraphrases that are specific enough to reconstruct
the original private scene.

## Interpretation Boundary

A successful private pilot can support this narrow claim:

> On a maintainer-private, sanitized, source-reviewed 20-scene pilot,
> AIppocampus showed the reported H1/H2 behavior for the named cohort and date.

It cannot claim:

- public benchmark quality;
- broad private real-history quality;
- second-user or cross-device generality;
- live model quality unless live models were actually used in the dated run;
- superiority over external systems without equivalent adapters and protocols.

If the pilot shows poor performance, keep the report. Failed or diagnostic
private pilots are useful evidence for whether synthetic fixture behavior
transfers to real scenes.
