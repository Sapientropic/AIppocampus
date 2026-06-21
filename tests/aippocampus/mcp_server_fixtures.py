from __future__ import annotations

import unittest


def field_path_count(value: object, prefix: str = "") -> int:
    if isinstance(value, dict):
        total = 0
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            total += 1 + field_path_count(item, path)
        return total
    if isinstance(value, list):
        total = 0
        for index, item in enumerate(value):
            path = f"{prefix}[]" if prefix else f"[{index}]"
            total += field_path_count(item, path)
        return total
    return 0


def assert_recall_template_action(
    test: unittest.TestCase,
    action: dict[str, object],
    *,
    action_id: str = "recall_with_cue",
    full_detail: bool = False,
) -> None:
    test.assertEqual(action["id"], action_id)
    test.assertEqual(action["requires"], ["cue"])
    test.assertTrue(action["template_only"])
    test.assertEqual(action["tool_name"], "agent_recall")
    test.assertEqual(action["arguments_template"], {"query": "{cue}"})
    command_template = str(action["command_template"])
    test.assertIn('aippocampus agent recall "{cue}" --json', command_template)
    if full_detail:
        test.assertIn("--detail full", command_template)
    test.assertEqual(action["mutation_risk"], "read_only")
    test.assertEqual(action["claim_boundary"], "no_claim_before_reopen")
