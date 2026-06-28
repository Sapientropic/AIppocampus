from __future__ import annotations

import json
from pathlib import Path

from aippocampus_runtime import health


def write_rollout(
    path: Path,
    cwd: Path,
    *,
    session_id: str = "health-session",
    include_second_turn: bool = False,
) -> None:
    rows = [
        {
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": "2026-06-05T00:00:00Z",
                "cwd": str(cwd),
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-05T00:00:01Z",
            "payload": {
                "type": "user_message",
                "message": "first source-backed freshness question",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-05T00:00:02Z",
            "payload": {
                "type": "agent_message",
                "phase": "commentary",
                "message": "checking local source",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-05T00:00:03Z",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": "first final source-backed answer",
            },
        },
    ]
    if include_second_turn:
        rows.extend(
            [
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T00:01:01Z",
                    "payload": {
                        "type": "user_message",
                        "message": "latest source-backed freshness marker",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T00:01:02Z",
                    "payload": {
                        "type": "agent_message",
                        "phase": "final_answer",
                        "message": "latest final answer must be searchable",
                    },
                },
            ]
        )
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_current_artifacts(
    root: Path,
    workspace: Path,
    rollout: Path,
    *,
    index_created_at: str = "2026-06-01T00:00:00Z",
    clean_created_at: str = "2026-06-01T00:00:00Z",
    rag_enabled: bool = True,
    clean_schema: int = 2,
    clean_upgrade_contract: bool = True,
) -> dict[str, Path]:
    anchors = workspace / "thread-anchors.md"
    anchors.write_text("# Anchors\n", encoding="utf-8")
    visibility = health.rollout_visibility_stats(rollout)
    current_message_count, last_line = health.count_messages(rollout)
    index_dir = root / "index"
    index_dir.mkdir()
    manifest = {
        "created_at": index_created_at,
        "message_count": current_message_count,
        "source_rollout_size": rollout.stat().st_size,
        "last_message_line": last_line,
        "anchor_sha256": health.file_sha256(anchors),
    }
    if rag_enabled:
        manifest["rag"] = {"enabled": True, "chunk_count": 1}
    (index_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (index_dir / "source_index.sqlite").write_bytes(b"index")
    clean = root / "clean-source"
    clean.mkdir()
    clean_manifest = {
        "created_at": clean_created_at,
        "schema_version": clean_schema,
        "source_rollout_size": rollout.stat().st_size,
        "message_count": visibility.expected_clean_source_message_count,
        "turn_count": visibility.expected_clean_source_turn_count,
        "source_texture_count": 1,
        "source_texture_policy": {
            "boundary": "source texture rows are rebuildable interpretation inputs, not source truth.",
        },
    }
    if clean_upgrade_contract:
        clean_manifest["upgrade_contract"] = {"source_backed": True}
    (clean / "manifest.json").write_text(json.dumps(clean_manifest), encoding="utf-8")
    (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
    (clean / "source-texture.jsonl").write_text(
        json.dumps(
            {
                "texture_id": "tex_1",
                "signal_kind": "self_correction_signal",
                "truth_boundary": "texture_signal_not_source_fact",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    graphify = root / "graphify-corpus"
    graphify.mkdir()
    (graphify / "corpus_manifest.json").write_text(
        json.dumps({"source_index_manifest_sha256": health.file_sha256(index_dir / "manifest.json")}),
        encoding="utf-8",
    )
    return {
        "anchors": anchors,
        "index_dir": index_dir,
        "clean_source_dir": clean,
        "graphify_corpus": graphify,
        "segments_dir": root / "segments",
        "checkpoint_state": root / "checkpoint_state.json",
    }


def write_latest_turn_gap_artifacts(
    root: Path,
    workspace: Path,
) -> tuple[Path, dict[str, Path]]:
    rollout = workspace / "rollout.jsonl"
    write_rollout(rollout, workspace, include_second_turn=False)
    current_size = rollout.stat().st_size
    rollout.write_text(
        rollout.read_text(encoding="utf-8")
        + "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T00:01:01Z",
                    "payload": {
                        "type": "user_message",
                        "message": "latest source-backed freshness marker",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T00:01:02Z",
                    "payload": {
                        "type": "agent_message",
                        "phase": "final_answer",
                        "message": "latest final answer must be searchable",
                    },
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    anchors = workspace / "thread-anchors.md"
    anchors.write_text("# Anchors\n", encoding="utf-8")
    index_dir = root / "index"
    index_dir.mkdir()
    (index_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-06-05T00:00:03Z",
                "message_count": 3,
                "source_rollout_size": current_size,
                "last_message_line": 4,
                "anchor_sha256": health.file_sha256(anchors),
                "rag": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (index_dir / "source_index.sqlite").write_bytes(b"index")
    clean = root / "clean-source"
    clean.mkdir()
    (clean / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "upgrade_contract": {"source_backed": True},
                "source_rollout_size": current_size,
                "message_count": 2,
                "turn_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
    return rollout, {
        "anchors": anchors,
        "index_dir": index_dir,
        "clean_source_dir": clean,
        "graphify_corpus": root / "graphify-corpus",
        "segments_dir": root / "segments",
        "checkpoint_state": root / "checkpoint_state.json",
    }
