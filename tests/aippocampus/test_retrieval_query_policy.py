from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.recall import query_policy as policy  # noqa: E402


class RetrievalQueryPolicyTests(unittest.TestCase):
    def test_semantic_trigger_terms_extract_multilingual_aliases_without_static_aliases(self) -> None:
        rows = [
            {
                "source": "semantic_cue_cache",
                "title": "External memory continuation",
                "aliases": ["memoria externa", "внешний гиппокамп", "ذاكرة سياقية"],
                "matched_terms": ["memoria externa"],
            },
            {
                "source": "semantic_triggers",
                "title": "Local path should be ignored",
                "aliases": [r"E:\\FAKE_TEST_LOCAL_PATH\\secret\\memory", "external hippocampus"],
            },
        ]

        terms = policy.semantic_trigger_terms(rows)

        self.assertIn("memoria externa", terms)
        self.assertIn("внешний гиппокамп", terms)
        self.assertIn("ذاكرة سياقية", terms)
        self.assertIn("external hippocampus", terms)
        self.assertNotIn(r"E:\\FAKE_TEST_LOCAL_PATH\\secret\\memory", terms)

    def test_domain_semantic_aliases_are_not_kept_in_static_alias_table(self) -> None:
        all_static_aliases = {
            str(alias).casefold()
            for aliases in policy.ALIASES.values()
            for alias in aliases
        }

        self.assertNotIn("external hippocampus", all_static_aliases)
        self.assertNotIn("active recall", all_static_aliases)
        self.assertIn(
            "external hippocampus",
            policy.semantic_trigger_terms(
                [
                    {
                        "source": "semantic_triggers",
                        "title": "External hippocampus recall continuity",
                        "aliases": ["external hippocampus", "active recall"],
                    }
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
