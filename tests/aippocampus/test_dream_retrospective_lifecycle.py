from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.dream import retrospective_lifecycle as lifecycle  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def probe(finding_id: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "finding_kind": "dream_synthesized",
        "dream_function": "prospective",
        "fingerprint": finding_id,
        "created_at": "2026-05-01T00:00:00Z",
        "review_after": "2026-05-10T00:00:00Z",
        "expires_at": "2026-06-01T00:00:00Z",
        "review_state": "needs_review",
        "adjudication_result": {"status": "parked"},
        "title": f"Probe {finding_id}",
        "summary": "A parked future-facing dream probe.",
        "source_refs": [source_ref("session:seed-a", "msg-seed-a", 10), source_ref("session:seed-b", "msg-seed-b", 20)],
    }
    base.update(overrides)
    return base


def validation_row(target: str, status: str, *, created_at: str = "2026-05-20T00:00:00Z", kind: str = "prospective_validation_event") -> dict[str, object]:
    return {
        "kind": kind,
        "target_finding_id": target,
        "validation_status": status,
        "created_at": created_at,
        "source_refs": [source_ref(f"session:{target}:{status}", f"msg-{target}-{status}", 30)],
    }


class DreamRetrospectiveLifecycleTests(unittest.TestCase):
    def test_due_parked_probes_receive_retrospective_status_buckets(self) -> None:
        probes = [
            probe("pf_supported"),
            probe("pf_refuted"),
            probe("pf_stale", expires_at="2026-05-11T00:00:00Z"),
            probe("pf_unknown"),
            probe("pf_pending", review_after="2026-06-10T00:00:00Z"),
            probe("ai_supported", dream_function="active_imagination"),
        ]
        later_rows = [
            validation_row("pf_supported", "supported"),
            validation_row("pf_refuted", "refuted"),
            validation_row("ai_supported", "supported", kind="active_imagination_validation_event"),
        ]

        payload = lifecycle.run_retrospective_lifecycle(
            probes,
            later_rows,
            now="2026-05-30T00:00:00Z",
        )
        by_id = {item["finding_id"]: item for item in payload["items"]}

        self.assertEqual(by_id["pf_supported"]["retrospective_policy"]["status"], "supported")
        self.assertEqual(by_id["pf_refuted"]["retrospective_policy"]["status"], "refuted")
        self.assertEqual(by_id["pf_stale"]["retrospective_policy"]["status"], "stale")
        self.assertEqual(by_id["pf_unknown"]["retrospective_policy"]["status"], "unknown")
        self.assertEqual(by_id["pf_pending"]["lifecycle_status"], "parked_pending_review")
        self.assertEqual(by_id["ai_supported"]["retrospective_policy"]["status"], "supported")
        self.assertEqual(
            payload["counts"],
            {
                "parked_pending_review": 1,
                "refuted": 1,
                "stale": 1,
                "supported": 2,
                "unknown": 1,
            },
        )

    def test_lifecycle_ignores_term_overlap_old_source_and_future_leakage(self) -> None:
        later_rows = [
            validation_row("pf_guarded", "supported", created_at="2026-04-30T00:00:00Z"),
            validation_row("pf_guarded", "supported", created_at="2026-06-30T00:00:00Z"),
            {
                "kind": "aippocampus_working_memory",
                "title": "Probe pf_guarded source review vocabulary overlaps",
                "created_at": "2026-05-20T00:00:00Z",
                "source_refs": [source_ref("session:overlap", "msg-overlap", 40)],
            },
        ]

        payload = lifecycle.run_retrospective_lifecycle(
            [probe("pf_guarded")],
            later_rows,
            now="2026-05-30T00:00:00Z",
        )

        item = payload["items"][0]
        self.assertEqual(item["retrospective_policy"]["status"], "unknown")
        self.assertEqual(item["window"]["ignored_before_probe"], 1)
        self.assertEqual(item["window"]["ignored_after_now"], 1)
        self.assertEqual(item["window"]["term_overlap_without_target"], 1)

    def test_coding_rejected_route_fixture_supports_probe_only_with_explicit_target(self) -> None:
        coding_probe = probe(
            "coding_rejected_route",
            probe_family="coding_rejected_route",
            rejected_route="manual_fixture_adapter",
        )
        later_rows = [
            {
                "kind": "coding_decision_event",
                "event_type": "rejected_route_reopened",
                "target_finding_id": "coding_rejected_route",
                "validation_status": "supported",
                "created_at": "2026-05-20T00:00:00Z",
                "source_refs": [source_ref("session:coding", "msg-coding", 50)],
            }
        ]

        payload = lifecycle.run_retrospective_lifecycle(
            [coding_probe],
            later_rows,
            now="2026-05-30T00:00:00Z",
        )
        summary = lifecycle.public_lifecycle_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(payload["items"][0]["retrospective_policy"]["status"], "supported")
        self.assertEqual(payload["items"][0]["evidence_kind_counts"], {"coding_decision_event": 1})
        self.assertEqual(summary["status_counts"]["supported"], 1)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)


if __name__ == "__main__":
    unittest.main()
