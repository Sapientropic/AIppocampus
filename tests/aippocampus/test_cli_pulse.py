from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

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

    def test_pulse_uses_compact_foreground_storage_action(self) -> None:
        from aippocampus_runtime.cli.pulse import pulse_payload

        payload = pulse_payload(
            {
                "ok": True,
                "foreground_action": {
                    "id": "review_storage_gc_summary",
                    "why": "Storage pressure is present; run this no-write summary before cache pressure grows.",
                    "command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                },
                "safe_next_actions": [
                    {
                        "id": "review_storage_gc_summary",
                        "why": "Storage pressure is present; run this no-write summary before cache pressure grows.",
                        "command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                    }
                ],
            }
        )

        self.assertEqual(payload["state"], "yellow")
        self.assertEqual(
            payload["reason"],
            "Storage pressure is present; run this no-write summary before cache pressure grows.",
        )
        self.assertEqual(payload["next_action"], "aippocampus storage gc --dry-run --summary-json --cwd .")

    def test_build_pulse_payload_uses_quick_health_contract(self) -> None:
        from aippocampus_runtime.cli import pulse as pulse_module

        seen_options = []

        def fake_health_report(options):
            seen_options.append(options)
            return {
                "ok": True,
                "product_readiness": {
                    "status": "ready",
                    "ordinary_first_recall_usable": True,
                    "blocking_action_count": 0,
                    "advisory_action_count": 0,
                    "high_severity_action_count": 0,
                    "storage_pressure_cleanup_recommended": None,
                    "next_best_action": "continue",
                },
                "recommended_actions": [],
                "storage_pressure": {
                    "available": False,
                    "status": "deferred",
                    "pressure": None,
                    "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                },
            }

        with patch.object(pulse_module.health_runtime, "build_health_report", side_effect=fake_health_report):
            payload = pulse_module.build_pulse_payload(".")

        self.assertEqual(len(seen_options), 1)
        options = seen_options[0]
        self.assertFalse(options.include_operator_diagnostics)
        self.assertFalse(options.include_expensive_diagnostics)
        self.assertEqual(options.operator_timeout_ms, pulse_module.PULSE_QUICK_HEALTH_TIMEOUT_MS)
        self.assertEqual(options.slow_section_threshold_ms, pulse_module.PULSE_SLOW_SECTION_THRESHOLD_MS)
        self.assertEqual(payload["state"], "yellow")
        self.assertEqual(payload["next_action"], "aippocampus storage gc --dry-run --summary-json --cwd .")

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
