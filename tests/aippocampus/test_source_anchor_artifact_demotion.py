from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.recall import agent_continuity, agent_recall_pipeline


class SourceAnchorArtifactDemotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        (self.clean / "messages.jsonl").write_text("", encoding="utf-8")
        (self.clean / "turns.jsonl").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def append_clean_rows(self, rows: list[dict[str, object]]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(
                    json.dumps(
                        {
                            "turn_id": row.get("turn_id"),
                            "turn_index": row.get("turn_index"),
                            "message_ids": [row.get("message_id")],
                            "assistant_phase": row.get("phase"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def assert_anchor_echo_blocked(
        self, *, row: dict[str, object], route_id: str, route_label: str
    ) -> None:
        self.append_clean_rows([row])
        handle = {
            "kind": "source_ref",
            "route_id": route_id,
            "source_refs": [{"source_id": "src_test", "message_id": row["message_id"]}],
        }
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": route_id,
                    "kind": "source_ref",
                    "handle": handle,
                    "route_label": route_label,
                    "source_refs": handle["source_refs"],
                }
            ],
        }
        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "黏菌 联想回忆 探索算法",
                cwd=self.cwd,
                clean_source_dir=self.clean,
            )

        self.assertEqual(report["source_anchor_gate"]["status"], "blocked")
        self.assertEqual(report["source_anchor_gate"]["reason"], "opened_source_validation_artifact")
        self.assertEqual(report["source_anchor_gate"]["opened_anchor_hits"], 3)
        self.assertEqual(report["foreground_action_card"]["decision"], "recover_low_confidence_route")

    def test_validation_artifact_anchor_echo_is_not_default_deepen_action(self) -> None:
        self.assert_anchor_echo_blocked(
            row={
                "message_id": "msg_validation_anchor_echo",
                "turn_id": "turn_validation_anchor_echo",
                "source_id": "src_test",
                "source_line": 42,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 42,
                "is_final": True,
                "text": (
                    "readiness fixture control-only validation report: "
                    "aippocampus agent recall 黏菌 联想回忆 探索算法 --json"
                ),
            },
            route_id="route_validation_anchor_echo",
            route_label="validation echo route",
        )

    def test_private_operator_source_policy_echo_is_not_default_deepen_action(self) -> None:
        self.assert_anchor_echo_blocked(
            row={
                "message_id": "msg_private_operator_anchor_echo",
                "turn_id": "turn_private_operator_anchor_echo",
                "source_id": "src_test",
                "source_line": 43,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 43,
                "is_final": True,
                "material_class": "private_operator_detail",
                "source_claim_policy": "not_source_evidence_without_private_reopen",
                "text": (
                    "继续深测并补完一批接线型 issue；黏菌 联想回忆 "
                    "探索算法 只是验收材料里的回放 cue。"
                ),
            },
            route_id="route_private_operator_anchor_echo",
            route_label="private operator echo route",
        )


if __name__ == "__main__":
    unittest.main()
