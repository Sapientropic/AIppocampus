from __future__ import annotations

import unittest

from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION, redact_private_paths


class PrivacyProjectionTests(unittest.TestCase):
    def test_route_kind_counters_and_workflow_paths_are_not_mistaken_for_local_paths(self) -> None:
        payload = {
            "source_reopen_path": "mcp.recall_deepen",
            "workflow_path": "agent recall -> deepen -> answer",
            "route_kinds": {"active_path": 1, "pathlet": 2},
            "file_path": "/Users/example/private.jsonl",
        }

        redacted = redact_private_paths(payload)

        self.assertEqual(redacted["source_reopen_path"], "mcp.recall_deepen")
        self.assertEqual(redacted["workflow_path"], "agent recall -> deepen -> answer")
        self.assertEqual(redacted["route_kinds"]["active_path"], 1)
        self.assertEqual(redacted["route_kinds"]["pathlet"], 2)
        self.assertEqual(redacted["file_path"], LOCAL_PATH_REDACTION)

    def test_template_placeholders_in_path_fields_are_not_redacted(self) -> None:
        payload = {
            "arguments_template": {
                "cwd": "{project_cwd}",
                "clean_source_dir": "{clean_source_dir}",
            },
            "cwd": "/Users/example/private-project",
        }

        redacted = redact_private_paths(payload)

        self.assertEqual(redacted["arguments_template"]["cwd"], "{project_cwd}")
        self.assertEqual(redacted["arguments_template"]["clean_source_dir"], "{clean_source_dir}")
        self.assertEqual(redacted["cwd"], LOCAL_PATH_REDACTION)

    def test_public_urls_with_home_segments_are_not_corrupted(self) -> None:
        payload = {
            "issue_url": "https://example.com/home/project/issues/1",
            "message": "Open https://example.com/home/project/issues/1 before reading /home/me/private",
        }

        redacted = redact_private_paths(payload)

        self.assertEqual(redacted["issue_url"], "https://example.com/home/project/issues/1")
        self.assertIn("https://example.com/home/project/issues/1", redacted["message"])
        self.assertIn(LOCAL_PATH_REDACTION, redacted["message"])

    def test_local_path_at_start_of_text_redacts_without_crashing(self) -> None:
        payload = {
            "message": "/home/me/private is local; https://example.com/home/project stays public",
        }

        redacted = redact_private_paths(payload)

        self.assertIn(LOCAL_PATH_REDACTION, redacted["message"])
        self.assertIn("https://example.com/home/project", redacted["message"])

if __name__ == "__main__":
    unittest.main()
