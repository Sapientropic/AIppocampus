from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
if str(SMOKE) not in sys.path:
    sys.path.insert(0, str(SMOKE))

import smoke_claude_code_history  # noqa: E402
import smoke_claude_code_mcp_host  # noqa: E402
import smoke_cross_agent_continuity  # noqa: E402


class CrossAgentContinuitySmokeTests(unittest.TestCase):
    def test_synthetic_cross_agent_smoke_passes_without_private_paths(self) -> None:
        result = smoke_cross_agent_continuity.run_smoke()

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["proof"]["retrieval_surface"], "registry clean-source + MCP search_memory"
        )
        self.assertTrue(result["proof"]["registry_redacted"])
        self.assertTrue(result["proof"]["private_path_free_payload"])
        directions = {
            item["origin_provider"]: item for item in result["proof"]["directions"]
        }
        self.assertEqual(directions["codex"]["consumer_host_label"], "claude-code")
        self.assertEqual(directions["claude-code"]["consumer_host_label"], "codex")
        self.assertGreater(directions["codex"]["match_count"], 0)
        self.assertGreater(directions["claude-code"]["match_count"], 0)
        self.assertTrue(directions["codex"]["source_refs"][0].startswith("codex:session:"))
        self.assertTrue(
            directions["claude-code"]["source_refs"][0].startswith("claude-code:session:")
        )
        self.assertEqual(directions["codex"]["redacted_source"], "<local-path-redacted>")
        self.assertEqual(directions["claude-code"]["redacted_source"], "<local-path-redacted>")

    def test_private_root_check_handles_json_escaped_windows_paths(self) -> None:
        private_root = Path("E:/Temp/aippocampus-smoke").resolve()
        encoded = json.dumps({"path": str(private_root)}, ensure_ascii=False)

        self.assertTrue(
            smoke_cross_agent_continuity.payload_contains_private_root(encoded, private_root)
        )

    def test_claude_history_smoke_reports_counts_without_text_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "claude-home"
            cwd = root / "project"
            cwd.mkdir()
            transcript = home / "projects" / "synthetic" / "session.jsonl"
            transcript.parent.mkdir(parents=True)
            rows = [
                {
                    "type": "user",
                    "sessionId": "claude-local-history",
                    "timestamp": "2026-05-30T06:00:00Z",
                    "cwd": str(cwd),
                    "uuid": "u1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "secret user text that must never be printed",
                            }
                        ],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "claude-local-history",
                    "timestamp": "2026-05-30T06:00:01Z",
                    "cwd": str(cwd),
                    "uuid": "a1",
                    "parentUuid": "u1",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "sanitized assistant body"}],
                    },
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )

            result = smoke_claude_code_history.run_smoke(home=home, cwd=cwd)
            encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "claude-code")
        self.assertTrue(result["current_cwd_match"])
        self.assertEqual(result["samples"][0]["message_count"], 2)
        self.assertEqual(result["samples"][0]["turn_count"], 1)
        self.assertNotIn("secret user text", encoded)
        self.assertNotIn("sanitized assistant body", encoded)
        self.assertNotIn(str(root), encoded)

    def test_claude_host_smoke_sanitizes_key_like_query_values(self) -> None:
        text = smoke_claude_code_mcp_host.sanitize_host_output(
            "x: https://example.test/mcp?exaApiKey=secret-value&other=ok C:/Users/name/tool"
        )

        self.assertIn("exaApiKey=<redacted>", text)
        self.assertNotIn("secret-value", text)
        self.assertNotIn("C:/Users", text)

    def test_claude_host_smoke_sanitizes_posix_local_paths(self) -> None:
        text = smoke_claude_code_mcp_host.sanitize_host_output(
            "server: node /Users/name/.claude/mcp.js and /home/name/.config/tool"
        )

        self.assertNotIn("/Users/name", text)
        self.assertNotIn("/home/name", text)
        self.assertIn("<local-path-redacted>", text)

    def test_claude_project_skill_adapter_points_at_safe_surfaces(self) -> None:
        result = smoke_claude_code_mcp_host.inspect_project_skill()

        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], ".claude/skills/aippocampus/SKILL.md")
        self.assertTrue(all(result["markers"].values()))

    def test_claude_tool_call_smoke_uses_strict_temp_config_and_redacts_output(self) -> None:
        calls: list[list[str]] = []
        configs: list[dict[str, object]] = []

        def fake_run(args: list[str], **kwargs: object) -> object:
            calls.append(args)
            config_path = Path(args[args.index("--mcp-config") + 1])
            configs.append(json.loads(config_path.read_text(encoding="utf-8")))

            class Proc:
                returncode = 0
                stdout = "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "content": [
                                        {
                                            "type": "tool_use",
                                            "id": "call_1",
                                            "name": "mcp__aippocampus__memory_health",
                                            "input": {"cwd": "E:/repo"},
                                        }
                                    ]
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": "call_1",
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": '{"ok":true,"path":"C:/Users/name/private"}',
                                                }
                                            ],
                                        }
                                    ]
                                },
                            }
                        ),
                    ]
                )
                stderr = ""

            return Proc()

        server_script = Path("E:/repo/skills/aippocampus/scripts/aippocampus_mcp_server.py")
        with patch.object(smoke_claude_code_mcp_host.subprocess, "run", side_effect=fake_run):
            result = smoke_claude_code_mcp_host.run_claude_mcp_tool_call(
                claude="claude",
                server_name="aippocampus",
                cwd="E:/repo",
                max_budget_usd=0.1,
                timeout=30,
                server_script=server_script,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["tool_called"])
        self.assertNotIn("C:/Users/name", result["summary"])
        self.assertIn("--bare", calls[0])
        self.assertIn("--strict-mcp-config", calls[0])
        self.assertIn("stream-json", calls[0])
        self.assertIn("--verbose", calls[0])
        self.assertIn("mcp__aippocampus__memory_health", calls[0])
        self.assertEqual(
            configs[0]["mcpServers"]["aippocampus"]["args"],
            [str(server_script)],
        )

    def test_claude_probe_can_require_real_tool_call_after_host_is_reachable(self) -> None:
        proc_by_command = {
            ("mcp", "list"): "aippocampus: python server - ✓ Connected",
            ("mcp", "get"): "aippocampus:\n  Status: ✓ Connected",
        }

        def fake_run(args: list[str], **kwargs: object) -> object:
            command = tuple(args[1:3])
            stream = "\n".join(
                [
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {
                                "content": [
                                    {
                                        "type": "tool_use",
                                        "id": "call_1",
                                        "name": "mcp__aippocampus__memory_health",
                                    }
                                ]
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "user",
                            "message": {
                                "content": [
                                    {"type": "tool_result", "tool_use_id": "call_1", "content": []}
                                ]
                            },
                        }
                    ),
                ]
            )

            class Proc:
                returncode = 0
                stderr = ""
                stdout = proc_by_command.get(command, stream)

            return Proc()

        with (
            patch.object(smoke_claude_code_mcp_host.shutil, "which", return_value="claude"),
            patch.object(smoke_claude_code_mcp_host.subprocess, "run", side_effect=fake_run),
        ):
            result = smoke_claude_code_mcp_host.run_claude_mcp_probe(call_tool=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "tool_call_reachable")
        self.assertEqual(result["tool_call"]["status"], "called_memory_health")
        self.assertEqual(result["project_skill"]["status"], "present")


if __name__ == "__main__":
    unittest.main()
