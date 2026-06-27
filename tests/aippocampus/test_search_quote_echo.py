from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime import core
from aippocampus_runtime.source import search
from aippocampus_runtime.source.artifact_role import artifact_role_profile


class SearchQuoteEchoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.env_patch = patch.dict(
            "os.environ",
            {"AIPPOCAMPUS_REGISTRY_DIR": str(self.cwd / "registry-default")},
        )
        self.env_patch.start()
        self.source = core.default_thread_clean_source_dir(self.cwd)
        self.source.mkdir(parents=True)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_short_quote_cue_prefers_original_source_over_validation_echo(self) -> None:
        rows = [
            {
                "message_id": "msg_validation_echo_one",
                "source_line": 120,
                "role": "assistant",
                "phase": "commentary",
                "scope_labels": ["technical_work"],
                "text": (
                    "我会复跑背景单测，然后马上复测真实 `agent background "
                    '"recall 不够自然 辛苦去捞"`，确认前台命令和 MCP 等价路径。'
                ),
            },
            {
                "message_id": "msg_validation_echo_two",
                "source_line": 121,
                "role": "assistant",
                "phase": "commentary",
                "scope_labels": ["technical_work"],
                "text": "CLI follow-through 已完整打开原始源窗口：搜索命中 `辛苦去捞` 的 opened source anchor。",
            },
            {
                "message_id": "msg_original_quote",
                "source_line": 284,
                "role": "user",
                "scope_labels": ["technical_work"],
                "text": "看起来不够自然，得是你辛苦去捞。",
            },
        ]
        with (self.source / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        result = search.search_clean_source(self.cwd, ["辛苦去捞"], limit=5)

        self.assertEqual(result["matches"][0]["message_id"], "msg_original_quote")
        echoes = {
            item["message_id"]: item
            for item in result["matches"]
            if str(item.get("message_id", "")).startswith("msg_validation_echo")
        }
        self.assertTrue(echoes["msg_validation_echo_one"]["artifact_demoted"])
        self.assertTrue(echoes["msg_validation_echo_two"]["artifact_demoted"])

    def test_opened_source_window_text_is_not_demoted_without_validation_context(self) -> None:
        profile = artifact_role_profile(
            text="The opened MCP source window contains MCP compact open-source anchor 明明还在本地.",
            query_text="MCP compact open-source anchor 明明还在本地",
            metadata={"role": "assistant", "phase": "final_answer"},
        )

        self.assertFalse(profile["demote"])
        self.assertEqual(profile["role"], "topic_candidate")


if __name__ == "__main__":
    unittest.main()
