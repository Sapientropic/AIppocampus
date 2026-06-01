from __future__ import annotations

import importlib.util
import json
import subprocess
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


def discussion(
    number: int,
    title: str,
    body: str = "",
    *,
    category: str = "Ideas",
    comments: tuple[str, ...] = (),
    node_id: str | None = "discussion-node",
):
    return planning_audit.DiscussionSnapshot(
        number=number,
        title=title,
        body=body,
        category=category,
        comments=comments,
        node_id=node_id,
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


def test_docs_claim_boundary_is_not_reported_as_unresolved_work(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "evidence" / "report.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "## Cannot Claim\n\n- No live semantic-model quality claim.\n",
        encoding="utf-8",
    )

    report = planning_audit.audit_issues([], milestone_numbers={}, repo_root=tmp_path)

    assert "docs_unowned_design_hit" not in kinds(report["needs_human_review"])
    assert report["summary"]["docs_unowned_design_hits"] == 0


def test_archived_state_doc_is_not_reported_as_current_unresolved_work(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "planning" / "old-state.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        'state: archived\n'
        'stop_condition: "explicitly deferred with blocker/risk"\n',
        encoding="utf-8",
    )

    report = planning_audit.audit_issues([], milestone_numbers={}, repo_root=tmp_path)

    assert "docs_unowned_design_hit" not in kinds(report["needs_human_review"])
    assert report["summary"]["docs_unowned_design_hits"] == 0


def test_discussion_without_issue_refs_or_docs_is_reported() -> None:
    report = planning_audit.audit_issues(
        [],
        milestone_numbers={},
        discussions=[
            discussion(
                74,
                "Origin thought",
                "This captures product direction but has no docs or issue pointer.",
            )
        ],
    )

    assert "discussion_orphan" in kinds(report["needs_human_review"])
    assert report["summary"]["orphan_discussions"] == 1


def test_discussion_with_issue_ref_is_not_orphan() -> None:
    report = planning_audit.audit_issues(
        [issue(381, "Prototype a local search-decision memory adapter")],
        milestone_numbers={},
        discussions=[
            discussion(
                75,
                "Search decision memory",
                "Implementation moved to #381.",
            )
        ],
    )

    assert "discussion_orphan" not in kinds(report["needs_human_review"])
    assert report["summary"]["orphan_discussions"] == 0


def test_discussion_stale_doc_link_is_reported(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()

    report = planning_audit.audit_issues(
        [],
        milestone_numbers={},
        repo_root=tmp_path,
        discussions=[
            discussion(
                76,
                "Public link cleanup",
                "See docs/guides/missing-public-api.md before publishing.",
                category="Announcements",
            )
        ],
    )

    item = next(item for item in report["needs_human_review"] if item["kind"] == "discussion_stale_doc_link")
    assert item["discussion"] == 76
    assert item["doc"] == "docs/guides/missing-public-api.md"
    assert report["summary"]["stale_discussion_links"] == 1


def test_discussion_missing_map_generates_single_compact_comment() -> None:
    report = planning_audit.audit_issues(
        [
            issue(381, "Prototype a local search-decision memory adapter"),
            issue(382, "Improve agent-facing discoverability without hollow marketing"),
        ],
        milestone_numbers={},
        discussions=[
            discussion(
                380,
                "Two orphan themes",
                "Follow-up work now lives in #381 and #382.",
                comments=("Earlier context only.",),
                node_id="D_kwDOexample",
            )
        ],
        generate_discussion_maps=True,
    )

    assert "discussion_missing_implementation_map" in kinds(report["needs_human_review"])
    repair = next(
        item
        for item in report["safe_repairs"]
        if item["kind"] == "add_discussion_implementation_map_comment"
    )
    assert repair["discussion"] == 380
    assert repair["discussion_id"] == "D_kwDOexample"
    assert "Implementation map:" in repair["body"]
    assert "#381 Prototype a local search-decision memory adapter" in repair["body"]
    assert "#382 Improve agent-facing discoverability without hollow marketing" in repair["body"]
    assert "Follow-up work now lives" not in repair["body"]


def test_discussion_existing_map_avoids_duplicate_comment() -> None:
    report = planning_audit.audit_issues(
        [
            issue(381, "Prototype a local search-decision memory adapter"),
            issue(382, "Improve agent-facing discoverability without hollow marketing"),
        ],
        milestone_numbers={},
        discussions=[
            discussion(
                380,
                "Two orphan themes",
                "Follow-up work now lives in #381 and #382.",
                comments=("Implementation map:\n- #381\n- #382",),
            )
        ],
        generate_discussion_maps=True,
    )

    assert "discussion_missing_implementation_map" not in kinds(report["needs_human_review"])
    assert report["safe_repairs"] == []


def test_planning_audit_cli_reports_discussion_fixture(tmp_path: Path) -> None:
    issues_file = tmp_path / "issues.json"
    discussions_file = tmp_path / "discussions.json"
    issues_file.write_text(json.dumps({"issues": [], "milestone_numbers": {}}), encoding="utf-8")
    discussions_file.write_text(
        json.dumps(
            {
                "discussions": [
                    {
                        "number": 74,
                        "title": "Origin thought",
                        "body": "Product direction without docs or issue owner.",
                        "category": {"name": "Ideas"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--issues-file",
            str(issues_file),
            "--discussions-file",
            str(discussions_file),
            "--repo-root",
            str(tmp_path),
            "--json",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["summary"]["orphan_discussions"] == 1
    assert data["needs_human_review"][0]["kind"] == "discussion_orphan"
