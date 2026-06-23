"""Source-chain prerequisite helpers for recall integration readiness."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol


class SourceCliJsonRunner(Protocol):
    def __call__(
        self,
        repo_root: Path,
        args: list[str],
        *,
        timeout: float = 30,
        stdin: str | None = None,
    ) -> dict[str, Any]: ...


def _messages_path_from_registry_entry(entry: Mapping[str, Any]) -> Path:
    paths = entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {}
    explicit = str(paths.get("clean_source_messages_jsonl") or "").strip()
    if explicit:
        return Path(explicit)
    clean_dir = str(paths.get("clean_source_dir") or "").strip()
    return Path(clean_dir) / "messages.jsonl" if clean_dir else Path("")


def _message_id_exists(messages_path: Path, message_id: str) -> bool:
    if not messages_path.exists():
        return False
    with messages_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, Mapping):
                continue
            if str(row.get("message_id") or row.get("id") or "") == message_id:
                return True
    return False


def expected_source_ref_prerequisite(
    repo_root: Path,
    expected_source_refs: Iterable[Mapping[str, Any]],
    *,
    run_source_cli_json: SourceCliJsonRunner,
) -> dict[str, Any]:
    """Check that private dogfood refs exist before a strict live probe runs.

    The readiness suite may name maintainer-local sources. Missing prerequisites
    should skip the private dogfood probe, not masquerade as recall/deepen
    opening the wrong source.
    """

    refs = [dict(ref) for ref in expected_source_refs if isinstance(ref, Mapping)]
    missing: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for ref in refs:
        thread_key = str(ref.get("thread_key") or "").strip()
        message_id = str(ref.get("message_id") or "").strip()
        if not thread_key:
            checked.append({"status": "no_thread_key_declared", "message_id": bool(message_id)})
            continue
        entry = run_source_cli_json(
            repo_root,
            ["registry", "show", thread_key, "--json"],
            timeout=20,
        )
        if entry.get("returncode") != 0 or entry.get("error"):
            missing.append(
                {
                    "thread_key": thread_key,
                    "message_id": message_id or None,
                    "reason": "expected_thread_missing",
                }
            )
            continue
        if not message_id:
            checked.append({"thread_key": thread_key, "status": "thread_present"})
            continue
        try:
            found = _message_id_exists(_messages_path_from_registry_entry(entry), message_id)
        except OSError:
            missing.append(
                {
                    "thread_key": thread_key,
                    "message_id": message_id,
                    "reason": "expected_source_unreadable",
                }
            )
            continue
        if found:
            checked.append({"thread_key": thread_key, "message_id": message_id, "status": "present"})
        else:
            missing.append(
                {
                    "thread_key": thread_key,
                    "message_id": message_id,
                    "reason": "expected_message_missing",
                }
            )
    status = "present" if not missing else "expected_source_missing"
    return {
        "status": status,
        "present": not missing,
        "checked_count": len(refs),
        "missing_count": len(missing),
        "missing": missing,
        "checked": checked,
        "repair_hint": (
            "Register or import the expected source bundle before running the strict live "
            "source-chain identity probe."
            if missing
            else None
        ),
        "privacy": {
            "local_paths_serialized": False,
            "raw_source_text_serialized": False,
        },
    }


def prerequisite_absent_probe(
    *,
    probe_label: str,
    cue: str,
    anchors: list[str],
    expected_refs: list[dict[str, Any]],
    prerequisite: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "aippocampus_source_chain_identity_probe",
        "probe_label": probe_label,
        "cue": cue,
        "status": "prerequisite_absent",
        "ok": True,
        "failures": [],
        "prerequisite": dict(prerequisite),
        "commands": {
            "registry_prerequisite": "aippocampus registry show <expected-thread-key> --json",
            "cli_recall": "",
            "cli_deepen": "",
            "mcp_agent_recall_arguments": {},
            "mcp_agent_deepen_arguments": {},
        },
        "expected_source_refs": expected_refs,
        "anchors": anchors,
        "cli": {"status": "skipped_expected_source_missing"},
        "mcp": {"status": "skipped_expected_source_missing"},
        "claim_boundary": (
            "live private source-chain probe skipped because the expected source is absent; "
            "this is not source evidence and does not prove useful recall"
        ),
    }
