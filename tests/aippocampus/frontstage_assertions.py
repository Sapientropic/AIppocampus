from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

COMPACT_DIAGNOSTIC_TOP_LEVEL_KEYS = {
    "cannot_claim",
    "red_lines",
    "detail_deferred",
    "source_boundary",
    "product_boundary",
    "route_availability_summary",
    "operator_diagnostics",
}

PRIVATE_PATH_MARKERS = (
    "C:\\",
    "E:\\",
    "/Users/",
    "/home/",
)

def assert_compact_frontstage_payload(
    test: Any,
    payload: Mapping[str, Any],
    *,
    max_top_level_diagnostics: int = 1,
    max_safe_actions: int = 5,
) -> None:
    """Assert default foreground JSON stays useful rather than audit-shaped."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    action = payload.get("foreground_action")
    test.assertIsInstance(action, Mapping)
    test.assertTrue(str(action.get("id") or "").strip())
    test.assertTrue(str(action.get("why") or action.get("label") or "").strip())
    test.assertNotIn("agent_next_action", payload)
    safe_actions = payload.get("safe_next_actions") or []
    test.assertLessEqual(len(safe_actions), max_safe_actions)
    leaked_keys = COMPACT_DIAGNOSTIC_TOP_LEVEL_KEYS.intersection(payload)
    test.assertLessEqual(
        len(leaked_keys),
        max_top_level_diagnostics,
        f"compact payload has too many diagnostic top-level keys: {sorted(leaked_keys)}",
    )
    test.assertNotIn("cannot_claim", payload)
    test.assertNotIn("red_lines", payload)
    for marker in PRIVATE_PATH_MARKERS:
        test.assertNotIn(marker, encoded)

def assert_semantic_human_output(
    test: Any,
    text: str,
    *,
    max_lines: int = 10,
    forbidden_boilerplate: tuple[str, ...] = ("cannot_claim",),
) -> None:
    """Assert human output is actionable without pinning incidental copy."""

    lines = [line for line in text.splitlines() if line.strip()]
    test.assertGreater(len(lines), 0)
    test.assertLessEqual(len(lines), max_lines)
    test.assertNotIn("Traceback", text)
    test.assertRegex(text, re.compile(r"(next|action|try|template|inspect|repair):", re.I))
    for phrase in forbidden_boilerplate:
        test.assertNotIn(phrase, text)
    for marker in PRIVATE_PATH_MARKERS:
        test.assertNotIn(marker, text)
