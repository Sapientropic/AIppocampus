# Public Readiness Verification

Initial evidence date: 2026-05-27.
Repository-layout command paths refreshed: 2026-05-29.

## Currentness Card

page_last_structural_review: 2026-06-18; this page is a dated verification
ledger and router.

latest_numeric_claim_source: `docs/evidence/current-claims.md`; this page keeps
the command evidence that supported earlier rows.

current_status: use this page to reopen what was actually run, then compare
against `stage-0-5-readiness.md` and Current Claims before making a present-tense
readiness statement.

remaining_gaps: public marketplace submission, fresh-clone review, and wider
provider/client sync evidence still need explicit dated verification before
claim expansion.

owner_routes: `docs/evidence/readiness/stage-0-5-readiness.md`,
`docs/evidence/current-claims.md`, `docs/evidence/benchmark-evidence-map.md`.

next_verification_command: `python tools\aippocampus\docs\check_docs_health.py --json`.

This file is a dated verification ledger. It preserves summarized command
evidence for release-readiness work, but the current Stage 0-5 claim boundary
lives in `docs/evidence/readiness/stage-0-5-readiness.md` and the canonical product requirements
remain in `docs/roadmap.md`.

Older entries preserve the historical `--tier fast` command name as evidence of
what was run at the time. The current test taxonomy is defined in
`tools/aippocampus/test_tier_manifest.py`: use `--tier quick` for the small local
inner loop, `--tier pr` for the fast local PR gate, and `--tier broad-pr` for
the broad deterministic pre-merge lane.

For the navigation map that connects benchmark runners, smoke scripts, corpus
records, and this ledger, see `docs/evidence/benchmark-evidence-map.md`.

Stable privacy rules live in `docs/guides/community/privacy-security-checklist.md`. Do not paste
raw command JSON here: local smoke outputs may contain machine-specific
temporary paths, so this document keeps only summarized evidence.

## Reader Path

This file is now the slim entrypoint and anchor-preserving map. Dated
evidence detail lives under [`public-readiness/`](public-readiness/).

| Need | Open |
| --- | --- |
| Release, host, provider, VCS, E2E50, and Stage 0-5 evidence notes | [`public-readiness/dated-ledger.md`](public-readiness/dated-ledger.md) |
| Continuous-memory attribution, cost/harm, and expected-null readouts | [`public-readiness/continuous-memory.md`](public-readiness/continuous-memory.md) |
| First-recall smoke, command ledger, scan notes, and example bundle | [`public-readiness/command-ledger.md`](public-readiness/command-ledger.md) |
| Current remaining gaps | [`#remaining-public-readiness-gaps`](#remaining-public-readiness-gaps) |

## 2026-06-12 Issue #279 E2E50 Public-safe 50-case Behavior Pack

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-12-issue-279-e2e50-public-safe-50-case-behavior-pack`](public-readiness/dated-2026-06-09-to-12.md#2026-06-12-issue-279-e2e50-public-safe-50-case-behavior-pack).

## 2026-06-10 Issue #1154 E2E50 Public-safe Behavior Pack Pivot

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-10-issue-1154-e2e50-public-safe-behavior-pack-pivot`](public-readiness/dated-2026-06-09-to-12.md#2026-06-10-issue-1154-e2e50-public-safe-behavior-pack-pivot).

## 2026-06-10 Issue #1086 E2E50 Private / Local Seed Follow-up

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-10-issue-1086-e2e50-private-local-seed-follow-up`](public-readiness/dated-2026-06-09-to-12.md#2026-06-10-issue-1086-e2e50-private-local-seed-follow-up).

## 2026-06-09 Issue #994 E2E50 Public-safe 20-case Seed Pack

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-994-e2e50-public-safe-20-case-seed-pack`](public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-994-e2e50-public-safe-20-case-seed-pack).

## 2026-06-09 Issue #963 Track B Top-k Miss Repair

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-963-track-b-top-k-miss-repair`](public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-963-track-b-top-k-miss-repair).

## 2026-06-09 Issue #1053 Preference Source-review Floor And Taxonomy Slice

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-1053-preference-source-review-floor-and-taxonomy-slice`](public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-1053-preference-source-review-floor-and-taxonomy-slice).

## 2026-06-09 Issue #1020 Claude Code Hook Contract Slice

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-1020-claude-code-hook-contract-slice`](public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-1020-claude-code-hook-contract-slice).

## 2026-06-09 - Source-review taxonomy and public shadow rerun

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-09---source-review-taxonomy-and-public-shadow-rerun`](public-readiness/dated-2026-06-09-to-12.md#2026-06-09---source-review-taxonomy-and-public-shadow-rerun).

## 2026-06-09 Issue #998 Claude Code Real-Host Dogfood Refresh

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-998-claude-code-real-host-dogfood-refresh`](public-readiness/dated-2026-06-09-to-12.md#2026-06-09-issue-998-claude-code-real-host-dogfood-refresh).

## 2026-06-12 Rollout Hard-Event Route-Chain Calibration

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-12-rollout-hard-event-route-chain-calibration`](public-readiness/dated-2026-06-09-to-12.md#2026-06-12-rollout-hard-event-route-chain-calibration).

## 2026-06-12 Rollout Hard-Event Cohort V2

Moved detail: [`public-readiness/dated-2026-06-09-to-12.md#2026-06-12-rollout-hard-event-cohort-v2`](public-readiness/dated-2026-06-09-to-12.md#2026-06-12-rollout-hard-event-cohort-v2).

## 2026-06-07 Issue #784 Provider-Key Bridge OS Store Smoke

Moved detail: [`public-readiness/dated-2026-06-04-to-07.md#2026-06-07-issue-784-provider-key-bridge-os-store-smoke`](public-readiness/dated-2026-06-04-to-07.md#2026-06-07-issue-784-provider-key-bridge-os-store-smoke).

## 2026-06-05 Issue #643 R2 Provider Metadata Evidence Smoke

Moved detail: [`public-readiness/dated-2026-06-04-to-07.md#2026-06-05-issue-643-r2-provider-metadata-evidence-smoke`](public-readiness/dated-2026-06-04-to-07.md#2026-06-05-issue-643-r2-provider-metadata-evidence-smoke).

## 2026-06-05 Issue #697 Released PyPI And Client-Matrix Refresh

Moved detail: [`public-readiness/dated-2026-06-04-to-07.md#2026-06-05-issue-697-released-pypi-and-client-matrix-refresh`](public-readiness/dated-2026-06-04-to-07.md#2026-06-05-issue-697-released-pypi-and-client-matrix-refresh).

## 2026-06-05 Issue #307 External Uvx Source-Install Probe

Moved detail: [`public-readiness/dated-2026-06-04-to-07.md#2026-06-05-issue-307-external-uvx-source-install-probe`](public-readiness/dated-2026-06-04-to-07.md#2026-06-05-issue-307-external-uvx-source-install-probe).

## 2026-06-04 Issue #104 Post-Migration R2 Provider Re-Smoke

Moved detail: [`public-readiness/dated-2026-06-04-to-07.md#2026-06-04-issue-104-post-migration-r2-provider-re-smoke`](public-readiness/dated-2026-06-04-to-07.md#2026-06-04-issue-104-post-migration-r2-provider-re-smoke).

## 2026-06-04 React VCS Production-Like Source Disambiguation

Moved detail: [`public-readiness/dated-2026-06-04-to-07.md#2026-06-04-react-vcs-production-like-source-disambiguation`](public-readiness/dated-2026-06-04-to-07.md#2026-06-04-react-vcs-production-like-source-disambiguation).

## 2026-05-28 Layout Refresh

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-28-layout-refresh`](public-readiness/dated-2026-05.md#2026-05-28-layout-refresh).

## 2026-05-30 Public-Core Boundary Refresh

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-public-core-boundary-refresh`](public-readiness/dated-2026-05.md#2026-05-30-public-core-boundary-refresh).

## 2026-05-30 Memory Pain Fixture Evidence

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-memory-pain-fixture-evidence`](public-readiness/dated-2026-05.md#2026-05-30-memory-pain-fixture-evidence).

## 2026-05-31 Russian Real-History Memory-Pain Smoke

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-31-russian-real-history-memory-pain-smoke`](public-readiness/dated-2026-05.md#2026-05-31-russian-real-history-memory-pain-smoke).

## 2026-05-30 Provider And Cross-Agent Continuity Slice

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-provider-and-cross-agent-continuity-slice`](public-readiness/dated-2026-05.md#2026-05-30-provider-and-cross-agent-continuity-slice).

## 2026-05-31 Windows Standalone Binary Smoke

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-31-windows-standalone-binary-smoke`](public-readiness/dated-2026-05.md#2026-05-31-windows-standalone-binary-smoke).

## 2026-05-31 Windows Binary Re-Smoke After Package Refactors

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-31-windows-binary-re-smoke-after-package-refactors`](public-readiness/dated-2026-05.md#2026-05-31-windows-binary-re-smoke-after-package-refactors).

## 2026-05-31 Provider Entrypoint And Storage Boundary Refresh

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-31-provider-entrypoint-and-storage-boundary-refresh`](public-readiness/dated-2026-05.md#2026-05-31-provider-entrypoint-and-storage-boundary-refresh).

## 2026-05-30 Track D Synthetic Runner Evidence

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-track-d-synthetic-runner-evidence`](public-readiness/dated-2026-05.md#2026-05-30-track-d-synthetic-runner-evidence).

## 2026-05-30 Real Codex Long-Session Continuity Smoke

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-real-codex-long-session-continuity-smoke`](public-readiness/dated-2026-05.md#2026-05-30-real-codex-long-session-continuity-smoke).

## 2026-05-30 P0 Evidence Refresh

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-p0-evidence-refresh`](public-readiness/dated-2026-05.md#2026-05-30-p0-evidence-refresh).

## 2026-05-30 MCP, Plugin, And Sync Boundary Refresh

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-mcp-plugin-and-sync-boundary-refresh`](public-readiness/dated-2026-05.md#2026-05-30-mcp-plugin-and-sync-boundary-refresh).

## 2026-05-30 Issues #55/#56 Evidence Closeout

Moved detail: [`public-readiness/dated-2026-05.md#2026-05-30-issues-5556-evidence-closeout`](public-readiness/dated-2026-05.md#2026-05-30-issues-5556-evidence-closeout).

## 2026-06-01 - Continuous-memory cost and harm ledger

Moved detail: [`public-readiness/continuous-memory.md#2026-06-01---continuous-memory-cost-and-harm-ledger`](public-readiness/continuous-memory.md#2026-06-01---continuous-memory-cost-and-harm-ledger).

## 2026-06-01 - Continuous-memory pre-registration

Moved detail: [`public-readiness/continuous-memory.md#2026-06-01---continuous-memory-pre-registration`](public-readiness/continuous-memory.md#2026-06-01---continuous-memory-pre-registration).

## 2026-06-02 - Continuous-memory scenario provenance and holdout controls

Moved detail: [`public-readiness/continuous-memory.md#2026-06-02---continuous-memory-scenario-provenance-and-holdout-controls`](public-readiness/continuous-memory.md#2026-06-02---continuous-memory-scenario-provenance-and-holdout-controls).

## 2026-06-02 - Continuous-memory host-native baseline contract

Moved detail: [`public-readiness/continuous-memory.md#2026-06-02---continuous-memory-host-native-baseline-contract`](public-readiness/continuous-memory.md#2026-06-02---continuous-memory-host-native-baseline-contract).

## 2026-06-03 - Continuous-memory cost/harm sensitivity sweep

Moved detail: [`public-readiness/continuous-memory.md#2026-06-03---continuous-memory-costharm-sensitivity-sweep`](public-readiness/continuous-memory.md#2026-06-03---continuous-memory-costharm-sensitivity-sweep).

## 2026-06-10 - Context-loss continuous-memory diagnostic slice

Moved detail: [`public-readiness/continuous-memory.md#2026-06-10---context-loss-continuous-memory-diagnostic-slice`](public-readiness/continuous-memory.md#2026-06-10---context-loss-continuous-memory-diagnostic-slice).

## 2026-06-08 - Continuous-memory preregistered repeat readout

Moved detail: [`public-readiness/continuous-memory.md#2026-06-08---continuous-memory-preregistered-repeat-readout`](public-readiness/continuous-memory.md#2026-06-08---continuous-memory-preregistered-repeat-readout).

## 2026-06-09 - Continuous-memory expected-null interpretation

Moved detail: [`public-readiness/continuous-memory.md#2026-06-09---continuous-memory-expected-null-interpretation`](public-readiness/continuous-memory.md#2026-06-09---continuous-memory-expected-null-interpretation).

## 2026-06-03 - First-recall onboarding receipt smoke

Moved detail: [`public-readiness/command-ledger.md#2026-06-03---first-recall-onboarding-receipt-smoke`](public-readiness/command-ledger.md#2026-06-03---first-recall-onboarding-receipt-smoke).

## Command Ledger

Moved detail: [`public-readiness/command-ledger.md#command-ledger`](public-readiness/command-ledger.md#command-ledger).

## Scan Notes

Moved detail: [`public-readiness/command-ledger.md#scan-notes`](public-readiness/command-ledger.md#scan-notes).

## Example Bundle

Moved detail: [`public-readiness/command-ledger.md#example-bundle`](public-readiness/command-ledger.md#example-bundle).

## Remaining Public-Readiness Gaps

Use this table as the current owner route. Do not turn these rows into public
claims until the linked owner produces dated evidence and `current-claims.md` or
`stage-0-5-readiness.md` is updated.

| Gap | Owner route | Next action | Boundary |
| --- | --- | --- | --- |
| Evidence drift after code changes | `tools/aippocampus/test_plan.py`, `tools/aippocampus/docs/check_docs_health.py`, and the relevant focused test | Re-run the changed-surface plan before moving a row from evidence detail into current claims. | Dated ledgers are audit detail, not current product copy. |
| Codex-only provider-scoped status output | [Public API environment/provider section](../../guides/public-api.md#environment-variables) and `aippocampus onboard --provider auto --status` | Add an explicitly scoped status shape only if a future claim needs Codex-only provider status. | The current provider matrix is read-only local readiness, not a Codex-only proof. |
| Interactive Codex Desktop marketplace UI coverage | [Install Guide](../../guides/install-guide.md) and [Ecosystem Integration Matrix](../../guides/ecosystem-integration-matrix.md) | Run a manual UI or external install review before claiming every Codex client surface. | Headless app-server/plugin probes are host-exposure evidence, not full UI coverage. |
| Broader provider/client sync coverage | [Stage 0-5 readiness](stage-0-5-readiness.md), [encrypted sync design](../../architecture/ops/encrypted-sync-v1.md), and sync/object-storage docs | Add a scoped provider/client evidence issue before widening Stage 3 claims. | Local HTTP object storage stays simulation; one R2 run is managed-provider evidence, not a matrix. |
| Stage 2 life-wide memory breadth | [proof-slice maturity](proof-slice-maturity.md), [current claims](../current-claims.md), and source-review reports | Broaden public-safe suppressed-label recovery and reviewed failure feedback before widening life-wide quality claims. | Sidecar labels, semantic summaries, and source-review diagnostics are navigation/evidence-selection layers, not source truth. |
| Evidence & Field Reports Discussion route | [community field-report boundary](../community-field-reports.md) and the public evidence page | Use the field-report boundary until a GitHub Discussion category is verified or created. | Do not claim a dedicated Discussion category exists from local docs alone. |
