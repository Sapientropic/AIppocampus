from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.aippocampus.import_path_helpers import import_tool_root_module

readiness = import_tool_root_module("recall_integration_readiness")
REPO_ROOT = Path(__file__).resolve().parents[2]


class RecallIntegrationReadinessTests(unittest.TestCase):
    def test_default_report_names_foreground_wired_and_blocked_surfaces(self) -> None:
        report = readiness.build_recall_integration_readiness()
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertTrue(report["ok"])
        self.assertEqual(report["kind"], "aippocampus_recall_integration_readiness")
        self.assertIn("git_head", report)
        self.assertIn("git_dirty", report)
        self.assertIn(report["evidence_scope"], {"clean_worktree", "dirty_worktree"})
        self.assertIsInstance(report["dirty_path_count"], int)
        self.assertEqual(
            by_id["repo_familiarity_fallback"]["status"],
            "callable",
        )
        self.assertTrue(by_id["repo_familiarity_fallback"]["foreground_callable"])
        self.assertTrue(by_id["mcp_agent_recall_deepen_parity"]["mcp_wired"])
        self.assertEqual(
            by_id["ambient_tiny_agent_recall_affordance"]["status"],
            "callable",
        )
        self.assertTrue(by_id["ambient_tiny_agent_recall_affordance"]["foreground_callable"])
        self.assertTrue(by_id["ambient_tiny_agent_recall_affordance"]["mcp_wired"])
        self.assertIn(
            "not default source evidence",
            by_id["ambient_tiny_agent_recall_affordance"]["claim"],
        )
        self.assertEqual(by_id["ambient_tiny_agent_recall_affordance"]["owner_issue"], "#2554")

    def test_proxy_only_foreground_claim_fails(self) -> None:
        report = readiness.build_recall_integration_readiness(
            [
                {
                    "surface_id": "bad_proxy",
                    "status": "proxy_only",
                    "owner_issue": "#0",
                    "foreground_callable": False,
                    "cli_wired": False,
                    "mcp_wired": False,
                    "claim": "foreground callable from a proxy smoke",
                }
            ]
        )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["failures"][0]["reason"],
            "proxy_only_surface_claims_foreground_callable",
        )

    def test_cli_wired_mcp_unwired_agent_surface_fails(self) -> None:
        report = readiness.build_recall_integration_readiness(
            [
                {
                    "surface_id": "cli_only_agent_feature",
                    "status": "callable",
                    "owner_issue": "#0",
                    "foreground_callable": True,
                    "cli_wired": True,
                    "mcp_wired": False,
                    "claim": "CLI foreground path is done",
                }
            ]
        )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["failures"][0]["reason"],
            "agent_facing_cli_wired_but_mcp_unwired",
        )

    def test_live_dogfood_failure_blocks_readiness(self) -> None:
        report = readiness.build_recall_integration_readiness(
            dogfood_report={
                "ok": False,
                "case_count": 3,
                "passed_count": 2,
                "failing_owners": ["registry_search_phrase_coverage"],
            }
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["failures"][0]["surface_id"], "known_artifact_recall_dogfood")
        self.assertEqual(report["failures"][0]["reason"], "live known-artifact dogfood failed")

    def test_mcp_first_apw_probe_failure_blocks_readiness(self) -> None:
        report = readiness.build_recall_integration_readiness(
            apw_probe={
                "ok": False,
                "status": "blocked",
                "cue": "黏菌 联想回忆 探索算法",
                "failures": [{"reason": "cli_apw_candidate_missing_from_mcp"}],
                "cli": {"apw_candidate_input_available": True},
                "mcp": {"apw_candidate_input_available": False},
            }
        )
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertFalse(report["ok"])
        self.assertEqual(by_id["apw_fallback"]["status"], "blocked")
        self.assertEqual(by_id["mcp_agent_recall_deepen_parity"]["status"], "blocked")
        self.assertIn(
            "cli_apw_candidate_missing_from_mcp",
            by_id["mcp_agent_recall_deepen_parity"]["mcp_first_apw_probe"]["failure_reasons"],
        )

    def test_mcp_first_apw_safe_abstain_does_not_claim_source_open(self) -> None:
        report = readiness.build_recall_integration_readiness(
            apw_probe={
                "ok": True,
                "status": "safe_abstain",
                "cue": "黏菌 联想回忆 探索算法",
                "failures": [],
                "cli": {"apw_candidate_input_available": False},
                "mcp": {
                    "apw_candidate_input_available": False,
                    "fallback_status": "abstained",
                    "foreground_action_id": "search_registry_sources_for_original_cue_anchors",
                },
            }
        )
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertTrue(report["ok"])
        self.assertEqual(by_id["apw_fallback"]["status"], "callable")
        self.assertIn("abstained safely", by_id["apw_fallback"]["reason"])
        self.assertIn(
            "MCP stayed aligned",
            by_id["mcp_agent_recall_deepen_parity"]["reason"],
        )

    def test_fixture_apw_probe_is_labeled_as_fixture_evidence(self) -> None:
        report = readiness.build_recall_integration_readiness(
            apw_probe={
                "ok": True,
                "status": "passed",
                "probe_label": "fixture_current_clean_source",
                "cue": "黏菌 联想回忆 探索算法",
                "failures": [],
                "cli": {
                    "apw_candidate_input_available": True,
                    "opened_anchor_hits": 3,
                },
                "mcp": {
                    "apw_candidate_input_available": True,
                    "opened_anchor_hits": 3,
                },
            }
        )
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        probe = by_id["mcp_agent_recall_deepen_parity"]["mcp_first_apw_probe"]
        self.assertEqual(probe["probe_label"], "fixture_current_clean_source")
        self.assertEqual(probe["probe_scope"], "fixture")
        self.assertIn("not live historical usefulness", probe["claim_boundary"])

    def test_live_source_chain_probe_marks_mcp_parity_useful(self) -> None:
        report = readiness.build_recall_integration_readiness(
            source_chain_probe={
                "ok": True,
                "status": "passed",
                "probe_label": "live_registry_source_chain",
                "cue": "最早那条机械飞升和海马体的讨论",
                "failures": [],
                "commands": {
                    "cli_recall": "aippocampus agent recall ...",
                    "cli_deepen": "aippocampus agent deepen ...",
                    "mcp_agent_recall_arguments": {"query": "最早那条机械飞升和海马体的讨论"},
                    "mcp_agent_deepen_arguments": {"request_index": 1},
                },
                "expected_source_refs": [{"message_id": "msg_expected"}],
                "anchors": ["机械飞升", "基因飞升"],
                "cli": {
                    "target_source_matched": True,
                    "opened_anchor_hits": 2,
                },
                "mcp": {
                    "target_source_matched": True,
                    "opened_anchor_hits": 2,
                },
                "claim_boundary": "live registry/source-chain probe",
            }
        )
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertTrue(report["ok"])
        parity = by_id["mcp_agent_recall_deepen_parity"]
        self.assertEqual(parity["status"], "useful")
        self.assertIn("source-chain cue passed", parity["reason"])
        self.assertEqual(
            parity["source_chain_identity_probe"]["probe_label"],
            "live_registry_source_chain",
        )

    def test_live_source_chain_probe_failure_blocks_readiness(self) -> None:
        report = readiness.build_recall_integration_readiness(
            source_chain_probe={
                "ok": False,
                "status": "blocked",
                "probe_label": "live_registry_source_chain",
                "cue": "最早那条机械飞升和海马体的讨论",
                "failures": [
                    {
                        "surface": "mcp",
                        "reason": "mcp_source_chain_deepen_opened_wrong_source",
                    }
                ],
                "mcp": {"target_source_matched": False},
            }
        )
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertFalse(report["ok"])
        self.assertEqual(by_id["mcp_agent_recall_deepen_parity"]["status"], "blocked")
        self.assertEqual(
            by_id["mcp_agent_recall_deepen_parity"]["reason"],
            "live source-chain identity probe failed",
        )
        self.assertIn(
            "mcp_source_chain_deepen_opened_wrong_source",
            by_id["mcp_agent_recall_deepen_parity"]["source_chain_identity_probe"]["failure_reasons"],
        )

    def test_foreground_mcp_transport_failure_blocks_parity_claim(self) -> None:
        report = readiness.build_recall_integration_readiness(
            foreground_mcp_failure="Transport closed"
        )
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertFalse(report["ok"])
        self.assertEqual(by_id["mcp_agent_recall_deepen_parity"]["status"], "blocked")
        self.assertEqual(
            by_id["mcp_agent_recall_deepen_parity"]["reason"],
            "foreground MCP transport failed",
        )
        self.assertEqual(report["failures"][0]["surface_id"], "mcp_agent_recall_deepen_parity")

    def test_acceptance_bearing_warning_fails_readiness(self) -> None:
        report = readiness.build_recall_integration_readiness(
            [
                {
                    "surface_id": "warned_acceptance_surface",
                    "status": "callable",
                    "owner_issue": "#0",
                    "foreground_callable": True,
                    "cli_wired": True,
                    "mcp_wired": True,
                    "claim": "follow-through was attempted",
                    "warnings": [
                        {
                            "code": "opened_source_anchor_hit_missing",
                            "acceptance_bearing": True,
                        }
                    ],
                }
            ]
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["failures"][0]["reason"], "acceptance_bearing_warning")

    def test_apw_probe_blocks_when_deepen_opens_source_without_advertised_anchors(self) -> None:
        def fake_source_cli(
            repo_root: Path,
            args: list[str],
            *,
            timeout: float = 30,
            stdin: str | None = None,
        ) -> dict:
            if args == ["mcp"]:
                request = json.loads(stdin or "{}")
                params = request.get("params", {})
                tool_name = params.get("name")
                if tool_name == "agent_recall":
                    payload = {
                        "status": "ok",
                        "associative_path_policy": {
                            "apw_candidate_input_available": True,
                        },
                        "associative_path_fallback": {"status": "route_candidate"},
                        "foreground_action": {
                            "id": "deepen_associative_path_fallback",
                            "arguments": {
                                "request_index": 6,
                                "recall_selector": "apw:fallback:test",
                            },
                        },
                    }
                elif tool_name == "agent_deepen":
                    payload = {
                        "status": "ok",
                        "result": {
                            "source_window": {
                                "messages": [
                                    {"text": "都弄完了，你验收一下看看，然后开下一阶段issues"}
                                ]
                            }
                        },
                    }
                else:
                    payload = {"status": "error"}
                return {
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
                        ]
                    }
                }
            return {
                "status": "ok",
                "result": {
                    "source_window": {
                        "messages": [
                            {"text": "公开 fixture 锚点：黏菌 联想回忆 探索算法。"}
                        ]
                    }
                },
            } if args[:2] == ["agent", "deepen"] else {
                "status": "ok",
                "associative_path_policy": {"apw_candidate_input_available": True},
                "associative_path_fallback": {"status": "route_candidate"},
                "foreground_action": {
                    "id": "deepen_associative_path_fallback",
                    "arguments": {
                        "request_index": 6,
                        "recall_selector": "apw:fallback:test-cli",
                    },
                },
            }

        with mock.patch.object(
            readiness,
            "_run_source_cli_json",
            side_effect=fake_source_cli,
        ):
            probe = readiness._apw_mcp_probe(
                REPO_ROOT,
                cue="黏菌 联想回忆 探索算法",
                anchors=["黏菌", "联想回忆", "探索算法"],
            )

        self.assertFalse(probe["ok"])
        self.assertEqual(probe["status"], "blocked")
        self.assertEqual(probe["mcp"]["opened_anchor_hits"], 0)
        self.assertEqual(
            probe["failures"][0]["reason"],
            "mcp_apw_deepen_opened_source_without_advertised_anchors",
        )

    def test_apw_probe_blocks_when_cli_candidate_is_missing_from_mcp(self) -> None:
        def fake_source_cli(
            repo_root: Path,
            args: list[str],
            *,
            timeout: float = 30,
            stdin: str | None = None,
        ) -> dict:
            if args == ["mcp"]:
                payload = {
                    "status": "ok",
                    "associative_path_policy": {
                        "apw_candidate_input_available": False,
                    },
                    "associative_path_fallback": {"status": "abstained"},
                    "foreground_action": {
                        "id": "search_registry_sources_for_original_cue_anchors",
                    },
                }
                return {
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
                        ]
                    }
                }
            return {
                "status": "ok",
                "result": {
                    "source_window": {
                        "messages": [
                            {"text": "公开 fixture 锚点：黏菌 联想回忆 探索算法。"}
                        ]
                    }
                },
            } if args[:2] == ["agent", "deepen"] else {
                "status": "ok",
                "associative_path_policy": {"apw_candidate_input_available": True},
                "associative_path_fallback": {"status": "route_candidate"},
                "foreground_action": {
                    "id": "deepen_associative_path_fallback",
                    "arguments": {
                        "request_index": 6,
                        "recall_selector": "apw:fallback:test-cli",
                    },
                },
            }

        with mock.patch.object(
            readiness,
            "_run_source_cli_json",
            side_effect=fake_source_cli,
        ):
            probe = readiness._apw_mcp_probe(
                REPO_ROOT,
                cue="黏菌 联想回忆 探索算法",
                anchors=["黏菌", "联想回忆", "探索算法"],
            )

        self.assertFalse(probe["ok"])
        self.assertEqual(probe["status"], "blocked")
        self.assertEqual(
            probe["failures"][0]["reason"],
            "cli_apw_candidate_missing_from_mcp",
        )

    def test_apw_probe_blocks_when_anchors_hit_wrong_target_source(self) -> None:
        def fake_source_cli(
            repo_root: Path,
            args: list[str],
            *,
            timeout: float = 30,
            stdin: str | None = None,
        ) -> dict:
            del repo_root, timeout
            source_payload = {
                "status": "ok",
                "result": {
                    "source_refs": [{"message_id": "msg_wrong"}],
                    "source_window": {
                        "messages": [
                            {"text": "公开 fixture 锚点：黏菌 联想回忆 探索算法。"}
                        ]
                    },
                },
            }
            recall_payload = {
                "status": "ok",
                "associative_path_policy": {"apw_candidate_input_available": True},
                "associative_path_fallback": {"status": "route_candidate"},
                "foreground_action": {
                    "id": "deepen_associative_path_fallback",
                    "arguments": {
                        "request_index": 6,
                        "recall_selector": "apw:fallback:test",
                    },
                },
            }
            if args == ["mcp"]:
                request = json.loads(stdin or "{}")
                tool_name = request.get("params", {}).get("name")
                payload = source_payload if tool_name == "agent_deepen" else recall_payload
                return {
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
                        ]
                    }
                }
            return source_payload if args[:2] == ["agent", "deepen"] else recall_payload

        with mock.patch.object(
            readiness,
            "_run_source_cli_json",
            side_effect=fake_source_cli,
        ):
            probe = readiness._apw_mcp_probe(
                REPO_ROOT,
                cue="黏菌 联想回忆 探索算法",
                anchors=["黏菌", "联想回忆", "探索算法"],
                expected_source_refs=[{"message_id": "msg_expected"}],
            )

        self.assertFalse(probe["ok"])
        self.assertFalse(probe["cli"]["target_source_matched"])
        self.assertFalse(probe["mcp"]["target_source_matched"])
        reasons = {failure["reason"] for failure in probe["failures"]}
        self.assertIn("cli_apw_deepen_opened_wrong_target_source", reasons)
        self.assertIn("mcp_apw_deepen_opened_wrong_target_source", reasons)

    def test_cli_json_report_is_machine_readable(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "aippocampus" / "recall_integration_readiness.py"),
                "--json",
                "--skip-live-checks",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["surface_count"], 6)


if __name__ == "__main__":
    unittest.main()
