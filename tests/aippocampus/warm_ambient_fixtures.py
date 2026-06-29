from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any, Callable


def write_clean_thread(root: Path, thread_key: str, rows: list[dict[str, Any]]) -> Path:
    clean_dir = root / "clean" / thread_key.replace(":", "-")
    clean_dir.mkdir(parents=True)
    messages_path = clean_dir / "messages.jsonl"
    messages_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return messages_path


def source_ref(
    thread_key: str = "session:old",
    message_id: str = "msg-1",
    line: int | None = 1,
    **extra: Any,
) -> dict[str, Any]:
    ref = {"thread_key": thread_key, "message_id": message_id, **extra}
    if line is not None:
        ref["line"] = line
    return ref


def clean_message(
    text: str,
    *,
    message_id: str = "msg-1",
    source_line: int = 1,
    role: str = "assistant",
    phase: str | None = "final_answer",
    is_final: bool | None = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "message_id": message_id,
        "source_line": source_line,
        "role": role,
        "text": text,
    }
    if phase is not None:
        row["phase"] = phase
    if is_final is not None:
        row["is_final"] = is_final
    return row


def prompt_trace_entry(
    text: str,
    *,
    thread_key: str = "session:old",
    role: str = "assistant",
    phase: str = "final_answer",
    message_id: str = "msg-1",
    line: int = 1,
) -> dict[str, Any]:
    return {
        "thread_key": thread_key,
        "role": role,
        "phase": phase,
        "text": text,
        "source_refs": [source_ref(thread_key, message_id, line)],
    }


def candidate_card(
    theme: str,
    *,
    support_level: str = "candidate",
    **fields: Any,
) -> dict[str, Any]:
    return {"theme": theme, "support_level": support_level, **fields}


def scout_candidates(
    *candidates: dict[str, Any],
    decision: str = "candidate",
    confidence: float = 0.75,
    **response_fields: Any,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "confidence": confidence,
        "candidates": list(candidates),
        **response_fields,
    }


def scout_candidate(
    theme: str,
    *,
    support_level: str = "candidate",
    confidence: float = 0.75,
    decision: str = "candidate",
    themes: list[str] | None = None,
    response_fields: dict[str, Any] | None = None,
    **candidate_fields: Any,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "decision": decision,
        "confidence": confidence,
        "candidates": [candidate_card(theme, support_level=support_level, **candidate_fields)],
    }
    if response_fields:
        response.update(response_fields)
    if themes is not None:
        response["themes"] = themes
    return response


def scout_skip(*, confidence: float = 0.1, **fields: Any) -> dict[str, Any]:
    return {"decision": "skip", "confidence": confidence, **fields}


def scout_block(reason: str, *, confidence: float = 0.91, **fields: Any) -> dict[str, Any]:
    return scout_skip(confidence=confidence, block=True, reason=reason, **fields)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_cli_json(main: Callable[[list[str]], int], argv: list[str]) -> tuple[int, dict[str, Any], str]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = main(argv)
    raw_output = stdout.getvalue()
    return code, json.loads(raw_output), raw_output


def assert_stale_queue_foreground_contract(case: Any, payload: dict[str, Any]) -> None:
    from aippocampus_runtime.warm_ambient.status_card import compact_warm_status_card

    case.assertNotIn("agent_next_action", payload)
    case.assertEqual(payload["foreground_action"]["id"], "continue_with_ordinary_recall")
    case.assertEqual(payload["foreground_action"]["command_template"], 'aippocampus agent recall "{cue}" --json')
    case.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
    action_ids = [action["id"] for action in payload["safe_next_actions"]]
    case.assertIn("recheck_warm_status", action_ids)
    case.assertNotIn("inspect_provider_status", action_ids)
    case.assertNotIn("plan_warm_repair", action_ids)
    case.assertNotIn("aippocampus doctor provider --json", json.dumps(payload, ensure_ascii=False))
    case.assertIn("probe_warm_worker_once", action_ids)
    case.assertNotIn("snooze_optional_warm_ambient", action_ids)
    case.assertIn("retire_stale_warm_queue_after_review", action_ids)
    case.assertNotIn("continue_with_ordinary_recall", action_ids)
    probe_action = next(
        action for action in payload["safe_next_actions"] if action["id"] == "probe_warm_worker_once"
    )
    case.assertEqual(
        probe_action["command_template"],
        'aippocampus warm --prompt "{cue}" --no-write --wait-all --json',
    )
    case.assertEqual(probe_action["requires"], ["cue"])
    retire_action = next(
        action
        for action in payload["safe_next_actions"]
        if action["id"] == "retire_stale_warm_queue_after_review"
    )
    case.assertNotIn("command", retire_action)
    case.assertTrue(retire_action["manual_only"])
    case.assertTrue(retire_action["continue_without_command"])
    case.assertNotIn("template_only", retire_action)
    case.assertIn("manual_instruction", retire_action)
    case.assertTrue(
        all(
            "command_template" in action or not action.get("template_only")
            for action in payload["safe_next_actions"]
        )
    )
    encoded = json.dumps(payload, ensure_ascii=False)
    case.assertNotIn("set the provider key or leave warm ambient off", encoded)

    card = compact_warm_status_card(payload)
    case.assertEqual(card["kind"], "aippocampus_warm_ambient_status_card")
    case.assertEqual(card["detail"], "compact")
    case.assertEqual(card["status"], "blocked_stale_queue")
    case.assertTrue(card["ordinary_recall_usable"])
    case.assertTrue(card["warm_not_blocking_recall"])
    case.assertEqual(card["foreground_action"]["id"], "continue_with_ordinary_recall")
    case.assertLessEqual(len(card["safe_next_actions"]), 1)
    case.assertNotIn("manage_command", card)
    case.assertTrue(card["details_available"])
    compact_encoded = json.dumps(card, ensure_ascii=False)
    case.assertNotIn("action_code", compact_encoded)
    case.assertIn("probe_warm_worker_once", compact_encoded)
    case.assertNotIn("snooze_optional_warm_ambient", compact_encoded)
    case.assertNotIn("retire_stale_warm_queue_after_review", compact_encoded)
    case.assertNotIn("AIPPOCAMPUS_WARM_RECALL_BACKGROUND", compact_encoded)

def write_registry(root: Path, entries: list[dict[str, Any]]) -> Path:
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_path

def write_thread_registry(
    root: Path,
    thread_key: str,
    rows: list[dict[str, Any]],
    *,
    title: str = "Old ambient thread",
) -> Path:
    messages_path = write_clean_thread(root, thread_key, rows)
    return write_registry(
        root,
        [
            {
                "thread_key": thread_key,
                "title": title,
                "paths": {"clean_source_messages_jsonl": str(messages_path)},
            }
        ],
    )
