from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "aippocampus" / "github" / "project_triage.py"
SPEC = importlib.util.spec_from_file_location("project_triage", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
project_triage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = project_triage
SPEC.loader.exec_module(project_triage)


def issue(number: int, title: str, body: str = "", labels: tuple[str, ...] = ()):
    return project_triage.IssueContext(number=number, title=title, body=body, labels=labels)


def test_sync_child_issue_gets_full_ready_fields() -> None:
    result = project_triage.infer_triage(
        issue(
            36,
            "Run physical second-machine cross-device sync smoke",
            "Parent: #21\n\n## Source docs and tools\n\n- `docs/architecture/encrypted-sync-v1.md`",
        )
    )

    assert result.status == "Ready"
    assert result.track == "Sync"
    assert result.kind == "Smoke"
    assert result.stage == "Stage 3"
    assert result.evidence == "None"
    assert result.priority == "P0"
    assert result.source.startswith("GitHub issue #36; parent issue #21")


def test_life_wide_source_review_issue_is_p0_implementation() -> None:
    result = project_triage.infer_triage(
        issue(
            34,
            "Use source-review failures to improve semantic label evidence generation",
            "Parent: #20\n\n## Scope\nImprove prompt/schema/evidence selection.",
        )
    )

    assert result.status == "Ready"
    assert result.track == "Life-wide memory"
    assert result.kind == "Implementation"
    assert result.stage == "Stage 2"
    assert result.priority == "P0"


def test_ambiguous_issue_stays_in_inbox_without_false_track() -> None:
    result = project_triage.infer_triage(issue(99, "Something vague"))

    assert result.status == "Inbox"
    assert result.track is None
    assert result.kind is None
    assert result.stage is None
    assert result.evidence == "None"
    assert result.priority == "P2"
    assert result.source == "GitHub issue #99"


def test_source_ignores_backticked_command_bullets() -> None:
    result = project_triage.infer_triage(
        issue(
            53,
            "Investigate foreground semantic hook timeouts across model alias",
            "\n".join(
                [
                    "- `--semantic-timeout 20` is a runtime flag, not a source file.",
                    "- `docs/roadmap.md`",
                    "- tools/aippocampus/smoke/example.py",
                ]
            ),
        )
    )

    assert result.source == (
        "GitHub issue #53; docs/roadmap.md; tools/aippocampus/smoke/example.py"
    )


def test_planned_updates_preserve_manual_values_but_promote_inbox() -> None:
    triage = project_triage.infer_triage(
        issue(38, "Run managed cloud or real object-storage sync smoke", "Parent: #21")
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Inbox",
            "Track": "Sync",
            "Kind": "Smoke",
            "Evidence": "None",
        },
        triage,
    )

    assert updates["Status"] == "Ready"
    assert "Track" not in updates
    assert "Kind" not in updates
    assert updates["Stage"] == "Stage 3"
    assert updates["Priority"] == "P0"
    assert updates["Source"].startswith("GitHub issue #38")


def test_benchmark_parent_overrides_semantic_sidecar_life_wide_keywords() -> None:
    result = project_triage.infer_triage(
        issue(
            217,
            "Add anti-circular controls for semantic-sidecar benchmark claims",
            "Parent: #216\n\nPrevent semantic-sidecar benchmark results from validating an LLM-generated label loop.",
        )
    )

    assert result.status == "Ready"
    assert result.track == "Benchmarks & Research"
    assert result.kind == "Smoke"
    assert result.stage == "Research"
    assert result.priority == "P1"
    assert result.warnings == (
        "missing_source_docs: design/benchmark issue should link canonical "
        "docs/... or skills/aippocampus/references/... context before implementation",
    )


def test_design_benchmark_issue_with_source_docs_has_no_warning() -> None:
    result = project_triage.infer_triage(
        issue(
            218,
            "Replace first-N ShareGPT benchmark slices with seeded stratified sampling",
            "Parent: #216\n\n## Source\n\n- `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`",
        )
    )

    assert result.track == "Benchmarks & Research"
    assert result.warnings == ()


def test_ordinary_ambiguous_issue_without_docs_does_not_warn() -> None:
    result = project_triage.infer_triage(issue(99, "Something vague"))

    assert result.status == "Inbox"
    assert result.warnings == ()


def test_hard_negative_issue_does_not_treat_later_as_priority_later() -> None:
    result = project_triage.infer_triage(
        issue(
            244,
            "Add H1 hard-negative confabulation discipline fixture and asymmetric scoring",
            "Parent: #228\n\nA cue matches an old conclusion that was later corrected or replaced.",
        )
    )

    assert result.status == "Ready"
    assert result.track == "Benchmarks & Research"
    assert result.kind == "Implementation"
    assert result.stage == "Research"
    assert result.priority == "P1"


def test_topic_epoch_fragmentation_routes_to_life_wide_not_external_models() -> None:
    result = project_triage.infer_triage(
        issue(
            262,
            "Topic-epoch fragmentation prevents warm ambient cache from helping same-session paraphrases",
            "This is a design gap rather than a provider outage. "
            "The warm ambient cache writes cards but natural same-topic paraphrases use different topic_epoch keys.",
            labels=("bug", "enhancement"),
        )
    )

    assert result.status == "Ready"
    assert result.track == "Life-wide memory"
    assert result.kind == "Implementation"
    assert result.stage == "Stage 2"
    assert result.priority == "P1"
    assert result.milestone == "Ambient Recall Warmth Pass"


def test_hippocampal_child_issue_gets_benchmark_mvp_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            244,
            "Add H1 hard-negative confabulation discipline fixture and asymmetric scoring",
            "Parent: #228\n\nMake honest abstention score better than confidently reopening the wrong source.",
        )
    )

    assert result.milestone == "Hippocampal Benchmark MVP"


def test_external_benchmark_adapter_gets_evidence_hardening_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            258,
            "Assess MemoryAgentBench as an incremental memory-agent benchmark adapter",
            "Parent: #216\n\nEvaluate whether MemoryAgentBench should become an external benchmark adapter.",
        )
    )

    assert result.milestone == "Benchmark Evidence Hardening"


def test_architecture_debt_issue_gets_architecture_slice_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            266,
            "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
            "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
            labels=("enhancement",),
        )
    )

    assert result.milestone == "Architecture Debt Slice 2026-06"


def test_public_readiness_issue_gets_distribution_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            382,
            "Improve agent-facing discoverability without hollow marketing",
            "Public readiness work across README, install guide, agent discovery, and distribution surfaces.",
            labels=("documentation", "enhancement"),
        )
    )

    assert result.status == "Ready"
    assert result.track == "Public readiness"
    assert result.kind == "Docs"
    assert result.stage == "Stage 1"
    assert result.milestone == "Public Readiness & Distribution"


def test_project_planning_automation_gets_distribution_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            383,
            "Extend planning audit to catch orphan Discussions and missing implementation maps",
            "Project triage and planning audit should keep roadmap metadata and implementation maps current.",
            labels=("documentation", "enhancement"),
        )
    )

    assert result.status == "Ready"
    assert result.track == "Public readiness"
    assert result.kind == "Implementation"
    assert result.stage == "Stage 1"
    assert result.milestone == "Public Readiness & Distribution"


def test_public_schema_privacy_issue_stays_in_distribution_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            338,
            "Define public schema metadata namespace and extension rules",
            "Public API schema metadata and privacy extension rules for the public contract.",
            labels=("documentation", "enhancement"),
        )
    )

    assert result.track == "Public readiness"
    assert result.milestone == "Public Readiness & Distribution"


def test_web_chat_import_issue_gets_public_distribution_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            370,
            "Bridge browser/web-chat captures into generic JSONL clean-source import",
            "Browser-local export to generic JSONL clean-source import for provider-neutral conversation intake.",
            labels=("enhancement",),
        )
    )

    assert result.status == "Ready"
    assert result.track == "Public readiness"
    assert result.kind == "Implementation"
    assert result.stage == "Stage 1"
    assert result.milestone == "Public Readiness & Distribution"


def test_cognitive_runtime_issue_gets_runtime_continuity_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            381,
            "Prototype a local search-decision memory adapter",
            "Local search-decision memory adapter for critical agent operations and source-backed runtime continuity.",
            labels=("enhancement",),
        )
    )

    assert result.status == "Ready"
    assert result.track == "Life-wide memory"
    assert result.kind == "Implementation"
    assert result.stage == "Stage 2"
    assert result.milestone == "Cognitive Runtime Continuity"


def test_segmented_index_issue_gets_sync_scale_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            376,
            "Add long-lived single-thread segment build/search scale soak",
            "Segmented index build/search scale soak for shard boundaries and non-blocking fanout budgets.",
            labels=("enhancement",),
        )
    )

    assert result.status == "Ready"
    assert result.track == "GB/TB scale"
    assert result.kind == "Implementation"
    assert result.stage == "Cross-stage"
    assert result.milestone == "Sync & Scale Infrastructure"


def test_security_privacy_issue_gets_hardening_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            352,
            "Refine external-model redaction granularity and project-safe path anchors",
            "Privacy and security hardening for external-model redaction, raw output, and project-safe path anchors.",
            labels=("enhancement",),
        )
    )

    assert result.status == "Ready"
    assert result.track == "External models"
    assert result.kind == "Implementation"
    assert result.stage == "Stage 6"
    assert result.milestone == "Security & Privacy Hardening"


def test_codeql_raw_private_issue_gets_security_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            326,
            "CodeQL follow-up: harden raw/private CLI output surfaces",
            "Security review follow-up for raw/private CLI output and privacy-security boundaries.",
            labels=("bug",),
        )
    )

    assert result.milestone == "Security & Privacy Hardening"


def test_benchmark_privacy_issue_keeps_benchmark_milestone() -> None:
    result = project_triage.infer_triage(
        issue(
            357,
            "Unify benchmark sensitive-content filtering with runtime privacy policy",
            "Benchmark report hardening should align sensitive-content filtering with the runtime privacy boundary.",
            labels=("enhancement",),
        )
    )

    assert result.track == "Benchmarks & Research"
    assert result.milestone == "Benchmark Evidence Hardening"


def test_architecture_debt_issue_routes_to_cross_stage_implementation() -> None:
    result = project_triage.infer_triage(
        issue(
            266,
            "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
            "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
            labels=("enhancement",),
        )
    )

    assert result.status == "Ready"
    assert result.track == "Docs cleanup"
    assert result.kind == "Implementation"
    assert result.stage == "Cross-stage"
    assert result.priority == "P1"


def test_benchmark_parent_beats_hippocampal_keyword_for_external_adapter() -> None:
    result = project_triage.infer_triage(
        issue(
            258,
            "Assess MemoryAgentBench as an incremental memory-agent benchmark adapter",
            "Parent: #216\n\nThis may later feed H1/H2/H5 comparison tables, but the slice is adapter assessment.",
        )
    )

    assert result.milestone == "Benchmark Evidence Hardening"


def test_milestone_update_only_fills_missing_open_issue_milestone() -> None:
    triage = project_triage.infer_triage(
        issue(
            266,
            "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
            "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
        )
    )

    update = project_triage.planned_milestone_update(
        issue(266, "Split aippocampus_runtime/core.py before it becomes hidden architecture debt"),
        triage,
        {"Architecture Debt Slice 2026-06": 5},
    )

    assert update == {
        "planned": "Architecture Debt Slice 2026-06",
        "milestone_number": 5,
    }


def test_milestone_update_preserves_existing_manual_milestone() -> None:
    triage = project_triage.infer_triage(
        issue(
            266,
            "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
            "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
        )
    )

    update = project_triage.planned_milestone_update(
        project_triage.IssueContext(
            number=266,
            title="Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
            body="",
            milestone="Human chosen milestone",
        ),
        triage,
        {"Architecture Debt Slice 2026-06": 5},
    )

    assert update == {
        "current": "Human chosen milestone",
        "planned": "Architecture Debt Slice 2026-06",
        "skipped": "existing_milestone",
    }


def test_milestone_update_skips_low_confidence_inferred_milestone() -> None:
    triage = project_triage.infer_triage(
        issue(
            326,
            "CodeQL follow-up: harden raw/private CLI output surfaces",
            "Security review follow-up for raw/private CLI output and privacy-security boundaries.",
            labels=("bug",),
        )
    )

    update = project_triage.planned_milestone_update(
        issue(
            326,
            "CodeQL follow-up: harden raw/private CLI output surfaces",
            "Security review follow-up for raw/private CLI output and privacy-security boundaries.",
            labels=("bug",),
        ),
        triage,
        {"Security & Privacy Hardening": 8},
    )

    assert triage.confidence == "low"
    assert update == {
        "planned": "Security & Privacy Hardening",
        "skipped": "low_confidence",
    }


def test_single_issue_milestone_permission_error_is_reported(monkeypatch) -> None:
    class MilestoneDeniedClient:
        def rest(self, method: str, path: str, payload: dict | None = None):
            raise project_triage.GitHubRestError(
                403,
                '{"message":"Must have admin rights to Repository."}',
            )

    triage_issue = issue(
        266,
        "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
        "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
    )
    item = {"id": "item-id", "fieldValues": {"nodes": []}}
    monkeypatch.setattr(
        project_triage,
        "ensure_issue_item",
        lambda *args, **kwargs: (item, triage_issue),
    )
    monkeypatch.setattr(project_triage, "apply_updates", lambda *args, **kwargs: None)

    report = project_triage.triage_single_issue(
        MilestoneDeniedClient(),
        "project-id",
        {},
        [],
        "Sapientropic/AIppocampus",
        266,
        dry_run=False,
        assign_milestones=True,
        milestone_numbers={"Architecture Debt Slice 2026-06": 5},
    )

    assert report["milestone_update"] == {
        "planned": "Architecture Debt Slice 2026-06",
        "milestone_number": 5,
        "skipped": "permission_denied",
        "error": "milestone_permission_denied",
    }


def test_external_benchmark_adapter_assessment_is_research_not_smoke() -> None:
    result = project_triage.infer_triage(
        issue(
            258,
            "Assess MemoryAgentBench as an incremental memory-agent benchmark adapter",
            "Parent: #216\n\nEvaluate whether MemoryAgentBench should become an external benchmark adapter. "
            "Plan a public-safe smoke only after feasibility is clear.",
        )
    )

    assert result.status == "Ready"
    assert result.track == "Benchmarks & Research"
    assert result.kind == "Research"
    assert result.stage == "Research"
    assert result.priority == "P1"


def test_default_planned_updates_do_not_repair_existing_wrong_fields() -> None:
    triage = project_triage.infer_triage(
        issue(
            262,
            "Topic-epoch fragmentation prevents warm ambient cache from helping same-session paraphrases",
            "The warm ambient cache writes cards but same-topic paraphrases use different topic_epoch keys.",
            labels=("bug", "enhancement"),
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Archived",
            "Track": "External models",
            "Kind": "Smoke",
            "Stage": "Stage 6",
            "Evidence": "None",
            "Priority": "Later",
            "Source": "GitHub issue #262",
        },
        triage,
    )

    assert updates == {}


def test_repair_managed_fields_fixes_high_confidence_script_owned_misroutes() -> None:
    triage = project_triage.infer_triage(
        issue(
            262,
            "Topic-epoch fragmentation prevents warm ambient cache from helping same-session paraphrases",
            "The warm ambient cache writes cards but same-topic paraphrases use different topic_epoch keys.",
            labels=("bug", "enhancement"),
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Archived",
            "Track": "External models",
            "Kind": "Smoke",
            "Stage": "Stage 6",
            "Evidence": "None",
            "Priority": "Later",
            "Source": "GitHub issue #262",
        },
        triage,
        repair_managed_fields=True,
    )

    assert updates == {
        "Status": "Ready",
        "Track": "Life-wide memory",
        "Kind": "Implementation",
        "Stage": "Stage 2",
        "Priority": "P1",
    }


def test_repair_managed_fields_does_not_overwrite_human_sourced_triage() -> None:
    triage = project_triage.infer_triage(
        issue(
            262,
            "Topic-epoch fragmentation prevents warm ambient cache from helping same-session paraphrases",
            "The warm ambient cache writes cards but same-topic paraphrases use different topic_epoch keys.",
            labels=("bug", "enhancement"),
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Archived",
            "Track": "External models",
            "Kind": "Smoke",
            "Stage": "Stage 6",
            "Evidence": "None",
            "Priority": "Later",
            "Source": "manual owner triage",
        },
        triage,
        repair_managed_fields=True,
    )

    assert updates == {}


def test_repair_managed_fields_treats_ownership_source_text_as_script_owned() -> None:
    triage = project_triage.infer_triage(
        issue(
            266,
            "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
            "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
            labels=("enhancement",),
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Inbox",
            "Kind": "Docs",
            "Priority": "P2",
            "Source": "GitHub issue #266; docs/runtime-script-map.md is updated if the ownership map changes.",
        },
        triage,
        repair_managed_fields=True,
    )

    assert updates["Kind"] == "Implementation"
    assert updates["Priority"] == "P1"


def test_repair_managed_fields_repairs_ready_script_owned_items() -> None:
    triage = project_triage.infer_triage(
        issue(
            267,
            "Centralize recall scoring constants into typed policy objects",
            "Magic numbers in recall scoring should move into a policy object.",
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Ready",
            "Track": "Benchmarks & Research",
            "Kind": "Smoke",
            "Stage": "Research",
            "Evidence": "None",
            "Priority": "P2",
            "Source": "GitHub issue #267",
        },
        triage,
        repair_managed_fields=True,
    )

    assert updates == {
        "Track": "Docs cleanup",
        "Kind": "Implementation",
        "Stage": "Cross-stage",
        "Priority": "P1",
    }


def test_repair_managed_fields_does_not_move_active_human_work_status() -> None:
    triage = project_triage.infer_triage(
        issue(
            262,
            "Topic-epoch fragmentation prevents warm ambient cache from helping same-session paraphrases",
            "The warm ambient cache writes cards but same-topic paraphrases use different topic_epoch keys.",
            labels=("bug", "enhancement"),
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "In Progress",
            "Track": "External models",
            "Kind": "Smoke",
            "Stage": "Stage 6",
            "Evidence": "None",
            "Priority": "Later",
            "Source": "GitHub issue #262",
        },
        triage,
        repair_managed_fields=True,
    )

    assert updates == {}


def test_repair_dry_run_report_marks_managed_items_and_updates() -> None:
    item = {
        "id": "item-id",
        "content": {
            "__typename": "Issue",
            "number": 262,
            "title": "Topic-epoch fragmentation prevents warm ambient cache from helping same-session paraphrases",
            "body": "The warm ambient cache writes cards but same-topic paraphrases use different topic_epoch keys.",
            "state": "OPEN",
            "labels": {"nodes": [{"name": "bug"}, {"name": "enhancement"}]},
        },
        "fieldValues": {
            "nodes": [
                {"name": "Archived", "field": {"name": "Status"}},
                {"name": "External models", "field": {"name": "Track"}},
                {"name": "Smoke", "field": {"name": "Kind"}},
                {"name": "Stage 6", "field": {"name": "Stage"}},
                {"name": "None", "field": {"name": "Evidence"}},
                {"name": "Later", "field": {"name": "Priority"}},
                {"text": "GitHub issue #262", "field": {"name": "Source"}},
            ]
        },
    }

    report = project_triage.triage_item(
        None,
        "project-id",
        {},
        item,
        dry_run=True,
        repair_managed_fields=True,
    )

    assert report["managed_by_triage"] is True
    assert report["repair_managed_fields"] is True
    assert report["updates"]["Track"] == "Life-wide memory"
    assert report["updates"]["Kind"] == "Implementation"
    assert report["updates"]["Status"] == "Ready"


def test_repair_mode_without_all_missing_does_not_fill_historical_missing_fields() -> None:
    triage = project_triage.infer_triage(
        project_triage.IssueContext(
            256,
            "Redact prompt-derived query_terms in prompt-hook --json dry-run output",
            "Debug JSON output can expose synthetic secret-shaped query_terms.",
            state="CLOSED",
            labels=("bug",),
        )
    )

    updates = project_triage.planned_updates(
        {
            "Status": "Done",
            "Priority": "P2",
            "Evidence": "None",
            "Source": "GitHub issue #256",
        },
        triage,
        fill_missing=False,
        repair_managed_fields=True,
    )

    assert updates == {}
