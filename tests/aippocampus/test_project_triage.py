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
