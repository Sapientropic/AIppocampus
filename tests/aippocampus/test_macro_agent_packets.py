from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import state  # noqa: E402
from aippocampus_runtime.recall import agent_continuity  # noqa: E402


def _write_macro_state(
    path: Path,
    *,
    source_refs: bool = True,
    changing: tuple[int, ...] = (1,),
    momentum_basis: dict[str, float] | None = None,
) -> None:
    entry = state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="乾",
        changing_lines=changing,
        source_refs=({"source_id": "macro-source-1"},) if source_refs else (),
        updated_at="2026-06-11T10:00:00Z",
        active_layer="人",
        momentum={"basis": momentum_basis or {"support_delta": 0.20}},
    )
    state.append_macro_orientation_state(path, entry)


class MacroAgentPacketTests(unittest.TestCase):
    def test_agent_macro_orientation_returns_compact_navigation_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "macro-orientation.jsonl"
            _write_macro_state(path)

            payload = agent_continuity.macro_orientation(
                project="AIppocampus",
                macro_state_path=path,
            )

        packet = payload["memory_packets"][0]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["mode"], "macro")
        self.assertEqual(packet["packet_kind"], "macro_orientation_packet")
        self.assertEqual(packet["authority_level"], "navigation_only")
        self.assertEqual(packet["action_grammar"], "direction_only")
        self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(packet["deepen_route_id"], "deepen:macro:project:AIppocampus:latest")
        self.assertLessEqual(len(packet["foreground_text"].encode("utf-8")), 360)
        self.assertIn("momentum rising", packet["foreground_text"])
        self.assertIn("macro_orientation", packet)
        self.assertEqual(packet["macro_orientation"]["momentum"]["direction"], "rising")
        self.assertEqual(packet["macro_orientation"]["momentum"]["phase"], "lin")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("basis", encoded)
        self.assertNotIn("line_topology", encoded)
        self.assertNotIn("macro-source-1", encoded)
        self.assertEqual(payload["red_lines"]["macro_claim_ready_without_reopen"], 0)

    def test_macro_deepen_and_explain_keep_source_trail_behind_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "macro-orientation.jsonl"
            _write_macro_state(path)

            deepened = agent_continuity.deepen(
                "macro:project:AIppocampus:latest",
                macro_state_path=path,
            )
            explained = agent_continuity.explain(
                "macro:project:AIppocampus:latest",
                macro_state_path=path,
            )

        self.assertEqual(deepened["surface"], "macro")
        self.assertEqual(deepened["result"]["source_refs"], [{"source_id": "macro-source-1"}])
        self.assertIn("derivation_trace", deepened["result"])
        self.assertEqual(deepened["result"]["momentum"]["basis"]["support_delta"], 0.2)
        self.assertEqual(
            deepened["result"]["line_topology"]["authority_level"],
            "navigation_only",
        )
        self.assertFalse(deepened["result"]["line_topology"]["fact_claim_allowed"])
        self.assertEqual(deepened["result"]["authority_level"], "navigation_only")
        self.assertEqual(explained["surface"], "macro")
        self.assertEqual(explained["explanation"]["next_safe_action"], "deepen_or_reopen_source")
        self.assertIn("macro_orientation_packet_not_fact", explained["explanation"]["reason_codes"])

    def test_usefulness_gate_suppresses_missing_source_or_no_movement_packets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_source = Path(tmp) / "missing-source.jsonl"
            standing = Path(tmp) / "standing.jsonl"
            _write_macro_state(missing_source, source_refs=False)
            _write_macro_state(standing, changing=(), momentum_basis={"staleness_delta": 1.30})

            missing_payload = agent_continuity.macro_orientation(
                project="AIppocampus",
                macro_state_path=missing_source,
            )
            standing_payload = agent_continuity.macro_orientation(
                project="AIppocampus",
                macro_state_path=standing,
            )

        self.assertEqual(missing_payload["memory_packets"], [])
        self.assertEqual(standing_payload["memory_packets"], [])
        self.assertEqual(missing_payload["metrics"]["macro_packet_shown_count"], 0)
        self.assertIn("source_required_before_macro_packet", missing_payload["cannot_claim"])
        self.assertIn("no_route_or_movement_delta", standing_payload["diagnostics"])

    def test_macro_fixture_report_covers_route_usefulness_without_claim_upgrade(self) -> None:
        report = agent_continuity.build_macro_orientation_packet_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["schema_version"], "macro-orientation-agent-packet-v0")
        self.assertEqual(report["metrics"]["claim_ready_macro_packets"], 0)
        self.assertGreaterEqual(report["metrics"]["manual_search_avoided_count"], 1)
        self.assertGreaterEqual(report["metrics"]["wrong_layer_recall_reduced_count"], 1)
        self.assertGreaterEqual(report["metrics"]["premature_broad_closeout_blocked_count"], 1)
        self.assertGreaterEqual(report["metrics"]["next_action_usefulness_count"], 1)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("PRIVATE", encoded)


if __name__ == "__main__":
    unittest.main()
