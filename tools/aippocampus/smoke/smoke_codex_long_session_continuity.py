#!/usr/bin/env python3
"""Real Codex long-session continuity smoke for compaction and corrections.

This is intentionally a slow/live smoke. It drives the real Codex app-server,
creates a disposable non-ephemeral thread, runs a synthetic correction scenario
for many turns, forces a real host compaction, and then verifies that a later
reply and rebuilt clean source preserve the corrected state.

The public JSON output is sanitized by design: it reports hashes, counts, hook
event names, and booleans, but never raw prompts, rollout paths, local paths,
credentials, or private memory text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

# Reuse the existing real Codex app-server protocol client. Keeping both live
# Codex smokes on one client avoids two subtly different stdio JSON contracts.
PLUGIN_SMOKE_DIR = _paths.REPO_ROOT / "plugins" / "aippocampus"
if str(PLUGIN_SMOKE_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SMOKE_DIR))

import build_clean_source  # noqa: E402
import smoke_real_codex_host as codex_host  # noqa: E402

KIND = "aippocampus_real_codex_long_session_continuity_smoke"
SCHEMA_VERSION = 1
STATUS_PASSED = "passed"
STATUS_SKIPPED = "skipped_host_unavailable"
STATUS_FAILED = "failed"
DEFAULT_TURN_COUNT = 50
POLL_INTERVAL_SECONDS = 2.0

LOCAL_PATH_RE = re.compile(r"(?i)([a-z]:\\[^\n\r\t]+|\\\\[^\\\n\r\t]+\\[^\\\n\r\t]+)")
SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._-]{8,}|api[_-]?key\s*[:=]\s*\S+|"
    r"token\s*[:=]\s*\S+|AGE-SECRET-KEY-[A-Z0-9-]+|sk-[a-z0-9_-]{20,})"
)


class SmokeFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def sanitize_error_message(value: object, *, max_chars: int = 500) -> str:
    text = str(value)
    text = LOCAL_PATH_RE.sub("[local_path]", text)
    text = SECRET_VALUE_RE.sub("[secret]", text)
    return text[:max_chars]


def issue(code: str, message: object) -> dict[str, str]:
    return {"code": code, "message": sanitize_error_message(message)}


def error_message(container: dict[str, Any], default: str) -> str:
    error = container.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        return str(message) if message is not None else default
    if error is not None:
        return str(error)
    return default


def sensitive_string_issues(value: Any, path: str = "$") -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, str):
        if LOCAL_PATH_RE.search(value):
            found.append(issue("local_path_in_public_payload", path))
        if SECRET_VALUE_RE.search(value):
            found.append(issue("secret_like_value_in_public_payload", path))
        return found
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(sensitive_string_issues(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            found.extend(sensitive_string_issues(item, f"{path}[{idx}]"))
    return found


def result_skeleton(run_id: str, target_turn_count: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": STATUS_FAILED,
        "ok": False,
        "run_id_sha1": sha1_text(run_id)[:16],
        "codex_user_agent": None,
        "host": {
            "available": False,
            "experimental_api_requested": True,
            "thread_started": False,
            "thread_id_sha1": None,
        },
        "scenario": {
            "target_pre_compact_turn_count": target_turn_count,
            "completed_pre_compact_turn_count": 0,
            "completed_total_turn_count": 0,
            "correction_event_observed": False,
            "compaction_observed": False,
            "recall_turn_completed": False,
            "clean_source_verified": False,
        },
        "evidence": {
            "turn_count": {
                "pre_compact_completed": 0,
                "total_completed": 0,
            },
            "compaction_boundary": {
                "method": "thread/compact/start",
                "compact_turn_completed": False,
                "context_compaction_item_observed": False,
                "pre_compact_hook_completed": False,
                "post_compact_hook_completed": False,
                "hook_events_observed": [],
            },
            "correction_survival": {},
            "clean_source": {},
        },
        "privacy_boundary": {
            "contains_raw_prompt_text": False,
            "contains_raw_rollout_text": False,
            "contains_rollout_path": False,
            "contains_local_path": False,
            "contains_credentials": False,
            "public_payload_sensitive_string_count": 0,
        },
        "failures": [],
        "cannot_claim": [
            "private_real_history_compaction_survival",
            "live_semantic_adjudication_quality",
            "interactive_desktop_ui_behavior",
            "all_codex_client_surfaces",
        ],
    }


def synthetic_tokens(run_id: str) -> tuple[str, str]:
    digest = sha1_text(run_id).upper()
    return f"LIVEOLD{digest[:8]}", f"LIVEFIX{digest[8:16]}"


def safe_run_id_segment(run_id: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_id).strip(".-")
    return (segment or "run")[:80]


def setup_prompt(obsolete_token: str) -> str:
    return (
        "AIppocampus live continuity smoke. This is synthetic public-safe test text. "
        f"Initial temporary route code: {obsolete_token}. Reply exactly ACK-SETUP."
    )


def correction_prompt(obsolete_token: str, corrected_token: str) -> str:
    return (
        "Correction for this smoke: the previous route code "
        f"{obsolete_token} is stale and must not be used. The current route code is "
        f"{corrected_token}. Reply exactly ACK-CORRECTED."
    )


def filler_prompt(index: int, corrected_token: str) -> str:
    return (
        f"Smoke filler turn {index}. Keep the current route code as {corrected_token}. "
        f"Reply exactly ACK-{index}."
    )


def recall_prompt() -> str:
    return (
        "After the correction and compaction, what is the current route code? "
        "Answer only the current route code."
    )


def input_text(text: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": text}]


def thread_turns(
    client: codex_host.CodexAppServerClient, thread_id: str, *, limit: int = 200
) -> list[dict[str, Any]]:
    response = client.request(
        "thread/turns/list",
        {"threadId": thread_id, "limit": limit},
        timeout=30,
        raise_on_error=False,
    )
    if response.get("error"):
        raise SmokeFailure("turns_list_failed", error_message(response, "turns/list failed"))
    result = response.get("result") or {}
    return [turn for turn in result.get("data") or [] if isinstance(turn, dict)]


def is_transient_turn_history_error(exc: SmokeFailure) -> bool:
    text = exc.message.casefold()
    return exc.code == "turns_list_failed" and (
        "rollout" in text and "empty" in text or "failed to load thread history" in text
    )


def thread_turns_with_retry(
    client: codex_host.CodexAppServerClient,
    thread_id: str,
    *,
    timeout: float = 60.0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_error: SmokeFailure | None = None
    while time.monotonic() < deadline:
        try:
            return thread_turns(client, thread_id, limit=limit)
        except SmokeFailure as exc:
            if not is_transient_turn_history_error(exc):
                raise
            last_error = exc
            time.sleep(POLL_INTERVAL_SECONDS)
    if last_error is not None:
        raise last_error
    return thread_turns(client, thread_id, limit=limit)


def completed_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [turn for turn in turns if turn.get("status") == "completed"]


def find_turn(turns: list[dict[str, Any]], turn_id: str) -> dict[str, Any] | None:
    return next((turn for turn in turns if turn.get("id") == turn_id), None)


def assistant_final_text(turn: dict[str, Any] | None) -> str:
    if not turn:
        return ""
    items = turn.get("items") or []
    for item in reversed(items):
        if item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
            return str(item.get("text") or "")
    return ""


def user_texts(turn: dict[str, Any] | None) -> list[str]:
    if not turn:
        return []
    texts: list[str] = []
    for item in turn.get("items") or []:
        if item.get("type") != "userMessage":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "text":
                texts.append(str(content.get("text") or ""))
    return texts


def wait_for_turn(
    client: codex_host.CodexAppServerClient,
    thread_id: str,
    turn_id: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_status = "not_found"
    while time.monotonic() < deadline:
        turn = find_turn(thread_turns_with_retry(client, thread_id), turn_id)
        if turn:
            last_status = str(turn.get("status") or "unknown")
            if last_status == "completed":
                return turn
            if last_status == "failed":
                raise SmokeFailure("turn_failed", error_message(turn, "turn failed"))
        time.sleep(POLL_INTERVAL_SECONDS)
    raise SmokeFailure("turn_timeout", f"turn {turn_id} did not complete; last={last_status}")


def run_turn(
    client: codex_host.CodexAppServerClient,
    thread_id: str,
    prompt: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    response = client.request(
        "turn/start",
        {"threadId": thread_id, "input": input_text(prompt)},
        timeout=30,
        raise_on_error=False,
    )
    if response.get("error"):
        raise SmokeFailure("turn_start_failed", error_message(response, "turn/start failed"))
    turn = (response.get("result") or {}).get("turn") or {}
    turn_id = str(turn.get("id") or "")
    if not turn_id:
        raise SmokeFailure("turn_start_missing_id", "turn/start did not return a turn id")
    return wait_for_turn(client, thread_id, turn_id, timeout=timeout)


def compact_notification_evidence(notifications: list[dict[str, Any]]) -> dict[str, Any]:
    hook_events: list[str] = []
    context_compaction_seen = False
    pre_completed = False
    post_completed = False
    for notification in notifications:
        method = str(notification.get("method") or "")
        params = notification.get("params") or {}
        if method in {"hook/started", "hook/completed"}:
            run = params.get("run") or {}
            event = str(run.get("eventName") or "")
            status = str(run.get("status") or "")
            if event:
                hook_events.append(event)
            if method == "hook/completed" and event == "preCompact" and status == "completed":
                pre_completed = True
            if method == "hook/completed" and event == "postCompact" and status == "completed":
                post_completed = True
        if method in {"item/started", "item/completed"}:
            item = params.get("item") or {}
            if item.get("type") == "contextCompaction":
                context_compaction_seen = True
    return {
        "context_compaction_item_observed": context_compaction_seen,
        "pre_compact_hook_completed": pre_completed,
        "post_compact_hook_completed": post_completed,
        "hook_events_observed": sorted(set(hook_events)),
    }


def run_compaction(
    client: codex_host.CodexAppServerClient,
    thread_id: str,
    *,
    before_turn_ids: set[str],
    notification_start: int,
    timeout: float,
) -> dict[str, Any]:
    response = client.request(
        "thread/compact/start",
        {"threadId": thread_id},
        timeout=30,
        raise_on_error=False,
    )
    if response.get("error"):
        raise SmokeFailure("compact_start_failed", error_message(response, "compact/start failed"))

    deadline = time.monotonic() + timeout
    compact_turn: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        turns = thread_turns_with_retry(client, thread_id)
        new_turns = [turn for turn in turns if str(turn.get("id") or "") not in before_turn_ids]
        if new_turns:
            compact_turn = new_turns[0]
            if compact_turn.get("status") == "completed":
                break
            if compact_turn.get("status") == "failed":
                raise SmokeFailure(
                    "compact_turn_failed",
                    error_message(compact_turn, "compact turn failed"),
                )
        time.sleep(POLL_INTERVAL_SECONDS)
    if not compact_turn or compact_turn.get("status") != "completed":
        raise SmokeFailure("compact_timeout", "context compaction did not complete")

    notifications = client.notifications[notification_start:]
    evidence = compact_notification_evidence(notifications)
    evidence.update(
        {
            "compact_turn_completed": True,
            "compact_turn_id_sha1": sha1_text(str(compact_turn.get("id") or ""))[:16],
        }
    )
    return evidence


def correction_survival_evidence(
    recall_text: str, corrected_token: str, obsolete_token: str
) -> dict[str, Any]:
    normalized = recall_text.casefold()
    corrected = corrected_token.casefold()
    obsolete = obsolete_token.casefold()
    return {
        "corrected_token_sha1": sha1_text(corrected_token)[:16],
        "obsolete_token_sha1": sha1_text(obsolete_token)[:16],
        "recall_answer_sha1": sha1_text(recall_text)[:16] if recall_text else None,
        "assistant_recalled_corrected_token": corrected in normalized,
        "assistant_avoided_obsolete_token": obsolete not in normalized,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def clean_source_evidence(
    manifest: dict[str, Any],
    *,
    corrected_token: str,
    obsolete_token: str,
    target_pre_compact_turns: int,
) -> dict[str, Any]:
    outputs = manifest.get("outputs") or {}
    messages = load_jsonl(Path(str(outputs.get("messages_jsonl") or "")))
    turns = load_jsonl(Path(str(outputs.get("turns_jsonl") or "")))
    corrected = corrected_token.casefold()
    obsolete = obsolete_token.casefold()
    correction_found = False
    recall_found = False
    stale_recall_found = False
    for message in messages:
        text = str(message.get("text") or "")
        lowered = text.casefold()
        if message.get("role") == "user" and corrected in lowered and obsolete in lowered:
            correction_found = True
        if message.get("role") == "assistant" and corrected in lowered:
            recall_found = True
            if obsolete in lowered:
                stale_recall_found = True
    return {
        "built_from_real_rollout": True,
        "message_count": int(manifest.get("message_count") or len(messages)),
        "turn_count": int(manifest.get("turn_count") or len(turns)),
        "target_pre_compact_turn_count": target_pre_compact_turns,
        "correction_message_found": correction_found,
        "recall_answer_found": recall_found,
        "stale_recall_answer_found": stale_recall_found,
    }


def find_rollout_by_thread_id(codex_home: Path, thread_id: str) -> Path:
    for dirname in ("sessions", "archived_sessions"):
        root = codex_home / dirname
        if not root.exists():
            continue
        matches = sorted(root.rglob(f"rollout-*{thread_id}.jsonl"), key=lambda path: path.stat().st_mtime)
        if matches:
            return matches[-1]
    raise SmokeFailure("rollout_not_found", "could not locate the real Codex rollout")


def safe_remove_tree(root: Path, target: Path) -> bool:
    if not target.exists():
        return False
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        raise SmokeFailure("unsafe_cleanup_path", "refusing to remove outside repo temp root")
    shutil.rmtree(target)
    return True


def validate_report(report: dict[str, Any]) -> tuple[bool, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    scenario = report.get("scenario") or {}
    evidence = report.get("evidence") or {}
    compaction = evidence.get("compaction_boundary") or {}
    correction = evidence.get("correction_survival") or {}
    clean_source = evidence.get("clean_source") or {}
    target = int(scenario.get("target_pre_compact_turn_count") or 0)
    pre_count = int(scenario.get("completed_pre_compact_turn_count") or 0)
    if pre_count < target:
        failures.append(issue("turn_count_below_target", f"{pre_count} < {target}"))
    for key in (
        "compact_turn_completed",
        "context_compaction_item_observed",
        "pre_compact_hook_completed",
        "post_compact_hook_completed",
    ):
        if compaction.get(key) is not True:
            failures.append(issue("compaction_boundary_not_verified", key))
    if correction.get("assistant_recalled_corrected_token") is not True:
        failures.append(issue("corrected_state_not_recalled", "assistant answer missed corrected token"))
    if correction.get("assistant_avoided_obsolete_token") is not True:
        failures.append(issue("obsolete_state_recalled", "assistant answer included obsolete token"))
    for key in ("built_from_real_rollout", "correction_message_found", "recall_answer_found"):
        if clean_source.get(key) is not True:
            failures.append(issue("clean_source_not_verified", key))
    if clean_source.get("stale_recall_answer_found"):
        failures.append(issue("clean_source_contains_stale_recall", "obsolete token found in recall answer"))
    payload_issues = sensitive_string_issues(report)
    if payload_issues:
        failures.append(issue("public_payload_not_sanitized", len(payload_issues)))
    return not failures, failures


def classify_unavailable(exc: BaseException, *, thread_started: bool) -> bool:
    if thread_started:
        return False
    text = str(exc).casefold()
    return any(
        needle in text
        for needle in (
            "could not find codex",
            "codex app-server exited",
            "closed stdout",
            "timed out waiting for initialize",
            "not logged in",
            "auth",
            "rate limit",
        )
    )


def run_real_long_session_smoke(
    repo_root: str | Path,
    *,
    codex_command: str | None = None,
    target_turn_count: int = DEFAULT_TURN_COUNT,
    run_id: str | None = None,
    turn_timeout: float = 180.0,
    compact_timeout: float = 240.0,
    keep_artifacts: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    target_turn_count = max(2, int(target_turn_count))
    run_id = run_id or uuid.uuid4().hex[:10]
    obsolete_token, corrected_token = synthetic_tokens(run_id)
    result = result_skeleton(run_id, target_turn_count)
    client: codex_host.CodexAppServerClient | None = None
    thread_id: str | None = None
    codex_home: Path | None = None
    archived = False
    temp_root = repo_root / ".tmp" / f"aippocampus-live-continuity-{safe_run_id_segment(run_id)}"

    try:
        codex = codex_host.resolve_codex_command(codex_command)
        client = codex_host.CodexAppServerClient(
            [*codex, "app-server", "--listen", "stdio://"],
            repo_root,
        )
        init = client.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "aippocampus-long-session-continuity-smoke",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
            timeout=90,
        )
        init_result = init.get("result") or {}
        result["host"]["available"] = True
        result["codex_user_agent"] = init_result.get("userAgent")
        if init_result.get("codexHome"):
            codex_home = Path(str(init_result["codexHome"]))

        thread = client.request(
            "thread/start",
            {
                "cwd": str(repo_root),
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
                "ephemeral": False,
                "threadSource": "user",
                "sessionStartSource": "startup",
            },
            timeout=120,
        )
        thread_obj = ((thread.get("result") or {}).get("thread") or {})
        thread_id = str(thread_obj.get("id") or "")
        if not thread_id:
            raise SmokeFailure("thread_start_missing_id", "thread/start did not return an id")
        result["host"]["thread_started"] = True
        result["host"]["thread_id_sha1"] = sha1_text(thread_id)[:16]

        run_turn(client, thread_id, setup_prompt(obsolete_token), timeout=turn_timeout)
        correction_turn = run_turn(
            client,
            thread_id,
            correction_prompt(obsolete_token, corrected_token),
            timeout=turn_timeout,
        )
        correction_observed = any(
            corrected_token in text and obsolete_token in text for text in user_texts(correction_turn)
        )
        result["scenario"]["correction_event_observed"] = correction_observed

        for index in range(2, target_turn_count):
            run_turn(
                client,
                thread_id,
                filler_prompt(index, corrected_token),
                timeout=turn_timeout,
            )

        before_compact_turns = thread_turns_with_retry(client, thread_id)
        before_ids = {str(turn.get("id") or "") for turn in before_compact_turns}
        pre_completed = len(completed_turns(before_compact_turns))
        result["scenario"]["completed_pre_compact_turn_count"] = pre_completed
        result["evidence"]["turn_count"]["pre_compact_completed"] = pre_completed

        notification_start = len(client.notifications)
        compaction_evidence = run_compaction(
            client,
            thread_id,
            before_turn_ids=before_ids,
            notification_start=notification_start,
            timeout=compact_timeout,
        )
        result["evidence"]["compaction_boundary"].update(compaction_evidence)
        result["scenario"]["compaction_observed"] = all(
            bool(compaction_evidence.get(key))
            for key in (
                "compact_turn_completed",
                "context_compaction_item_observed",
                "pre_compact_hook_completed",
                "post_compact_hook_completed",
            )
        )

        recall_turn = run_turn(client, thread_id, recall_prompt(), timeout=turn_timeout)
        result["scenario"]["recall_turn_completed"] = True
        recall_text = assistant_final_text(recall_turn)
        result["evidence"]["correction_survival"] = correction_survival_evidence(
            recall_text,
            corrected_token,
            obsolete_token,
        )

        all_turns = thread_turns_with_retry(client, thread_id)
        total_completed = len(completed_turns(all_turns))
        result["scenario"]["completed_total_turn_count"] = total_completed
        result["evidence"]["turn_count"]["total_completed"] = total_completed

        archive = client.request(
            "thread/archive",
            {"threadId": thread_id},
            timeout=60,
            raise_on_error=False,
        )
        archived = "result" in archive and not archive.get("error")
        if not archived:
            raise SmokeFailure(
                "thread_archive_failed",
                error_message(archive, "thread/archive failed"),
            )
        if codex_home is None:
            raise SmokeFailure("codex_home_missing", "initialize did not report codexHome")
        rollout = find_rollout_by_thread_id(codex_home, thread_id)
        clean_manifest = build_clean_source.build_clean_source(
            repo_root,
            rollout=rollout,
            output_dir=temp_root / "clean-source",
        )
        clean_evidence = clean_source_evidence(
            clean_manifest,
            corrected_token=corrected_token,
            obsolete_token=obsolete_token,
            target_pre_compact_turns=target_turn_count,
        )
        result["evidence"]["clean_source"] = clean_evidence
        result["scenario"]["clean_source_verified"] = all(
            clean_evidence.get(key) is True
            for key in ("built_from_real_rollout", "correction_message_found", "recall_answer_found")
        ) and not clean_evidence.get("stale_recall_answer_found")

        ok, validation_failures = validate_report(result)
        result["failures"] = validation_failures
        result["status"] = STATUS_PASSED if ok else STATUS_FAILED
        result["ok"] = ok
        return result
    except BaseException as exc:
        if isinstance(exc, SmokeFailure):
            failure = issue(exc.code, exc.message)
        else:
            failure = issue(type(exc).__name__, exc)
        result["failures"] = [failure]
        skipped = classify_unavailable(exc, thread_started=bool(thread_id))
        result["status"] = STATUS_SKIPPED if skipped else STATUS_FAILED
        result["ok"] = False
        return result
    finally:
        if client is not None:
            try:
                if thread_id and not archived:
                    client.request(
                        "thread/archive",
                        {"threadId": thread_id},
                        timeout=30,
                        raise_on_error=False,
                    )
            finally:
                client.close()
        if not keep_artifacts:
            safe_remove_tree(repo_root / ".tmp", temp_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(_paths.REPO_ROOT))
    parser.add_argument("--codex-command")
    parser.add_argument("--run-id")
    parser.add_argument("--turn-count", type=int, default=DEFAULT_TURN_COUNT)
    parser.add_argument("--turn-timeout", type=float, default=180.0)
    parser.add_argument("--compact-timeout", type=float, default=240.0)
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_real_long_session_smoke(
        args.repo_root,
        codex_command=args.codex_command,
        target_turn_count=args.turn_count,
        run_id=args.run_id,
        turn_timeout=args.turn_timeout,
        compact_timeout=args.compact_timeout,
        keep_artifacts=args.keep_artifacts,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    if args.json_output:
        print(payload)
    else:
        print(f"real Codex long-session continuity smoke: {result['status']}")
        print(
            "turns: "
            f"{result['scenario']['completed_pre_compact_turn_count']} pre-compact / "
            f"{result['scenario']['completed_total_turn_count']} total"
        )
        for failure in result.get("failures") or []:
            print(f"- {failure.get('code')}: {failure.get('message')}")
    if result["status"] == STATUS_PASSED:
        return 0
    if result["status"] == STATUS_SKIPPED:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
