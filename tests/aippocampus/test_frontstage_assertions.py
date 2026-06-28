from __future__ import annotations

import unittest

from tests.aippocampus import frontstage_assertions


class FrontstageAssertionPolicyTests(unittest.TestCase):
    def test_compact_detail_affordance_allowlist_has_owner_policy(self) -> None:
        self.assertEqual(frontstage_assertions.compact_detail_affordance_policy_issues(), [])

    def test_unowned_compact_detail_affordance_is_rejected(self) -> None:
        issues = frontstage_assertions.compact_detail_affordance_policy_issues(
            {
                "bad.surface": {
                    ("operator_detail_command",): "legacy string reason without owner",
                }
            }
        )

        self.assertEqual(
            issues,
            ["bad.surface:operator_detail_command missing structured policy"],
        )


if __name__ == "__main__":
    unittest.main()
