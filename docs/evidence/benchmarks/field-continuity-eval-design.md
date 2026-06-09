# Field Continuity Eval Design

Status: design and public-safe fixture contract for GitHub #982.
Scope: long-term source-backed continuity quality, not a single retrieval
leaderboard score or a private-history publication channel.

Field Continuity asks whether AIppocampus helps a later agent continue with
care across time: recall what should matter, avoid dragging in what should not
matter, reopen source before specific claims, and preserve privacy boundaries
when history is local or sensitive. This is the project-level evaluation shape
for the continuity promise. It complements Track B source-evidence retrieval
and hard-negative tests, but it does not replace them.

Closing #982 means the design, fixture schema, public-safe seed fixture, and
runner report contract exist. It does not approve Beta, Production/Stable,
hosted-service readiness, or broad superiority claims.

## Evaluation Tracks

| Track | Role | Public claim boundary |
| --- | --- | --- |
| `public_dialogue_control` | LoCoMo / LongMemEval-style long conversations for evidence retrieval, topic drift, same-name lures, multilingual prompts, and false activation. | Useful public control for dialogue memory behavior; not proof of cross-thread project or agent-work continuity. |
| `public_agent_trajectory` | SWE-Hero / OpenHands / MemoryAgentBench-style agent traces for route attempts, tool/test failures, updates, conflicts, and forgetting or correction behavior. | Public or redistributable traces can support agent-work continuity claims only within their trace source shape. |
| `public_vcs_future_event` | Pull requests, reverts, reopened issues, patchsets, SATD, workaround removal, and future-window events with hard labels. | Supports source-backed future-event recall and stale-route suppression, not personal/life-wide continuity. |
| `synthetic_public_safe` | Small checked-in fixtures derived from public field-report shapes, with raw prompts and raw source text removed. | Contract smoke and regression guard only; field reports are seeds, not product proof. |
| `private_dogfood` | Local real-history aggregate runs using the same schema and reporting rules. | Private-dogfood-only unless the case source is redistributable. Public reports may include hashes and aggregates only. |

Private dogfood remains important because AIppocampus is partly about
life-wide continuity. It cannot be the sole external-facing quality claim.
Any claim that cannot be backed by public or redistributable artifacts must be
marked `private_dogfood_only`.

## Scenario Coverage

| Scenario family from #982 | Public dialogue | Public agent trajectory | Public VCS hard event | Synthetic public-safe | Private dogfood |
| --- | --- | --- | --- | --- | --- |
| Cross-month history | Yes, if the corpus has dated sessions. | Yes, if traces span sessions or issue timelines. | Yes, through dated issue/PR windows. | Shape only. | Yes, aggregate only. |
| User correction of old facts or preferences | Yes for dialogue preference correction. | Yes for trace updates and changed constraints. | Limited to project facts and patches. | Covered by route-correction fixture shape. | Yes, aggregate only. |
| Same-name entities / wrong twin lures | Yes. | Yes, especially repo/file/issue lures. | Yes, through same-name files/issues/branches. | Shape can be added as negative controls. | Yes, aggregate only. |
| Project path migration | Limited. | Yes when trace paths or repo roots move. | Yes when file moves/renames are labelled. | Shape only. | Yes, aggregate only. |
| Multilingual and CJK/English mixed prompts | Yes when corpus includes language variation. | Possible if trace prompts are multilingual. | Mostly prompt wrapper, not VCS label itself. | Covered by multilingual route-correction fixture shape. | Yes, aggregate only. |
| Stale or superseded source | Yes for dated corrections. | Yes for failed/repaired attempts. | Strong fit through reverts, reopen, and follow-up patches. | Covered by stale-route control. | Yes, aggregate only. |
| Privacy-sensitive fragments | Public corpora can test redaction shape only. | Public traces can test tool-error/report redaction. | Public labels can test path/secret redaction rules. | Covered by report-leakage and forbidden-field contract. | Yes, but public report remains hash/aggregate only. |
| Current instruction conflicts with old source | Yes as dialogue contradiction control. | Yes as updated task constraints. | Yes as later issue/PR instruction superseding earlier state. | Shape can be added as a hard negative. | Yes, aggregate only. |

## Fixture Schema

The checked-in public-safe fixture lives at
`benchmark_corpus/field_continuity/fixture.json`. It is deliberately small and
source-safe so a contributor can inspect the contract without private data.

Top-level fields:

- `schema_version`: currently `aippocampus.field_continuity_fixture.v1`.
- `fixture_id` and `fixture_license`: stable fixture identity and reuse terms.
- `source`: source issue, design issue, field-report discussion, and boundary
  status.
- `boundary`: booleans that state whether the fixture is public-safe,
  synthetic, copied from raw prompt text, copied from raw source snippets, or
  contains private real history.
- `arms`: all compared arms for the fixture.
- `scenario_families`: declared families, expected behavior, and non-claims.
- `private_seed_reporting_contract`: allowed aggregate fields and forbidden
  private fields for private dogfood reports.
- `cases`: public-safe case rows.

Each case includes:

- `case_id`, `scenario_family`, `case_kind`, and `prompt_shape`.
- `seed_hash_sha256` rather than raw prompt or raw source text.
- `expected_metrics` and `negative_control_tags`.
- `arms`, where each arm reports source-safe boolean metric outcomes.

The fixture intentionally treats summaries, semantic matches, and hook scents
as navigation layers. Only source reopening or bounded evidence can support
specific continuity claims.

## Arms

| Arm | Meaning | Why it exists |
| --- | --- | --- |
| `no_memory` | Agent has no continuity route for the case. | Separates genuine continuity value from generic caution or refusal. |
| `fts_only` | Direct full-text search without source-backed route planning. | Checks whether keyword search alone can recover source and suppress wrong lures. |
| `summary_first` | Starts from generated summaries or rollups before source. | Detects prompt-budget pressure, leakage risk, and overconfident stale summaries. |
| `semantic_only` | Uses vector/semantic matching without the source-backed route contract. | Detects latency cost and lure sensitivity from semantic similarity alone. |
| `hook_only` | Ambient foreground scent without deepen/reopen behavior. | Keeps foreground-hook usefulness separate from hook-only sufficiency. |
| `active_recall_or_source_reopen` | AIppocampus route that treats source as ground and reopens or bounds claims. | The active source-backed continuity behavior under test. |
| `stale_wrong_route_control` | Deliberately wrong or stale route. | Guards against wrong-family persistence and stale-route dominance. |

Graphiti, Zep, Mem0, or other system baselines can be added later only after
their source shape, privacy boundary, and comparable route/reopen affordance are
documented. The design should not create a fake fairness layer just to compare
unlike systems.

## Metrics

The runner reports metric families separately instead of collapsing them into
one score:

- Route quality: `progressive_route_recovery`,
  `manual_query_invention_required` when added.
- Source authority: `source_reopen_success`,
  `exact_prompt_or_tool_failure_recovery`.
- Claim discipline: `uncertainty_boundary_preserved`,
  `abstains_when_evidence_insufficient`,
  `external_state_overclaim`.
- No-recall and no-harm controls: `wrong_family_persistence`,
  `irrelevant_memory_drag`.
- Privacy and reporting: `report_leakage`.
- Cost: `latency_budget_overrun`, `prompt_budget_overrun`.
- Human/product alignment: field-report alignment or user-visible helpfulness
  may be added when the source is public or aggregated safely.

The default report keeps top-level metrics for
`active_recall_or_source_reopen` and also emits `metrics.by_arm` for every arm.
That makes regressions readable without turning the eval into a leaderboard.

## Runner Report

`benchmarks/aippocampus/benchmark_field_continuity.py --json` emits:

- `config`: deterministic/public/private/live-model boundary.
- `fixture_validation`: schema, arms, scenario families, negative controls, and
  private-seed reporting contract.
- `metrics`: active-arm rates plus `metrics.by_arm`.
- `quality_gates`: fixture validity, field-report link, negative controls,
  private seed contract, and active-arm boundary preservation.
- `privacy_boundary`: whether raw prompt text, raw source text, or absolute
  paths were emitted.
- `private_seed_reporting_contract`: hash-only and aggregate-only constraints.
- `cases`: sanitized case summaries.
- `cannot_claim`: explicit non-claims for live, private, hook-only, semantic,
  hosted, or cross-device quality.

Public reports must not include raw prompts, raw source snippets, local paths,
rollout ids, thread ids, session ids, credentials, cookies, or raw tool-error
text. Private dogfood reports use the same metric keys, but only publish
aggregate rows with hash ids and date buckets.

## Beta Readiness Link

Field Continuity is a Beta prerequisite because Beta should not imply that
source-backed continuity is merely a retrieval smoke. This design closes the
#982 prerequisite at the design/fixture/runner-contract layer.

Remaining Beta evidence still needs dated run outputs, release-note agreement,
README/API claim consistency, and any active owner-issue blockers or waivers in
`docs/evidence/readiness/classifier-policy.md`. A closed design issue is not a
package classifier decision.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_field_continuity.py --json
python -m unittest tests.aippocampus.test_benchmark_field_continuity
```

