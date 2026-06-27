from __future__ import annotations

import tempfile
import unittest

from tests.aippocampus.cli_fixtures import parse_cli_json, run_aippocampus_cli


class AippocampusCliPulseTests(unittest.TestCase):
    run_cli = staticmethod(run_aippocampus_cli)

    def test_pulse_projects_health_states_to_green_yellow_red(self) -> None:
        from aippocampus_runtime.cli.pulse import pulse_payload, render_pulse_text

        green = pulse_payload(
            {
                "ok": True,
                "product_readiness": {
                    "status": "ready",
                    "ordinary_first_recall_usable": True,
                    "blocking_action_count": 0,
                    "advisory_action_count": 0,
                    "next_best_action": "continue",
                },
                "recommended_actions": [],
            }
        )
        self.assertEqual(
            green,
            {
                "kind": "aippocampus_pulse",
                "state": "green",
                "reason": "ready",
                "next_action": "continue",
            },
        )
        self.assertEqual(render_pulse_text(green), "AIppocampus pulse: green - ready; next: continue")

        yellow = pulse_payload(
            {
                "ok": True,
                "product_readiness": {
                    "status": "ready_with_optional_maintenance",
                    "ordinary_first_recall_usable": True,
                    "blocking_action_count": 0,
                    "advisory_action_count": 1,
                    "next_best_action": "run_checkpoint_when_idle",
                },
                "recommended_actions": [
                    {
                        "id": "checkpoint",
                        "severity": "suggestion",
                        "reason": "30 messages since the last captured checkpoint",
                        "command": "aippocampus maintenance plan --summary-json",
                    }
                ],
            }
        )
        self.assertEqual(yellow["state"], "yellow")
        self.assertEqual(yellow["reason"], "30 messages since the last captured checkpoint")
        self.assertEqual(yellow["next_action"], "aippocampus maintenance plan --summary-json")

        red = pulse_payload(
            {
                "ok": False,
                "product_readiness": {
                    "status": "needs_maintenance",
                    "ordinary_first_recall_usable": False,
                    "maintenance_required_before_recall": True,
                    "blocking_action_count": 1,
                    "advisory_action_count": 0,
                    "next_best_action": "apply_required_maintenance",
                },
                "recommended_actions": [
                    {
                        "id": "build_clean_source",
                        "severity": "critical",
                        "reason": "clean source is missing",
                        "facade_command": "aippocampus maintenance --cwd .",
                    }
                ],
            }
        )
        self.assertEqual(red["state"], "red")
        self.assertEqual(red["reason"], "clean source is missing")
        self.assertEqual(red["next_action"], "aippocampus maintenance --cwd .")

    def test_pulse_cli_is_one_line_or_compact_json_not_health_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            human = self.run_cli("pulse", "--cwd", tmp)
            machine = self.run_cli("pulse", "--cwd", tmp, "--json")

        self.assertIn(human.returncode, {0, 2}, human.stderr)
        self.assertEqual(len([line for line in human.stdout.splitlines() if line.strip()]), 1)
        self.assertIn("AIppocampus pulse:", human.stdout)

        payload = parse_cli_json(self, machine, expected_returncode={0, 2}, label="pulse json")
        self.assertEqual(set(payload), {"kind", "state", "reason", "next_action"})
        self.assertEqual(payload["kind"], "aippocampus_pulse")
        self.assertIn(payload["state"], {"green", "yellow", "red"})
        self.assertNotIn("recommended_actions", payload)
        self.assertNotIn("product_readiness", payload)


if __name__ == "__main__":
    unittest.main()
