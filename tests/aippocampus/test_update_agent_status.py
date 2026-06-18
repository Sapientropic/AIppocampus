from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.update import cli as update_cli
from tests.aippocampus.test_update_sync import REPO_ROOT, provider_env


class UpdateAgentStatusTests(unittest.TestCase):
    def test_agent_json_returns_partial_card_before_slow_probes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env({"DEEPSEEK_API_KEY": "test"}):
            root = Path(tmp)
            probe = root / "host-probe.json"
            probe.write_text(
                json.dumps(
                    {
                        "validation_ok": True,
                        "mcp_status": {"tool_names": ["agent_recall", "agent_deepen"]},
                        "mcp_tool_is_error": False,
                        "mcp_tool_payload": {"status": "ok"},
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            slow_names = (
                "compare_skill",
                "compare_plugin",
                "enrich_plugin_cache_status",
                "status_hooks",
                "status_llm",
            )
            slow_patches = [
                patch.object(
                    update_cli,
                    name,
                    side_effect=AssertionError(f"{name} should be deferred"),
                )
                for name in slow_names
            ]
            with ExitStack() as stack:
                for slow_patch in slow_patches:
                    stack.enter_context(slow_patch)
                child_probe = stack.enter_context(
                    patch(
                        "aippocampus_runtime.ops.provider_doctor._child_process_env_visibility",
                        side_effect=AssertionError("child process probe should be deferred"),
                    )
                )
                with redirect_stdout(stdout):
                    code = update_cli.main(
                        [
                            "status",
                            "--repo-root",
                            str(REPO_ROOT),
                            "--codex-home",
                            str(root / "codex-home"),
                            "--host-probe-report",
                            str(probe),
                            "--agent-json",
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0, payload)
        child_probe.assert_not_called()
        self.assertTrue(payload["summary"]["partial_readiness"])
        self.assertIn("readiness_card", payload)
        self.assertEqual(payload["readiness_card"]["subject"], "update_status")
        self.assertTrue(payload["readiness_card"]["usable_now"])
        self.assertFalse(payload["readiness_card"]["blocks_first_recall"])
        self.assertEqual(
            payload["summary"]["magic_ready_semantics"],
            "legacy_alias_for_product_magic_ready",
        )
        deferred = set(payload["summary"]["deferred_components"])
        self.assertIn("skill_tree_fingerprint", deferred)
        self.assertIn("plugin_cache_fingerprint", deferred)
        self.assertIn("hooks_status", deferred)
        self.assertIn("llm_child_process", deferred)
        self.assertEqual(payload["partial_readiness"]["status"], "partial")
        self.assertEqual(
            payload["partial_readiness"]["operator_detail_command"],
            "aippocampus update status --operator-json",
        )
        cards = {card["id"]: card for card in payload["foreground_status_cards"]}
        self.assertIn("partial_readiness", cards)
        self.assertIn("current_thread_tool_discovery", cards)
        self.assertNotIn("action_hint_setup", cards)
        self.assertEqual(
            cards["partial_readiness"]["command"],
            "aippocampus update status --operator-json",
        )
        self.assertEqual(payload["next_actions"][0]["surface"], "operator_detail")
        self.assertNotIn("action_hints", {item["surface"] for item in payload["next_actions"]})
        violations = executable_command_violations(payload["foreground_status_cards"])
        self.assertEqual(violations, [])
