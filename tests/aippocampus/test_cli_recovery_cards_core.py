from __future__ import annotations

import json
import unittest

from aippocampus_runtime.contracts import executable_command_violations
from tests.aippocampus.cli_fixtures import run_aippocampus_cli
from tests.aippocampus.frontstage_assertions import assert_compact_frontstage_payload


class AippocampusCliRecoveryCardCoreTests(unittest.TestCase):
    """PR-lane core for CLI recovery cards.

    The full recovery-card catalog intentionally lives in the broad lane; this
    file keeps the default PR loop focused on representative frontdoors and the
    foreground-action contract that ordinary agents rely on during failures.
    """

    run_cli = staticmethod(run_aippocampus_cli)

    def test_agent_parent_json_is_foreground_chooser_not_argparse(self) -> None:
        proc = self.run_cli("agent", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_agent_recovery")
        self.assertEqual(payload["status"], "command_required")
        self.assertEqual(payload["choices"][0]["id"], "recall")
        self.assertEqual(payload["choices"][1]["id"], "aippo")
        self.assertIn("command_template", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(executable_command_violations(payload), [])

    def test_memory_privacy_controls_json_frontdoors_are_status_cards(self) -> None:
        for command, kind in {
            "memory": "aippocampus_memory_chooser",
            "privacy": "aippocampus_privacy_chooser",
            "controls": "aippocampus_controls_chooser",
        }.items():
            with self.subTest(command=command):
                proc = self.run_cli(command, "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["kind"], kind)
                self.assertEqual(payload["surface_class"], "foreground_chooser_card")
                self.assertIsInstance(payload["foreground_action"], dict)
                self.assertNotIn("agent_next_action", payload)
                self.assertIn("safe_next_actions", payload)
                self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])

    def test_self_note_missing_command_is_structured_no_write_recovery(self) -> None:
        proc = self.run_cli("self-note", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_recovery")
        self.assertEqual(payload["error"]["code"], "self_note_command_required")
        self.assertFalse(payload["write_boundary"]["written"])
        self.assertTrue(payload["source_boundary"]["direction_only_is_not_source_truth"])
        self.assertEqual(executable_command_violations(payload), [])

    def test_navigation_default_compact_keeps_diagnostics_behind_detail_gate(self) -> None:
        compact = self.run_cli("navigate", "--json")
        operator = self.run_cli("navigate", "--operator-json")

        self.assertEqual(compact.returncode, 0, compact.stderr)
        compact_payload = json.loads(compact.stdout)
        self.assertEqual(compact_payload["detail"], "compact")
        self.assertEqual(compact_payload["status"], "needs_cue")
        self.assertNotIn("diagnostic_command", json.dumps(compact_payload))
        assert_compact_frontstage_payload(self, compact_payload, max_top_level_diagnostics=1)

        self.assertEqual(operator.returncode, 0, operator.stderr)
        operator_payload = json.loads(operator.stdout)
        self.assertEqual(operator_payload["detail"], "operator")
        self.assertIn("diagnostic_command", operator_payload["lanes"][0])

    def test_import_conversation_missing_args_returns_recovery_card(self) -> None:
        proc = self.run_cli("import", "conversation", "--json")

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_import_conversation_recovery")
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["missing"], ["input_path", "format_or_provider"])
        self.assertFalse(payload["error"]["written"])
        self.assertNotIn("<path>", payload["error"]["next_action"])

    def test_object_sync_backend_chooser_keeps_action_contract(self) -> None:
        proc = self.run_cli("object-sync", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_object_sync_chooser")
        self.assertEqual(payload["status"], "choose_action")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertIn("safe_next_actions", payload)
        self.assertNotIn("agent_next_action", payload)


if __name__ == "__main__":
    unittest.main()
