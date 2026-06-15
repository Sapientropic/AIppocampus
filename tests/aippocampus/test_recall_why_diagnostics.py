from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.mcp import server as mcp  # noqa: E402
from aippocampus_runtime.recall import why_diagnostics as why  # noqa: E402
from aippocampus_runtime.recall import why_reason_codes as reason_codes  # noqa: E402
from aippocampus_runtime.recall import why_surfaces as surfaces  # noqa: E402


class RecallWhyDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self._write_clean_source(
            [
                {
                    "message_id": "msg-final",
                    "turn_id": "turn-1",
                    "source_id": "src-test",
                    "source_line": 4,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "text": "Clean source continuity routes require reopen before claims.",
                }
            ]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_source(self, messages: list[dict]) -> None:
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for row in messages:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        turn_rows = [
            {
                "turn_id": row.get("turn_id"),
                "turn_index": row.get("turn_index"),
                "message_ids": [row.get("message_id")],
                "assistant_phase": row.get("phase"),
            }
            for row in messages
        ]
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for row in turn_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_successful_route_is_hash_only_and_requires_source_reopen(self) -> None:
        cue = "SECRET_TOKEN=abc123 clean source continuity"

        payload = why.recall_diagnostic_report(
            cue=cue,
            mode="why-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_recall_diagnostic")
        self.assertEqual(payload["decision"], "surfaced")
        self.assertIn("route_returned", payload["reasons"])
        self.assertIn("source_reopen_required", payload["reasons"])
        self.assertEqual(payload["next_safe_action"], "reopen_source")
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("clean source continuity", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("Clean source continuity routes", encoded)
        self.assertTrue(payload["privacy_boundary"]["diagnostic_is_not_truth_source"])
        self.assertIn("diagnostic_reason_is_not_memory_evidence", payload["cannot_claim"])

    def test_common_reason_code_mappings_cover_issue_acceptance_cases(self) -> None:
        payload = why.recall_diagnostic_report(
            cue="private recall cue",
            mode="why-not-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            recall_context_payload={"status": "no_routes", "routes": [], "query_terms": ["private"]},
            active_lock_payload={
                "state": "expired",
                "lock_id": "arl_test",
                "candidate_ref_count": 0,
                "reopenable_ref_count": 0,
                "source_reopen_required": True,
                "diagnostics": {"invalidated_by": ["ttl_expired"]},
            },
            ambient_cache_payload={
                "status": "hit",
                "cards": [
                    {
                        "support_level": "candidate",
                        "source_thickness": "thin",
                        "source_reopen_required": True,
                        "source_refs": [],
                    }
                ],
                "suppression_diagnostics": {
                    "reason_buckets": [
                        "secret_or_property_risk_blocked",
                        "external_payload_blocked",
                        "local_route_handle_only",
                        "current_thread_echo",
                        "source_validation_failed",
                    ]
                },
            },
            semantic_gate_payload={
                "available": False,
                "decision": "skip",
                "availability_reason": "semantic_worker_timeout",
                "diagnostic": "semantic_provider_read_timeout",
                "error_buckets": {"read_timeout": 1},
                "worker_count": 1,
            },
        )

        reasons = set(payload["reasons"])
        self.assertGreaterEqual(
            reasons,
            {
                "no_source_refs",
                "stale_handle",
                "secret_or_property_risk_blocked",
                "external_payload_blocked",
                "local_route_handle_only",
                "anti_nag_source_already_visible",
                "semantic_provider_timeout",
                "source_thickness_thin",
                "source_reopen_required",
                "source_ref_not_found",
            },
        )
        self.assertEqual(payload["decision"], "suppressed")
        self.assertEqual(payload["reason_code_catalog_version"], 1)

    def test_ambient_cache_surface_distinguishes_bounded_evidence_ready(self) -> None:
        report = surfaces.ambient_cache_surface_report(
            {
                "status": "hit",
                "cards": [
                    {
                        "support_level": "evidence",
                        "authority_state": "bounded_evidence_ready",
                        "source_reopen_required": False,
                        "reopen_required_before_claim": False,
                        "reopen_recommended_for_exact_quote": True,
                        "source_refs": [{"thread_key": "session:old", "line": 4}],
                    }
                ],
            }
        )

        self.assertIn("bounded_evidence_ready", report["reason_codes"])
        self.assertIn("reopen_recommended_for_exact_quote", report["reason_codes"])
        self.assertNotIn("source_reopen_required", report["reason_codes"])
        self.assertTrue(report["details"]["bounded_evidence_ready"])
        self.assertFalse(report["details"]["source_reopen_required"])
        self.assertEqual(
            reason_codes.next_safe_action(report["reason_codes"]),
            "use_bounded_evidence_when_relevant",
        )

    def test_cli_facade_exposes_why_not_recall_json_without_raw_cue(self) -> None:
        result = facade.run_command(
            [
                "why-not-recall",
                "SECRET_TOKEN=abc123 clean source continuity",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
            ],
            capture_output=True,
        )

        self.assertTrue(result.ok, result.stderr)
        payload = json.loads(result.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["mode"], "why-not-recall")
        self.assertEqual(payload["kind"], "aippocampus_recall_diagnostic")
        self.assertIn("recall_context", payload["searched_surfaces"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_why_not_recall_distinguishes_low_specificity_surface_from_silence(self) -> None:
        payload = why.recall_diagnostic_report(
            cue="vague context",
            mode="why-not-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            recall_context_payload={
                "status": "ok",
                "query_terms": ["vague"],
                "routes": [
                    {
                        "route_id": f"route-{index}",
                        "source_refs": [{"source_id": f"src-{index}"}],
                        "source_reopen_required": True,
                    }
                    for index in range(5)
                ],
            },
        )

        self.assertEqual(payload["decision"], "surfaced")
        self.assertEqual(payload["diagnostic_class"], "surfaced_but_low_specificity")
        self.assertFalse(payload["why_not_applicable"])
        self.assertEqual(payload["route_specificity"], "low")
        self.assertIn("tighten_cue", payload["suggested_next"])

    def test_mcp_recall_diagnostic_returns_public_safe_payload(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 678,
                "method": "tools/call",
                "params": {
                    "name": "recall_diagnostic",
                    "arguments": {
                        "cue": "SECRET_TOKEN=abc123 clean source continuity",
                        "mode": "why-recall",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                    },
                },
            }
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["kind"], "aippocampus_recall_diagnostic")
        self.assertIn("source_reopen_required", payload["reasons"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn(str(self.cwd), encoded)


if __name__ == "__main__":
    unittest.main()
