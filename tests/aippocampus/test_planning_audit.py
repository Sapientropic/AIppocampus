from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "aippocampus" / "github" / "planning_audit.py"
SPEC = importlib.util.spec_from_file_location("planning_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
planning_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = planning_audit
SPEC.loader.exec_module(planning_audit)


def issue(
    number: int,
    title: str,
    body: str = "",
    *,
    state: str = "OPEN",
    labels: tuple[str, ...] = (),
    milestone: str | None = None,
    comments: tuple[str, ...] = (),
):
    return planning_audit.IssueSnapshot(
        number=number,
        title=title,
        body=body,
        state=state,
        labels=labels,
        milestone=milestone,
        comments=comments,
    )


def kinds(items: list[dict[str, object]]) -> set[str]:
    return {str(item["kind"]) for item in items}


def test_missing_milestone_high_confidence_issue_becomes_safe_repair() -> None:
    report = planning_audit.audit_issues(
        [
            issue(
                266,
                "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
                "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
            )
        ],
        milestone_numbers={"Architecture Debt Slice 2026-06": 5},
    )

    assert report["summary"]["open_without_milestone"] == 1
    assert report["summary"]["safe_repairs"] == 1
    assert report["safe_repairs"][0]["kind"] == "assign_milestone"
    assert report["safe_repairs"][0]["issue"] == 266
    assert report["safe_repairs"][0]["milestone"] == "Architecture Debt Slice 2026-06"
    assert report["safe_repairs"][0]["milestone_number"] == 5


def test_existing_human_milestone_is_preserved() -> None:
    report = planning_audit.audit_issues(
        [
            issue(
                266,
                "Split aippocampus_runtime/core.py before it becomes hidden architecture debt",
                "core.py mixes path tools, rollout parsing, text processing, redaction, CLI, and graph building.",
                milestone="Human chosen milestone",
            )
        ],
        milestone_numbers={"Architecture Debt Slice 2026-06": 5},
    )

    assert report["summary"]["open_without_milestone"] == 0
    assert report["safe_repairs"] == []


def test_design_issue_without_source_docs_is_human_review_only() -> None:
    report = planning_audit.audit_issues(
        [
            issue(
                217,
                "Add anti-circular controls for semantic-sidecar benchmark claims",
                "Parent: #216\n\nPrevent semantic-sidecar benchmark results from validating generated labels.",
            )
        ],
        milestone_numbers={},
    )

    assert "missing_source_docs" in kinds(report["needs_human_review"])
    assert report["summary"]["missing_source_refs"] == 1
    assert report["safe_repairs"] == []


def test_closed_child_checklist_exact_pattern_is_safe_repair() -> None:
    report = planning_audit.audit_issues(
        [
            issue(10, "Closed child", state="CLOSED", comments=("Closed by #11 with tests.",)),
            issue(20, "Umbrella", "- [ ] #10 Closed child\n- [ ] #12 Still open"),
        ],
        milestone_numbers={},
    )

    repair = next(item for item in report["safe_repairs"] if item["kind"] == "check_closed_child")
    assert repair["issue"] == 20
    assert repair["child_issue"] == 10
    assert "- [x] #10 Closed child" in str(repair["updated_body"])
    assert "- [ ] #12 Still open" in str(repair["updated_body"])


def test_closed_issue_without_evidence_is_reported_not_reopened() -> None:
    report = planning_audit.audit_issues(
        [issue(44, "Close me somehow", state="CLOSED")],
        milestone_numbers={},
    )

    assert "weak_closed_issue_evidence" in kinds(report["needs_human_review"])
    assert report["summary"]["suspicious_recent_closures"] == 1
    assert all(item["kind"] != "reopen_issue" for item in report["safe_repairs"])


def test_github_rest_comment_count_is_not_treated_as_comment_body() -> None:
    parsed = planning_audit.parse_github_issue(
        {
            "number": 44,
            "title": "Closed issue",
            "body": "",
            "state": "closed",
            "labels": [],
            "comments": 3,
        }
    )

    assert parsed is not None
    assert parsed.comments == ()


def test_docs_unresolved_hit_needs_owner_issue(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "research" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("## Open Questions\nThis needs a reviewed owner.\n", encoding="utf-8")

    report = planning_audit.audit_issues([], milestone_numbers={}, repo_root=tmp_path)

    assert "docs_unowned_design_hit" in kinds(report["needs_human_review"])
    assert report["summary"]["docs_unowned_design_hits"] == 1


def test_docs_unresolved_hit_with_owner_issue_is_not_reported(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "research" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("## Open Questions\nThis needs a reviewed owner.\n", encoding="utf-8")

    report = planning_audit.audit_issues(
        [issue(55, "Own note", "Source: docs/research/note.md")],
        milestone_numbers={},
        repo_root=tmp_path,
    )

    assert "docs_unowned_design_hit" not in kinds(report["needs_human_review"])
    assert report["summary"]["docs_unowned_design_hits"] == 0
