from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.public_output import emit_public_json, emit_public_text  # noqa: E402
from aippocampus_runtime.update import operator_output  # noqa: E402


class PublicOutputTests(unittest.TestCase):
    def test_emit_public_text_redacts_unsafe_caller_text(self) -> None:
        stream = io.StringIO()

        emit_public_text(
            r"token=abc123 and E:\private\workspace\note.md",
            stream=stream,
        )

        raw = stream.getvalue()
        self.assertNotIn("abc123", raw)
        self.assertNotIn(r"E:\private\workspace\note.md", raw)
        self.assertIn("<redacted:sensitive-output>", raw)

    def test_emit_public_json_preserves_shape_while_redacting_sensitive_fields(self) -> None:
        stream = io.StringIO()
        payload = {
            "secret": "raw-secret-value",
            "cwd": "/Users/example/private-project",
            "note": "token=raw-json-token",
        }

        emit_public_json(payload, stream=stream)

        encoded = stream.getvalue()
        emitted = json.loads(encoded)
        self.assertEqual(emitted["secret"], "<sensitive-value-redacted>")
        self.assertEqual(emitted["cwd"], "<local-path-redacted>")
        self.assertEqual(emitted["note"], "token=<sensitive-value-redacted>")
        self.assertNotIn("raw-secret-value", encoded)
        self.assertNotIn("raw-json-token", encoded)
        self.assertNotIn("/Users/example/private-project", encoded)

    def test_operator_json_redacts_credentials_without_breaking_recovery_paths(self) -> None:
        stream = io.StringIO()
        payload = {
            "target_path": r"C:\Users\Name\aippocampus-plugin",
            "rollback_command": r"aippocampus update rollback --path C:\Users\Name\backup",
            "api_key_env": "AIPPOCAMPUS_DEEPSEEK_API_KEY",
            "password": "hunter2",
            "nested": {
                "message": "provider failed with token=abc123 and keep path C:\\Users\\Name\\x",
                "total_tokens": 42,
            },
        }

        with contextlib.redirect_stdout(stream):
            operator_output.emit_operator_json(payload)

        emitted = json.loads(stream.getvalue())
        encoded = json.dumps(emitted, ensure_ascii=False)
        self.assertEqual(emitted["password"], "<redacted:sensitive-json-field>")
        self.assertEqual(emitted["api_key_env"], "AIPPOCAMPUS_DEEPSEEK_API_KEY")
        self.assertEqual(emitted["nested"]["total_tokens"], 42)
        self.assertIn(r"C:\Users\Name\aippocampus-plugin", emitted["target_path"])
        self.assertIn(r"C:\Users\Name\backup", emitted["rollback_command"])
        self.assertIn("token=<redacted:secret>", emitted["nested"]["message"])
        self.assertNotIn("hunter2", encoded)
        self.assertNotIn("token=abc123", encoded)


if __name__ == "__main__":
    unittest.main()
