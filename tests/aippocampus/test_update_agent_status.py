from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.update import cli as update_cli
from tests.aippocampus.test_update_sync import REPO_ROOT, provider_env

PROVIDER_KEY_ENV_NAMES = (
    "AIPPOCAMPUS_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
)


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
        self.assertNotIn("readiness_card", payload)
        self.assertNotIn("foreground_status_cards", payload)
        self.assertNotIn("action_hints", payload)
        self.assertNotIn("agent_callable", payload)
        self.assertNotIn("host_conformance", payload)
        self.assertNotIn("next_actions", payload)
        self.assertTrue(payload["setup_card"]["usable_now"])
        self.assertFalse(payload["setup_card"].get("blocks_first_recall", False))
        deferred = set(payload["summary"]["deferred_components"])
        self.assertIn("skill_tree_fingerprint", deferred)
        self.assertIn("plugin_cache_fingerprint", deferred)
        self.assertIn("hooks_status", deferred)
        self.assertIn("llm_child_process", deferred)
        self.assertEqual(payload["setup_card"]["state"], "partial_foreground_status")
        self.assertEqual(
            payload["setup_card"]["operator_detail_command"],
            "aippocampus update status --operator-json",
        )
        self.assertEqual(payload["foreground_action"]["surface"], "operator_detail")
        surfaces = {item.get("surface") for item in payload["safe_next_actions"]}
        self.assertIn("operator_detail", surfaces)
        self.assertIn("agent_callable", surfaces)
        self.assertNotIn("action_hints", surfaces)
        violations = executable_command_violations(payload["safe_next_actions"])
        self.assertEqual(violations, [])

    def test_operator_status_omits_provider_key_env_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            for name in PROVIDER_KEY_ENV_NAMES:
                os.environ.pop(name, None)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "status",
                        "--repo-root",
                        str(REPO_ROOT),
                        "--codex-home",
                        str(Path(tmp) / "codex-home"),
                        "--no-child-check",
                        "--operator-json",
                    ]
                )

        raw = stdout.getvalue()
        self.assertEqual(code, 0)
        for name in PROVIDER_KEY_ENV_NAMES:
            self.assertNotIn(name, raw)
        payload = json.loads(raw)
        llm = payload["surfaces"]["llm"]
        self.assertEqual(llm["status"], "missing_provider_env_var")
        self.assertTrue(llm["provider_env_var_omitted"])
