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
