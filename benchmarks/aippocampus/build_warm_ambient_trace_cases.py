#!/usr/bin/env python3
"""Build sanitized warm ambient recall benchmark cases from clean source.

This is a local calibration helper, not a public memory surface. It exports
compact JSON/JSONL cases that `benchmark_warm_ambient_recall.py --cases-file`
can consume. The output may contain sanitized snippets from local clean source,
so generated files should be treated as private working artifacts and kept out
of the public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampuslib import compact_text, sanitize_external_model_text
from registry import load_registry, registry_paths
from search_clean_source import iter_clean_messages


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clean_text(value: Any, *, chars: int) -> tuple[str, dict[str, Any]]:
    text, policy = sanitize_external_model_text(str(value or ""))
    return compact_text(text.strip(), chars), policy


def source_ref_for(message: dict[str, Any], *, thread_key: str) -> dict[str, Any]:
    line = message.get("source_line", message.get("line"))
    ref = {
        "thread_key": thread_key,
        "line": as_int(line, 0) or line,
        "message_id": str(message.get("message_id") or "")[:160],
        "phase": str(message.get("phase") or "")[:80],
    }
    return {key: value for key, value in ref.items() if value not in {"", None, 0}}


def trace_row_for(message: dict[str, Any], *, thread_key: str) -> dict[str, Any] | None:
    text, _policy = clean_text(message.get("text"), chars=420)
    if not text:
        return None
    row = {
        "thread_key": thread_key,
        "role": compact_text(str(message.get("role") or ""), 40),
        "phase": compact_text(str(message.get("phase") or ""), 80),
        "turn_index": message.get("turn_index"),
        "text": text,
        "source_refs": [source_ref_for(message, thread_key=thread_key)],
    }
    return {
        key: value
        for key, value in row.items()
        if value is not None and value != "" and value != []
    }


def case_id_for(*, thread_key: str, message: dict[str, Any]) -> str:
    seed = "\n".join(
        [
            thread_key,
            str(message.get("message_id") or ""),
            str(message.get("source_line") or message.get("line") or ""),
            str(message.get("text") or "")[:160],
        ]
    )
    return "trace_" + sha1_text(seed)


def iter_thread_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in registry.get("threads") or [] if isinstance(entry, dict)]


def clean_messages_path(entry: dict[str, Any]) -> Path | None:
    raw = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
    if not raw:
        return None
    return Path(str(raw))


def build_cases_for_thread(
    entry: dict[str, Any],
    *,
    per_thread: int,
    trace_window: int,
    min_prompt_chars: int,
    include_redacted_prompts: bool,
    label_template: bool,
    skipped: dict[str, int],
) -> list[dict[str, Any]]:
    thread_key = compact_text(str(entry.get("thread_key") or ""), 160)
    path = clean_messages_path(entry)
    if not thread_key or path is None or not path.exists():
        skipped["missing_clean_source"] = skipped.get("missing_clean_source", 0) + 1
        return []

    messages = iter_clean_messages(path)
    if not messages:
        skipped["empty_clean_source"] = skipped.get("empty_clean_source", 0) + 1
        return []

    cases: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if len(cases) >= max(1, per_thread):
            break
        if str(message.get("role") or "").casefold() != "user":
            continue
        prompt, policy = clean_text(message.get("text"), chars=1200)
        if policy.get("redacted") and not include_redacted_prompts:
            skipped["redacted_prompt"] = skipped.get("redacted_prompt", 0) + 1
            continue
        if policy.get("hard_block"):
            skipped["hard_blocked_prompt"] = skipped.get("hard_blocked_prompt", 0) + 1
            continue
        if len(prompt) < min_prompt_chars:
            skipped["short_prompt"] = skipped.get("short_prompt", 0) + 1
            continue

        start = max(0, index - max(0, trace_window - 1))
        trace_messages = messages[start : index + 1]
        prompt_trace = [
            row
            for row in (trace_row_for(item, thread_key=thread_key) for item in trace_messages)
            if row is not None
        ]
        case = {
            "case_id": case_id_for(thread_key=thread_key, message=message),
            "prompt": prompt,
            "prompt_trace": prompt_trace,
            "current_thread_key": thread_key,
            "expected_available": None,
            "expected_min_cards": 0,
        }
        if label_template:
            case.update(manual_label_template_fields())
        cases.append(case)
    return cases


def manual_label_template_fields() -> dict[str, Any]:
    return {
        "expected_topic_epoch_action": None,
        "expected_topic_epoch_actions": [],
        "expected_min_source_validation_statuses": {},
        "expected_min_current_thread_echo_count": None,
        "expected_max_current_thread_echo_count": None,
        "label_notes": (
            "Private manual labels: set topic epoch action(s), source-ref validation "
            "status counts, and current-thread echo bounds after reviewing this sanitized trace."
        ),
    }


def build_trace_cases(
    *,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    limit: int = 50,
    per_thread: int = 5,
    trace_window: int = 6,
    min_prompt_chars: int = 8,
    include_redacted_prompts: bool = False,
    label_template: bool = False,
) -> dict[str, Any]:
    path = (
        Path(registry_path).resolve()
        if registry_path
        else registry_paths(Path(registry_dir).resolve() if registry_dir else None)[0]
    )
    registry = load_registry(path)
    skipped: dict[str, int] = {
        "missing_clean_source": 0,
        "empty_clean_source": 0,
        "redacted_prompt": 0,
        "hard_blocked_prompt": 0,
        "short_prompt": 0,
    }
    cases: list[dict[str, Any]] = []
    for entry in iter_thread_entries(registry):
        if len(cases) >= max(0, limit):
            break
        thread_cases = build_cases_for_thread(
            entry,
            per_thread=per_thread,
            trace_window=trace_window,
            min_prompt_chars=min_prompt_chars,
            include_redacted_prompts=include_redacted_prompts,
            label_template=label_template,
            skipped=skipped,
        )
        remaining = max(0, limit - len(cases))
        cases.extend(thread_cases[:remaining])

    return {
        "kind": "aippocampus_warm_ambient_trace_cases",
        "schema_version": 1,
        "registry_sha1": sha1_text(str(path)),
        "case_count": len(cases),
        "label_template": bool(label_template),
        "cases": cases,
        "skipped": skipped,
        "privacy_boundary": {
            "raw_registry_paths_emitted": False,
            "raw_clean_source_paths_emitted": False,
            "redacted_prompts_skipped_by_default": not include_redacted_prompts,
        },
        "note": "Generated cases are private calibration artifacts; do not commit real trace exports.",
    }


def write_cases_file(cases: list[dict[str, Any]], path: Path | str, *, jsonl: bool = False) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if jsonl:
        target.write_text(
            "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + ("\n" if cases else ""),
            encoding="utf-8",
        )
    else:
        target.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--jsonl", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--per-thread", type=int, default=5)
    parser.add_argument("--trace-window", type=int, default=6)
    parser.add_argument("--min-prompt-chars", type=int, default=8)
    parser.add_argument("--include-redacted-prompts", action="store_true")
    parser.add_argument(
        "--label-template",
        action="store_true",
        help="Emit empty manual labels for source-ref, echo, and topic-drift calibration.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = build_trace_cases(
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        limit=args.limit,
        per_thread=args.per_thread,
        trace_window=args.trace_window,
        min_prompt_chars=args.min_prompt_chars,
        include_redacted_prompts=args.include_redacted_prompts,
        label_template=args.label_template,
    )
    output = write_cases_file(payload["cases"], args.out, jsonl=args.jsonl)
    summary = {
        "kind": payload["kind"],
        "schema_version": payload["schema_version"],
        "case_count": payload["case_count"],
        "label_template": payload["label_template"],
        "skipped": payload["skipped"],
        "output": str(output),
        "privacy_boundary": payload["privacy_boundary"],
    }
    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"warm ambient trace cases: cases={payload['case_count']} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
