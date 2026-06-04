#!/usr/bin/env python3
"""Single-machine cross-device sync smoke for AIppocampus Stage 3.

This smoke models two device registries and several OS-shaped source locators
on one machine. It is stronger than a simple two-folder copy because it checks
the device-boundary contract: push must remove or rewrite source-device
absolute locators, pull must repair generated-artifact locators to the target
registry, conflicts must be preserved, and raw rollout transfer must stay
explicit.

It does not prove a physical second machine, a real cloud folder client, or a
different kernel/filesystem runtime. Keep that boundary visible in docs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.sync import bundle as sync_bundle

THREAD_KEY = "session:cross-device-smoke"
THREAD_DIR = sync_bundle.thread_dir_name(THREAD_KEY)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def fake_windows_workspace() -> str:
    return "C:" + "\\Users\\Source Device\\AIppocampus"


def fake_posix_workspace() -> str:
    return "/" + "home/source-device/AIppocampus"


def create_device_registry(
    device_root: Path,
    *,
    device_name: str,
    workspace_locator: str,
    message_text: str,
) -> dict[str, Any]:
    registry = device_root / "registry"
    thread_store = registry / "threads" / THREAD_DIR
    clean_source = thread_store / "clean-source"
    index_dir = thread_store / "index"
    raw_rollout = device_root / "raw" / "rollout.jsonl"

    write_json(
        clean_source / "manifest.json", {"kind": "aippocampus_clean_source", "device": device_name}
    )
    write_jsonl(
        clean_source / "messages.jsonl",
        [
            {
                "message_id": "msg_cross_001",
                "turn_id": "turn_cross_001",
                "source_id": "src_cross_device",
                "role": "user",
                "text": message_text,
            }
        ],
    )
    write_jsonl(
        clean_source / "turns.jsonl",
        [{"turn_id": "turn_cross_001", "message_ids": ["msg_cross_001"]}],
    )
    write_jsonl(
        clean_source / "semantic-scope-labels.jsonl",
        [
            {
                "message_id": "msg_cross_001",
                "source": "deepseek_subconscious_scope_labels",
                "scope_labels": ["idea_seed"],
            }
        ],
    )
    write_json(index_dir / "manifest.json", {"kind": "aippocampus_index", "device": device_name})
    write_json(index_dir / "graph.json", {"nodes": [], "edges": []})
    raw_rollout.parent.mkdir(parents=True, exist_ok=True)
    raw_rollout.write_text("raw private rollout\n", encoding="utf-8")

    stale_other_os = (
        fake_posix_workspace() if "\\" in workspace_locator else fake_windows_workspace()
    )
    write_json(
        registry / "threads.json",
        {
            "threads": [
                {
                    "thread_key": THREAD_KEY,
                    "project_label": f"Cross-device smoke {device_name}",
                    "paths": {
                        "workspace": workspace_locator,
                        "registry_thread_store": f"{stale_other_os}/registry/threads/{THREAD_DIR}",
                        "clean_source_dir": f"{stale_other_os}/clean-source",
                        "clean_source_messages_jsonl": f"{stale_other_os}/clean-source/messages.jsonl",
                        "clean_source_turns_jsonl": f"{stale_other_os}/clean-source/turns.jsonl",
                        "index_dir": f"{stale_other_os}/index",
                        "graph_json": f"{stale_other_os}/index/graph.json",
                        "messages_jsonl": f"{stale_other_os}/index/messages.jsonl",
                        "sqlite": f"{stale_other_os}/index/source_index.sqlite",
                        "rollout": str(raw_rollout),
                    },
                }
            ]
        },
    )
    write_jsonl(registry / "semantic_triggers.jsonl", [{"trigger": "cross-device-smoke"}])
    write_jsonl(registry / "working_memory.jsonl", [{"memory_id": f"wm_{device_name}"}])
    write_json(registry / "cognitive_map.json", {"routes": []})
    return {
        "registry": registry,
        "thread_store": thread_store,
        "clean_source": clean_source,
        "index_dir": index_dir,
        "raw_rollout": raw_rollout,
        "workspace_locator": workspace_locator,
        "stale_other_os_locator": stale_other_os,
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def require(condition: bool, code: str, failures: list[dict[str, str]], detail: str = "") -> None:
    if not condition:
        failures.append({"code": code, "detail": detail})


def same_resolved_path(value: Any, expected: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return Path(value).resolve() == expected.resolve()


def locator_values(registry: dict[str, Any]) -> dict[str, Any]:
    threads = registry.get("threads") or []
    if not threads:
        return {}
    return dict((threads[0].get("paths") or {}))


def validate_portable_registry(
    registry: dict[str, Any],
    *,
    source_markers: list[str],
    failures: list[dict[str, str]],
) -> None:
    text = json_text(registry)
    for marker in source_markers:
        require(marker not in text, "source_locator_leak", failures, marker)
    paths = locator_values(registry)
    require(paths.get("workspace") is None, "workspace_not_cleared", failures)
    require(paths.get("rollout") is None, "raw_rollout_not_excluded", failures)
    for key in (
        "registry_thread_store",
        "clean_source_dir",
        "clean_source_messages_jsonl",
        "clean_source_turns_jsonl",
        "index_dir",
        "graph_json",
    ):
        value = paths.get(key)
        require(
            isinstance(value, str) and value.startswith("registry/"),
            "non_portable_locator",
            failures,
            key,
        )
        require("\\" not in str(value), "portable_locator_uses_backslash", failures, key)
    require(registry.get("sync_portable_paths") is True, "missing_sync_portable_marker", failures)


def validate_target_registry(
    registry: dict[str, Any],
    *,
    target_registry: Path,
    source_markers: list[str],
    failures: list[dict[str, str]],
) -> None:
    text = json_text(registry)
    for marker in source_markers:
        require(marker not in text, "source_locator_leak_after_pull", failures, marker)
    paths = locator_values(registry)
    expected_root = target_registry / "threads" / THREAD_DIR
    require(
        same_resolved_path(paths.get("registry_thread_store"), expected_root),
        "target_thread_store_not_repaired",
        failures,
    )
    require(
        same_resolved_path(
            paths.get("clean_source_messages_jsonl"),
            expected_root / "clean-source" / "messages.jsonl",
        ),
        "target_messages_not_repaired",
        failures,
    )
    require(
        same_resolved_path(paths.get("graph_json"), expected_root / "index" / "graph.json"),
        "target_graph_not_repaired",
        failures,
    )
    require(paths.get("workspace") is None, "target_workspace_not_unresolved", failures)


def run_cross_device_sync_smoke(
    repo_root: str | Path,
    *,
    keep_artifacts: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    run_id = run_id or uuid.uuid4().hex[:10]
    temp_context = None
    if keep_artifacts:
        root = repo_root / ".tmp" / f"aippocampus-cross-device-sync-{run_id}"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="aippocampus-cross-device-sync-")
        root = Path(temp_context.name)

    failures: list[dict[str, str]] = []
    result: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "artifact_root": str(root),
        "kept_artifacts": keep_artifacts,
        "claims": {
            "single_machine_dual_device_model": True,
            "cross_os_path_shape_model": True,
            "physical_second_machine": False,
            "real_cloud_backend": False,
        },
        "steps": {},
        "failures": failures,
    }

    try:
        device_a = create_device_registry(
            root / "device-a",
            device_name="device-a",
            workspace_locator=fake_windows_workspace(),
            message_text="Device A original clean-source memory.",
        )
        device_b_root = root / "device-b"
        sync_dir = root / "shared-sync-folder"

        push_a = sync_bundle.push_sync_bundle(device_a["registry"], sync_dir)
        status_a = sync_bundle.status_sync_bundle(sync_dir)
        portable_registry = read_json(sync_dir / "registry" / "threads.json")
        source_markers = [
            str(device_a["registry"]),
            str(device_a["raw_rollout"]),
            fake_windows_workspace(),
            fake_posix_workspace(),
        ]
        validate_portable_registry(
            portable_registry, source_markers=source_markers, failures=failures
        )

        target_b = device_b_root / "registry"
        pull_b = sync_bundle.pull_sync_bundle(sync_dir, target_b)
        target_registry = read_json(target_b / "threads.json")
        validate_target_registry(
            target_registry,
            target_registry=target_b,
            source_markers=source_markers,
            failures=failures,
        )
        require(
            (
                target_b / "threads" / THREAD_DIR / "clean-source" / "semantic-scope-labels.jsonl"
            ).is_file(),
            "missing_semantic_sidecar_after_pull",
            failures,
        )
        require(
            not (target_b / "raw-rollouts").exists(), "raw_rollout_synced_without_opt_in", failures
        )

        b_messages = target_b / "threads" / THREAD_DIR / "clean-source" / "messages.jsonl"
        b_messages.write_text(
            json.dumps(
                {
                    "message_id": "msg_cross_001",
                    "turn_id": "turn_cross_001",
                    "source_id": "src_cross_device",
                    "role": "user",
                    "text": "Device B local edit that must not be overwritten.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        conflict_pull_b = sync_bundle.pull_sync_bundle(sync_dir, target_b)
        conflict_files_b = list((target_b / ".sync-conflicts").rglob("messages.jsonl"))
        require(
            conflict_pull_b.get("conflicts", 0) >= 1,
            "expected_device_b_conflict",
            failures,
            json_text(conflict_pull_b),
        )
        require(
            "Device B local edit" in b_messages.read_text(encoding="utf-8"),
            "device_b_local_edit_overwritten",
            failures,
        )
        require(bool(conflict_files_b), "missing_device_b_conflict_copy", failures)
        if conflict_files_b:
            require(
                "Device A original" in conflict_files_b[0].read_text(encoding="utf-8"),
                "conflict_copy_missing_source_content",
                failures,
            )

        sync_dir_b = root / "device-b-to-a-sync"
        push_b = sync_bundle.push_sync_bundle(target_b, sync_dir_b)
        conflict_pull_a = sync_bundle.pull_sync_bundle(sync_dir_b, device_a["registry"])
        conflict_files_a = list((device_a["registry"] / ".sync-conflicts").rglob("messages.jsonl"))
        require(
            conflict_pull_a.get("conflicts", 0) >= 1,
            "expected_device_a_conflict",
            failures,
            json_text(conflict_pull_a),
        )
        require(bool(conflict_files_a), "missing_device_a_conflict_copy", failures)
        if conflict_files_a:
            require(
                "Device B local edit" in conflict_files_a[0].read_text(encoding="utf-8"),
                "reverse_conflict_missing_target_content",
                failures,
            )

        raw_sync = root / "raw-opt-in-sync"
        raw_target = root / "device-c-raw-target" / "registry"
        push_raw = sync_bundle.push_sync_bundle(
            device_a["registry"],
            raw_sync,
            include_raw=True,
            allow_plaintext_raw=True,
        )
        raw_pull = sync_bundle.pull_sync_bundle(raw_sync, raw_target)
        raw_registry = read_json(raw_target / "threads.json")
        raw_paths = locator_values(raw_registry)
        expected_raw = raw_target / "raw-rollouts" / f"{THREAD_DIR}.jsonl"
        require(
            same_resolved_path(raw_paths.get("rollout"), expected_raw),
            "raw_rollout_not_repaired_to_target",
            failures,
        )
        require(expected_raw.is_file(), "raw_rollout_file_missing_after_opt_in", failures)

        result["steps"] = {
            "push_device_a": push_a,
            "status_device_a_sync": status_a,
            "pull_device_b": pull_b,
            "device_b_conflict_pull": conflict_pull_b,
            "push_device_b": push_b,
            "device_a_conflict_pull": conflict_pull_a,
            "push_raw_opt_in": push_raw,
            "pull_raw_opt_in": raw_pull,
        }
        result["observed"] = {
            "portable_paths": locator_values(portable_registry),
            "target_b_paths": locator_values(target_registry),
            "raw_target_rollout": raw_paths.get("rollout"),
            "device_b_conflict_count": len(conflict_files_b),
            "device_a_conflict_count": len(conflict_files_a),
        }
        result["ok"] = not failures
        return result
    finally:
        if temp_context is not None:
            temp_context.cleanup()
        elif not keep_artifacts and root.exists():
            shutil.rmtree(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(_paths.REPO_ROOT))
    parser.add_argument("--run-id")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_cross_device_sync_smoke(
        args.repo_root,
        run_id=args.run_id,
        keep_artifacts=args.keep_artifacts,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"cross-device sync smoke: {'ok' if result.get('ok') else 'failed'}")
        for failure in result.get("failures") or []:
            print(f"- {failure.get('code')}: {failure.get('detail')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
