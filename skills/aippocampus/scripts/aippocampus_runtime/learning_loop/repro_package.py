"""Repro-package foreground payloads for learning and issue reports."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.learning_loop.dogfood_cases import build_sanitized_repro_package
from aippocampus_runtime.learning_loop.frontdoor_common import (
    KIND,
    SCHEMA_VERSION,
    privacy_boundary,
    public_payload,
    with_boundary_detail,
)


def _runtime_version() -> str:
    try:
        return importlib.metadata.version("aippocampus")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _load_repro_package_input(args: Any) -> Any:
    if args.input_json and args.stdin:
        raise ValueError("choose only one of --input-json or --stdin")
    if args.stdin:
        return json.loads(sys.stdin.read())
    return json.loads(args.input_json.read_text(encoding="utf-8"))


def repro_package_payload(args: Any) -> dict[str, Any]:
    payload = _load_repro_package_input(args)
    if not isinstance(payload, Mapping):
        raise ValueError("--input-json must contain a JSON object")
    missing = [
        field
        for field in ("command", "expected", "actual")
        if not str(payload.get(field) or "").strip()
    ]
    if missing:
        raise ValueError("missing required repro fields: " + ", ".join(missing))
    if not (
        payload.get("output") is not None
        or payload.get("stdout") is not None
        or payload.get("output_ref")
    ):
        raise ValueError("missing one of output, stdout, or output_ref")
    package = build_sanitized_repro_package(
        payload,
        version=args.version or _runtime_version(),
        commit=args.commit or "unknown",
        plugin_manifest_version=args.plugin_manifest_version or "unknown",
    )
    primary = {
        "id": "review_public_safe_repro_package",
        "label": "Review public-safe repro package",
        "message": "Paste repro_package into a public issue only after human review.",
        "mutation_risk": "manual_public_issue_write",
        "claim_boundary": "repro_package_not_source_truth",
    }
    return public_payload(
        with_boundary_detail(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "repro_package",
                "ok": bool(package.get("ok")),
                "repro_package": package,
                **canonical_foreground_action_fields(primary, safe_next_actions=[primary]),
                "privacy_boundary": package.get("privacy_boundary") or privacy_boundary(),
            },
            cannot_claim=[
                "source_truth_from_repro_package",
                "official_benchmark_score_from_repro_package",
                "private_history_quality",
            ],
        )
    )


def repro_package_template_payload() -> dict[str, Any]:
    schema = repro_package_input_schema()
    template = schema["redacted_example"]
    template_json = json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True)
    primary = foreground_shell_action(
        action_id="package_repro_input_file",
        label="Package a saved repro input JSON file",
        command="aippocampus repro package --input-json repro-input.json --json",
        why="Use this after writing the template JSON to repro-input.json and filling expected/actual.",
        mutation_risk="read_only",
        claim_boundary="repro_package_not_source_truth",
    )
    stdin_action = foreground_shell_action(
        action_id="package_repro_stdin",
        label="Package repro JSON through stdin",
        command="cat repro-input.json | aippocampus repro package --stdin --json",
        why="Portable Unix stdin path when a pipe is preferred.",
        mutation_risk="read_only",
        claim_boundary="repro_package_not_source_truth",
    )
    validate_action = foreground_shell_action(
        action_id="validate_repro_input_json",
        label="Validate repro input JSON",
        command="python -m json.tool repro-input.json",
        why="Check JSON syntax before packaging.",
        mutation_risk="read_only",
        claim_boundary="syntax_check_not_source_evidence",
    )
    return public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "repro_package_template",
            "ok": True,
            "template": template,
            "template_json": template_json,
            "stdin_payload": template_json,
            "expected_input_schema": schema,
            **canonical_foreground_action_fields(
                primary,
                safe_next_actions=[primary, stdin_action, validate_action],
            ),
            "input_delivery": {
                "primary": "input_json_file",
                "stdin_payload_field": "stdin_payload",
            },
            "next_actions": [
                {"label": str(action.get("label") or action.get("id")), "command": str(action["command"]), "mutates": False}
                for action in (primary, stdin_action)
            ],
            "privacy_boundary": privacy_boundary(),
        }
    )


def repro_package_input_schema() -> dict[str, Any]:
    return {
        "required": ["command", "expected", "actual"],
        "one_of": ["output", "output_ref"],
        "optional": ["surface", "source_refs", "privacy_boundary"],
        "redacted_example": {
            "surface": "agent_recall",
            "command": "aippocampus agent recall \"old decision or handoff cue\" --json",
            "output_ref": "saved-output://local/redacted-command-output.json",
            "expected": "source-backed route appears with reopen boundary",
            "actual": "route was missing or degraded",
            "source_refs": [{"source_id": "public-fixture-source", "message_id": "msg_public_001"}],
            "privacy_boundary": "no raw private stdout or prompt text",
        },
    }


def repro_package_recovery_payload(*, malformed_error: str | None = None) -> dict[str, Any]:
    code = "learning_repro_input_malformed" if malformed_error else "learning_repro_input_required"
    primary = foreground_shell_action(
        action_id="show_repro_package_template",
        label="Show repro package template",
        command="aippocampus repro package --template --json",
        why="Start with a redacted template before packaging public issue evidence.",
        mutation_risk="read_only",
        claim_boundary="repro_package_not_source_truth",
    )
    guidance = foreground_shell_action(
        action_id="inspect_learning_guidance",
        label="Inspect learning guidance first",
        command="aippocampus learning guidance --json",
        why="Use when the repro should come from a prepared learning or guidance result.",
        mutation_risk="read_only",
        claim_boundary="learning_guidance_not_source_truth",
    )
    package_file = foreground_shell_action(
        action_id="package_repro_input_file",
        label="Package a saved repro input JSON file",
        command="aippocampus repro package --input-json command-output.json --json",
        why="Use after filling the expected input schema with redacted output or output_ref.",
        mutation_risk="read_only",
        claim_boundary="repro_package_not_source_truth",
    )
    return public_payload(
        with_boundary_detail(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "repro_package_recovery",
                "ok": False,
                "error": {
                    "code": code,
                    "message": (
                        "repro-package needs a saved JSON object with command plus output or "
                        "output_ref and expected/actual fields; no private stdout or prompt text "
                        "was read."
                    ),
                    "malformed_error": malformed_error or "",
                    "next_command": "aippocampus repro package --template --json",
                },
                **canonical_foreground_action_fields(
                    primary,
                    safe_next_actions=[primary, package_file, guidance],
                ),
                "expected_input_schema": repro_package_input_schema(),
                "recovery_paths": [
                    {
                        "label": "from sanitized replay or guidance output",
                        "steps": [
                            "run `aippocampus learning guidance --json` or sanitized replay",
                            "save the relevant command outcome as the expected input schema",
                            "run `aippocampus repro package --input-json command-output.json --json`",
                        ],
                        "copyable_validate_command": "python -m json.tool command-output.json",
                        "copyable_package_command": "aippocampus repro package --input-json command-output.json --json",
                        "mutates": False,
                    },
                    {
                        "label": "fresh command/output capture template",
                        "steps": [
                            "run the foreground command manually",
                            "record only redacted output or an output_ref",
                            "fill command/expected/actual/source_refs before packaging",
                        ],
                        "template": repro_package_input_schema()["redacted_example"],
                        "copyable_template_command": "aippocampus repro package --template --json",
                        "copyable_stdin_command": "cat command-output.json | aippocampus repro package --stdin --json",
                        "mutates": False,
                    },
                ],
                "next_actions": [
                    {
                        "label": "inspect learning guidance first",
                        "command": "aippocampus learning guidance --json",
                        "mutates": False,
                    }
                ],
                "privacy_boundary": privacy_boundary(),
            },
            cannot_claim=[
                "source_truth_from_repro_package",
                "private_history_quality",
            ],
        )
    )
