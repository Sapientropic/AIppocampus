from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.contracts import shell_quote
from aippocampus_runtime.question import frontdoor as question_frontdoor


class CommandQuotingContractTests(unittest.TestCase):
    def test_question_route_search_command_uses_shared_shell_quote(self) -> None:
        title = 'a$(echo PWNED)b `touch owned` "quoted"\nnext'

        command = question_frontdoor._search_command(title)

        self.assertEqual(command, f"aippocampus search {shell_quote(title)} --json")
        self.assertNotIn(f'"{title}"', command)
        self.assertIn("$(echo PWNED)", command)

    def test_question_frontdoor_has_no_manual_shell_escape_quoter(self) -> None:
        source = (SCRIPTS / "aippocampus_runtime" / "question" / "frontdoor.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(r'replace("\\", "\\\\").replace(\'"\', \'\\\"\')', source)
        self.assertIn("shell_quote(", source)

    def test_aippocampus_command_builders_do_not_hand_roll_shell_quoting(self) -> None:
        offenders: list[str] = []
        manual_patterns = (
            r'replace("\\", "\\\\").replace(\'"\', \'\\\"\')',
            r'replace("\\", "\\\\").replace("\"", "\\\"")',
        )
        for path in (SCRIPTS / "aippocampus_runtime").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "aippocampus " not in text:
                continue
            for pattern in manual_patterns:
                if pattern in text:
                    offenders.append(str(path.relative_to(SCRIPTS)))

        self.assertEqual(offenders, [])

if __name__ == "__main__":
    unittest.main()
