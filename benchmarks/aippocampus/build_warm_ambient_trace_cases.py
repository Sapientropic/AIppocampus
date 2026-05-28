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


def resolve_clean_source_messages_path(
    *,
    clean_source_messages: Path | str | None = None,
    clean_source_dir: Path | str | None = None,
) -> Path | None:
    if clean_source_messages:
        return Path(clean_source_messages)
    if clean_source_dir:
        return Path(clean_source_dir) / "messages.jsonl"
    return None


def iter_clean_messages_stream(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("text"):
                yield item


def group_key_for_message(message: dict[str, Any]) -> str:
    meta = message.get("_meta") if isinstance(message.get("_meta"), dict) else {}
    return compact_text(
        str(
            message.get("source_id")
            or meta.get("conversation_id")
            or meta.get("source_file")
            or "clean_source"
        ),
        160,
    )


def corpus_thread_key(*, dataset_id: str | None, messages_path: Path) -> str:
    # Public corpora can be huge and path-shaped dataset ids can leak local
    # layout. Keep one synthetic registry thread per sampled case pack and use
    # message_id for exact dereference inside that pack.
    label = compact_text(str(dataset_id or messages_path.parent.name or messages_path.stem), 120)
    return "corpus:" + sha1_text(label or "clean-source")


def sanitized_subset_message(message: dict[str, Any]) -> dict[str, Any]:
    # The case-pack registry is only for local source-ref validation during
    # tuning. Keep dereference fields and sanitized text; drop dataset metadata
    # such as raw source files or conversation ids so aggregate reports cannot
    # become an accidental corpus manifest.
    keep = (
        "message_id",
        "turn_id",
        "source_id",
        "clean_ordinal",
        "source_line",
        "line",
        "role",
        "phase",
        "turn_index",
        "is_final",
    )
    clean = {key: message.get(key) for key in keep if key in message}
    text, _policy = clean_text(message.get("text"), chars=1600)
    clean["text"] = text
    return clean


def append_subset_message(
    target: list[dict[str, Any]],
    seen: set[str],
    message: dict[str, Any],
) -> None:
    key = "|".join(
        [
            str(message.get("message_id") or ""),
            str(message.get("source_line") or message.get("line") or ""),
            sha1_text(str(message.get("text") or "")),
        ]
    )
    if key in seen:
        return
    seen.add(key)
    target.append(sanitized_subset_message(message))


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


def build_cases_for_message_group(
    messages: list[dict[str, Any]],
    *,
    thread_key: str,
    per_thread: int,
    trace_window: int,
    min_prompt_chars: int,
    include_redacted_prompts: bool,
    label_template: bool,
    skipped: dict[str, int],
    subset_messages: list[dict[str, Any]],
    subset_seen: set[str],
) -> list[dict[str, Any]]:
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
        for item in trace_messages:
            append_subset_message(subset_messages, subset_seen, item)
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


def build_cases_from_clean_source_messages(
    messages_path: Path,
    *,
    dataset_id: str | None,
    limit: int,
    per_thread: int,
    trace_window: int,
    min_prompt_chars: int,
    include_redacted_prompts: bool,
    label_template: bool,
) -> dict[str, Any]:
    skipped: dict[str, int] = {
        "missing_clean_source": 0,
        "empty_clean_source": 0,
        "redacted_prompt": 0,
        "hard_blocked_prompt": 0,
        "short_prompt": 0,
    }
    if not messages_path.exists():
        skipped["missing_clean_source"] = 1
    messages: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    subset_messages: list[dict[str, Any]] = []
    subset_seen: set[str] = set()
    thread_key = corpus_thread_key(dataset_id=dataset_id, messages_path=messages_path)
    current_group_key = ""

    def flush_group(group: list[dict[str, Any]]) -> None:
        if not group or len(cases) >= max(0, limit):
            return
        remaining = max(0, limit - len(cases))
        group_cases = build_cases_for_message_group(
            group,
            thread_key=thread_key,
            per_thread=min(max(1, per_thread), remaining),
            trace_window=trace_window,
            min_prompt_chars=min_prompt_chars,
            include_redacted_prompts=include_redacted_prompts,
            label_template=label_template,
            skipped=skipped,
            subset_messages=subset_messages,
            subset_seen=subset_seen,
        )
        cases.extend(group_cases[:remaining])

    if messages_path.exists():
        for message in iter_clean_messages_stream(messages_path):
            group_key = group_key_for_message(message)
            if current_group_key and group_key != current_group_key:
                flush_group(messages)
                if len(cases) >= max(0, limit):
                    break
                messages = []
            current_group_key = group_key
            messages.append(message)
        if len(cases) < max(0, limit):
            flush_group(messages)
    if not cases and not any(value for key, value in skipped.items() if key != "empty_clean_source"):
        skipped["empty_clean_source"] = 1

    return {
        "kind": "aippocampus_warm_ambient_trace_cases",
        "schema_version": 1,
        "source_mode": "clean_source_messages",
        "source_sha1": sha1_text(str(dataset_id or messages_path.name)),
        "case_count": len(cases),
        "label_template": bool(label_template),
        "cases": cases,
        "source_subset": {
            "thread_key": thread_key,
            "message_count": len(subset_messages),
            "messages": subset_messages,
        },
        "skipped": skipped,
        "privacy_boundary": {
            "raw_registry_paths_emitted": False,
            "raw_clean_source_paths_emitted": False,
            "redacted_prompts_skipped_by_default": not include_redacted_prompts,
            "source_subset_sanitized": True,
        },
        "note": "Generated cases are private calibration artifacts; do not commit real trace exports.",
    }


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
    clean_source_messages: Path | str | None = None,
    clean_source_dir: Path | str | None = None,
    dataset_id: str | None = None,
    limit: int = 50,
    per_thread: int = 5,
    trace_window: int = 6,
    min_prompt_chars: int = 8,
    include_redacted_prompts: bool = False,
    label_template: bool = False,
) -> dict[str, Any]:
    messages_path = resolve_clean_source_messages_path(
        clean_source_messages=clean_source_messages,
        clean_source_dir=clean_source_dir,
    )
    if messages_path is not None:
        return build_cases_from_clean_source_messages(
            messages_path,
            dataset_id=dataset_id,
            limit=limit,
            per_thread=per_thread,
            trace_window=trace_window,
            min_prompt_chars=min_prompt_chars,
            include_redacted_prompts=include_redacted_prompts,
            label_template=label_template,
        )

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
        "source_mode": "registry",
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


def write_clean_source_case_pack(
    payload: dict[str, Any],
    *,
    messages_path: Path | str,
    registry_path: Path | str,
) -> dict[str, Path]:
    subset = payload.get("source_subset") if isinstance(payload, dict) else None
    if not isinstance(subset, dict):
        raise ValueError("payload does not include a source_subset; build from clean-source messages first")
    thread_key = str(subset.get("thread_key") or "")
    messages = subset.get("messages") or []
    if not thread_key:
        raise ValueError("source_subset.thread_key is required")
    if not isinstance(messages, list):
        raise ValueError("source_subset.messages must be a list")

    messages_target = Path(messages_path)
    registry_target = Path(registry_path)
    messages_target.parent.mkdir(parents=True, exist_ok=True)
    registry_target.parent.mkdir(parents=True, exist_ok=True)
    messages_target.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in messages) + ("\n" if messages else ""),
        encoding="utf-8",
    )
    registry_target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": thread_key,
                        "title": "Warm ambient benchmark case pack",
                        "paths": {"clean_source_messages_jsonl": str(messages_target)},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"messages_path": messages_target, "registry_path": registry_target}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--clean-source-messages")
    parser.add_argument("--clean-source-dir")
    parser.add_argument("--dataset-id")
    parser.add_argument("--out", required=True)
    parser.add_argument("--jsonl", action="store_true")
    parser.add_argument("--subset-messages-out")
    parser.add_argument("--registry-out")
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
        clean_source_messages=args.clean_source_messages,
        clean_source_dir=args.clean_source_dir,
        dataset_id=args.dataset_id,
        limit=args.limit,
        per_thread=args.per_thread,
        trace_window=args.trace_window,
        min_prompt_chars=args.min_prompt_chars,
        include_redacted_prompts=args.include_redacted_prompts,
        label_template=args.label_template,
    )
    output = write_cases_file(payload["cases"], args.out, jsonl=args.jsonl)
    pack_outputs: dict[str, Path] = {}
    if args.subset_messages_out or args.registry_out:
        if not args.subset_messages_out or not args.registry_out:
            parser.error("--subset-messages-out and --registry-out must be used together")
        pack_outputs = write_clean_source_case_pack(
            payload,
            messages_path=args.subset_messages_out,
            registry_path=args.registry_out,
        )
    summary = {
        "kind": payload["kind"],
        "schema_version": payload["schema_version"],
        "source_mode": payload.get("source_mode"),
        "case_count": payload["case_count"],
        "label_template": payload["label_template"],
        "skipped": payload["skipped"],
        "output": str(output),
        "source_subset_message_count": (payload.get("source_subset") or {}).get("message_count"),
        "subset_messages_output": str(pack_outputs["messages_path"]) if pack_outputs else None,
        "registry_output": str(pack_outputs["registry_path"]) if pack_outputs else None,
        "privacy_boundary": payload["privacy_boundary"],
    }
    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"warm ambient trace cases: cases={payload['case_count']} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
