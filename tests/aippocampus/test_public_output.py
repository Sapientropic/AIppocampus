from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.public_output import emit_public_text  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
