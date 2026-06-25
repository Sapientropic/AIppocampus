from __future__ import annotations


def clean_source_ref(ref: dict) -> dict:
    return {
        "thread_key": ref.get("thread_key") or ref.get("thread_id"),
        "message_id": ref.get("message_id"),
        "line": ref.get("line") or ref.get("source_line"),
    }
