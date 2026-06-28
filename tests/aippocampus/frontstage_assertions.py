from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.foreground_action_lint import compact_foreground_action_violations
from aippocampus_runtime.mcp.compact_profile import COMPACT_DEBUG_FIELD_DENYLIST

PathComponent = str | int

COMPACT_DIAGNOSTIC_TOP_LEVEL_KEYS = {
    "apw_route_identity",
    "associative_path_fallback",
    "associative_path_policy",
    "cannot_claim",
    "diagnostic_detail_command",
    "feedback_actions",
    "feedback_boundary",
    "red_lines",
    "detail_deferred",
    "source_boundary",
    "product_boundary",
    "route_availability_summary",
    "operator_diagnostics",
    "operator_detail_command",
    "operator_detail_command_template",
    "output_boundary",
    "policy_boundary",
    "provider_key_bridge",
    "recall_gate_context",
    "runtime_provenance",
    "semantic_gate_diagnostics",
    "source_anchor_gate",
}

PRIVATE_PATH_MARKERS = (
    "C:\\",
    "E:\\",
    "/Users/",
    "/home/",
)

COMPACT_DETAIL_AFFORDANCE_KEYS = {
    "operator_detail_command",
    "operator_detail_command_template",
    "operator_detail_requires",
    "operator_json_command_template",
    "operator_json_requires",
    "detail_available_with",
    "detail_available_with_template",
    "detail_requires",
}

@dataclass(frozen=True)
class CompactDetailAffordancePolicy:
    owner: str
    reason: str
    default_exposure: str
    removal_condition: str


def _detail_policy(
    *,
    owner: str,
    reason: str,
    default_exposure: str,
    removal_condition: str,
) -> CompactDetailAffordancePolicy:
    return CompactDetailAffordancePolicy(
        owner=owner,
        reason=reason,
        default_exposure=default_exposure,
        removal_condition=removal_condition,
    )


COMPACT_DETAIL_AFFORDANCE_ALLOWLIST: dict[
    str,
    Mapping[tuple[PathComponent, ...], CompactDetailAffordancePolicy],
] = {
    "agent_recall.safe_cue_detail": {
        (
            "operator_detail_command",
        ): _detail_policy(
            owner="recall foreground projection",
            reason=(
                "A safe cue can offer one full-detail CLI reopen path without "
                "exposing diagnostics inline."
            ),
            default_exposure="one explicit full-detail CLI command only",
            removal_condition="remove when recall compact exposes no command-bearing detail hatch",
        ),
        (
            "claim_boundary",
            "detail_available_with",
        ): _detail_policy(
            owner="recall foreground projection",
            reason=(
                "The claim boundary may point at the same full-detail command "
                "as the compact escape hatch."
            ),
            default_exposure="claim boundary points to the same detail command",
            removal_condition="remove with agent_recall.safe_cue_detail command hatch",
        ),
    },
    "agent_recall.template_detail": {
        (
            "operator_detail_command_template",
        ): _detail_policy(
            owner="recall foreground projection",
            reason="No cue-specific command is executable yet, so compact JSON carries only a template.",
            default_exposure="template_only command; not executable until caller supplies cue",
            removal_condition="remove when missing-cue recall card has a non-command detail signal",
        ),
        (
            "operator_detail_requires",
        ): _detail_policy(
            owner="recall foreground projection",
            reason="The template must name the missing cue instead of pretending to be executable.",
            default_exposure="required-input metadata beside the template",
            removal_condition="remove with agent_recall.template_detail command template",
        ),
        (
            "claim_boundary",
            "detail_available_with_template",
        ): _detail_policy(
            owner="recall foreground projection",
            reason="Claim-boundary detail follows the same template-only rule.",
            default_exposure="claim boundary names the template-only detail path",
            removal_condition="remove with agent_recall.template_detail command template",
        ),
        (
            "claim_boundary",
            "detail_requires",
        ): _detail_policy(
            owner="recall foreground projection",
            reason="The claim-boundary template must also declare its missing cue.",
            default_exposure="required-input metadata beside the claim-boundary template",
            removal_condition="remove with agent_recall.template_detail command template",
        ),
    },
    "cli.agent_aippo.needs_input": {
        (
            "operator_json_command_template",
        ): _detail_policy(
            owner="agent aippo CLI foreground card",
            reason="The AIppo parent card needs one operator JSON template for explicit diagnostic mode.",
            default_exposure="template_only operator JSON path; not a safe_next_action",
            removal_condition="remove when the no-input AIppo card has a non-command detail affordance",
        ),
        (
            "operator_json_requires",
        ): _detail_policy(
            owner="agent aippo CLI foreground card",
            reason="The operator JSON template must name the missing task cue.",
            default_exposure="required-input metadata beside the template",
            removal_condition="remove with cli.agent_aippo.needs_input command template",
        ),
        (
            "claim_boundary",
            "detail_available_with_template",
        ): _detail_policy(
            owner="agent aippo CLI foreground card",
            reason=(
                "The claim boundary may point at the same operator JSON "
                "template without serializing diagnostics."
            ),
            default_exposure="claim boundary names the template-only detail path",
            removal_condition="remove with cli.agent_aippo.needs_input command template",
        ),
        (
            "claim_boundary",
            "detail_requires",
        ): _detail_policy(
            owner="agent aippo CLI foreground card",
            reason="The claim-boundary template must also declare its missing task cue.",
            default_exposure="required-input metadata beside the claim-boundary template",
            removal_condition="remove with cli.agent_aippo.needs_input command template",
        ),
    },
    "cli.navigate.needs_cue": {
        (
            "lanes",
            0,
            "operator_detail_command",
        ): _detail_policy(
            owner="CLI recovery navigation card",
            reason=(
                "The no-cue navigation card has no route to deepen, so one "
                "lane-level detail affordance is useful."
            ),
            default_exposure="lane-level detail command only when no cue exists",
            removal_condition="remove when no-cue navigation has a non-command detail affordance",
        ),
        (
            "lanes",
            1,
            "operator_detail_command",
        ): _detail_policy(
            owner="CLI recovery navigation card",
            reason="Concept expansion is also operator-only until the user supplies a concrete navigation cue.",
            default_exposure="lane-level detail command only when no cue exists",
            removal_condition="remove when no-cue navigation has a non-command detail affordance",
        ),
    },
    "mcp.agent_deepen.missing_selector": {},
    "task_orientation.compact": {},
}


def compact_detail_affordance_policy_issues(
    allowlist: Mapping[
        str,
        Mapping[tuple[PathComponent, ...], Any],
    ] = COMPACT_DETAIL_AFFORDANCE_ALLOWLIST,
) -> list[str]:
    issues: list[str] = []
    for surface, paths in sorted(allowlist.items()):
        for path, policy in sorted(paths.items(), key=lambda item: _format_path(item[0])):
            if not isinstance(policy, CompactDetailAffordancePolicy):
                issues.append(f"{surface}:{_format_path(path)} missing structured policy")
                continue
            missing = [
                name
                for name in ("owner", "reason", "default_exposure", "removal_condition")
                if not str(getattr(policy, name)).strip()
            ]
            if missing:
                issues.append(
                    f"{surface}:{_format_path(path)} missing {', '.join(missing)}"
                )
    return issues


def _format_path(path: tuple[PathComponent, ...]) -> str:
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered = f"{rendered}[{part}]"
        elif rendered:
            rendered = f"{rendered}.{part}"
        else:
            rendered = part
    return rendered


def _detail_affordance_paths(value: Any, path: tuple[PathComponent, ...] = ()) -> set[tuple[PathComponent, ...]]:
    paths: set[tuple[PathComponent, ...]] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = (*path, str(key))
            if key in COMPACT_DETAIL_AFFORDANCE_KEYS:
                paths.add(child_path)
            paths.update(_detail_affordance_paths(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, child in enumerate(value):
            paths.update(_detail_affordance_paths(child, (*path, index)))
    return paths


def assert_compact_detail_affordances(
    test: Any,
    payload: Mapping[str, Any],
    *,
    surface: str,
) -> None:
    """Assert compact/default detail escape hatches are intentional and scoped."""

    test.assertIn(surface, COMPACT_DETAIL_AFFORDANCE_ALLOWLIST)
    allowed = set(COMPACT_DETAIL_AFFORDANCE_ALLOWLIST[surface])
    actual = _detail_affordance_paths(payload)
    test.assertEqual(
        sorted(_format_path(path) for path in actual - allowed),
        [],
        f"unexpected compact detail affordance on {surface}",
    )
    test.assertEqual(
        sorted(_format_path(path) for path in allowed - actual),
        [],
        f"missing expected compact detail affordance on {surface}",
    )


def assert_compact_frontstage_payload(
    test: Any,
    payload: Mapping[str, Any],
    *,
    max_top_level_diagnostics: int = 1,
    max_safe_actions: int = 1,
    allow_write_safe_actions: bool = False,
    current_status_command: str | None = None,
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
    test.assertEqual(
        compact_foreground_action_violations(
            payload,
            max_safe_actions=max_safe_actions,
            allow_write_safe_actions=allow_write_safe_actions,
            current_status_command=current_status_command,
        ),
        [],
    )
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


def compact_debug_field_paths(
    value: Any,
    path: tuple[PathComponent, ...] = (),
) -> list[str]:
    if isinstance(value, Mapping):
        paths: list[str] = []
        for key, child in value.items():
            child_path = (*path, str(key))
            if key in COMPACT_DEBUG_FIELD_DENYLIST:
                paths.append(_format_path(child_path))
            paths.extend(compact_debug_field_paths(child, child_path))
        return paths
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        paths = []
        for index, child in enumerate(value):
            paths.extend(compact_debug_field_paths(child, (*path, index)))
        return paths
    return []


def assert_no_compact_debug_fields(
    test: Any,
    payload: Mapping[str, Any],
    *,
    surface: str,
) -> None:
    """Assert MCP compact structuredContent is a product card, not proof dump."""

    test.assertEqual(
        compact_debug_field_paths(payload),
        [],
        f"compact surface {surface} leaked detail/operator fields",
    )


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
