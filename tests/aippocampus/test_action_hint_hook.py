from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import action_hint, action_hint_cache  # noqa: E402


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"clean:{name}", "segment_id": f"msg-{name}"}


class ActionHintHookTests(unittest.TestCase):
    def test_pre_tool_use_emits_tiny_hint_without_raw_tool_leak(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight",
                    "next_action": "run_preflight_before_broad_test",
                    "guidance_text": "Run ruff before pytest.",
                    "source_refs": [source_ref("learn")],
                    "reason_codes": ["learning_guidance_surface"],
                }
            ],
            now_unix=1000,
        )
        envelope = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "pytest E:/Users/private/project/tests/test_secret.py "
                    "--token sk-FAKE-SHOULD-NOT-LEAK"
                ),
                "file_path": "E:/Users/private/project/tests/test_secret.py",
                "command_family": "pytest",
            },
        }

        report = action_hint.evaluate_action_hint(envelope, cache_report, now_unix=1001)
        serialized = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["decision"], "hint")
        self.assertTrue(report["hint"]["navigation_only"])
        self.assertTrue(report["hint"]["no_claim_before_reopen"])
        self.assertTrue(report["hint"]["source_reopen_required"])
        self.assertFalse(report["hint"]["can_support_factual_claim"])
        self.assertFalse(report["diagnostics"]["command_rewritten"])
        self.assertFalse(report["diagnostics"]["permission_system_behavior"])
        self.assertNotIn("sk-FAKE-SHOULD-NOT-LEAK", serialized)
        self.assertNotIn("E:/Users/private", serialized)
        self.assertNotIn("pytest E:/Users/private", serialized)

    def test_unrelated_or_visible_source_actions_stay_silent(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            aar_v2_records=[
                {
                    "record_id": "aar-record",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [source_ref("aar")],
                    "nudge": {"recommended_action": "reopen_source_before_specific_claim"},
                }
            ],
            now_unix=1000,
        )
        unrelated = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "README.md"},
        }
        visible = {
            "hook_event_name": "PreToolUse",
            "tool_name": "final_answer",
            "action_class": "specific_memory_source_claim",
            "support_level": "candidate",
            "visible_source_refs": [source_ref("aar")],
        }

        unrelated_report = action_hint.evaluate_action_hint(unrelated, cache_report, now_unix=1001)
        visible_report = action_hint.evaluate_action_hint(visible, cache_report, now_unix=1001)

        self.assertEqual(unrelated_report["decision"], "silent")
        self.assertEqual(visible_report["decision"], "silent")

    def test_unsupported_event_fails_open(self) -> None:
        report = action_hint.evaluate_action_hint(
            {"hook_event_name": "UserPromptSubmit", "prompt": "hello"},
            [],
            now_unix=1001,
        )

        self.assertEqual(report["decision"], "silent")
        self.assertEqual(report["reason"], "unsupported_event")


if __name__ == "__main__":
    unittest.main()
