from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.recall import agent_continuity, agent_continuity_cli_support
from aippocampus_runtime.recall.agent_recall_cache import (
    LastRecallCacheError,
    read_last_recall_cache_result,
)


class AgentLastRecallRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        rows = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_line": 2,
                "role": "user",
                "text": "继续 agent-native recall opt-in path，但不要把 SECRET_TOKEN=abc123 放进前台。",
            }
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_last_recall_cache_keeps_public_safe_query_as_advisory_only(self) -> None:
        cache_path = self.cwd / "last-recall-query.json"
        wrote = agent_continuity_cli_support.write_last_recall_cache(
            [{"request_index": 1, "route_id": "route_query", "handle": "handle_query"}],
            query="agent-native recall opt-in SECRET_TOKEN=abc123",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=None,
            macro_state_path=None,
            project="AIppocampus",
            max_matches=1,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )

        cue = agent_continuity_cli_support.query_from_last_recall_cache(cache_path)
        recovery = agent_continuity_cli_support.last_recall_unavailable_payload(
            mode="deepen",
            exc=ValueError("same-machine last recall cache does not match"),
            schema_version=agent_continuity.SCHEMA_VERSION,
            kind="aippocampus_agent_continuity_path",
            cue=cue,
        )
        encoded = json.dumps(recovery, ensure_ascii=False)

        self.assertTrue(wrote)
        self.assertIn("agent-native recall opt-in", cue or "")
        self.assertNotIn("abc123", cue or "")
        self.assertNotIn("command", recovery["foreground_action"])
        self.assertEqual(
            recovery["foreground_action"]["command_template"],
            'aippocampus agent recall "{cue}" --json --detail full',
        )
        self.assertIn("agent-native recall opt-in", recovery["foreground_action"]["previous_cached_cue"])
        self.assertEqual(
            recovery["foreground_action"]["previous_cue_role"],
            "advisory_only_not_executable",
        )
        self.assertIn("{cue}", recovery["operator_detail_command"])
        self.assertNotIn("abc123", encoded)

    def test_last_recall_unavailable_current_cue_can_be_executable(self) -> None:
        recovery = agent_continuity_cli_support.last_recall_unavailable_payload(
            mode="deepen",
            exc=ValueError("same-machine last recall cache is missing"),
            schema_version=agent_continuity.SCHEMA_VERSION,
            kind="aippocampus_agent_continuity_path",
            cue="current task cue for this thread",
            cue_role="current",
        )

        self.assertEqual(recovery["foreground_action"]["id"], "recall_with_cue_full_detail")
        self.assertIn("current task cue for this thread", recovery["foreground_action"]["command"])
        self.assertNotIn("previous_cached_cue", recovery["foreground_action"])

    def test_corrupt_last_recall_cache_returns_typed_recovery_instead_of_empty_state(self) -> None:
        cache_path = self.cwd / "corrupt-last-recall.json"
        cache_path.write_text("{not-json", encoding="utf-8")

        result = read_last_recall_cache_result(cache_path)
        with self.assertRaises(LastRecallCacheError) as raised:
            agent_continuity_cli_support.handle_from_last_recall_cache(
                request_index=1,
                path=cache_path,
            )
        recovery = agent_continuity_cli_support.last_recall_unavailable_payload(
            mode="deepen",
            exc=raised.exception,
            schema_version=agent_continuity.SCHEMA_VERSION,
            kind="aippocampus_agent_continuity_path",
            cue=agent_continuity_cli_support.query_from_last_recall_cache(cache_path),
        )
        encoded = json.dumps(recovery, ensure_ascii=False)
        compact = compact_agent_deepen_payload(
            recovery,
            request_index=1,
            last_recall=True,
            surface="agent_cli_source_court_compact",
        )
        compact_encoded = json.dumps(compact, ensure_ascii=False)

        self.assertFalse(result.ok)
        self.assertEqual(result.diagnostic.status, "malformed")
        self.assertEqual(result.diagnostic.reason_code, "invalid_json")
        self.assertEqual(recovery["status"], "cannot_verify")
        self.assertEqual(recovery["cache_recovery"]["state"], "malformed")
        self.assertEqual(recovery["foreground_action"]["id"], "recall_with_cue_full_detail")
        self.assertIn("cache_read_diagnostic", recovery["result"])
        self.assertEqual(compact["surface"], "agent_cli_source_court_compact")
        self.assertEqual(compact["status"], "cannot_verify")
        self.assertEqual(compact["foreground_action"]["id"], "recall_with_cue_full_detail")
        self.assertNotIn("cache_read_diagnostic", compact_encoded)
        self.assertNotIn("malformed", compact_encoded)
        self.assertNotIn("invalid_json", compact_encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("{not-json", encoded)

if __name__ == "__main__":
    unittest.main()
