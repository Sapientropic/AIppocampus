"""Optional clean-source redaction profile projections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampus_runtime.safety import project_clean_source_row


def write_clean_source_redaction_profiles(
    messages: list[dict[str, Any]],
    *,
    profiles: list[str] | None,
    output_dir: Path,
    project_root: Path,
    canonical_messages_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Write optional clean-source projections without mutating canonical text."""

    profile_outputs: dict[str, dict[str, Any]] = {}
    profile_summary: dict[str, dict[str, Any]] = {
        "raw-private": {
            "source_fidelity": "canonical",
            "messages_jsonl": str(canonical_messages_path),
            "default": True,
        }
    }
    for profile in list(dict.fromkeys(profiles or [])):
        if profile == "raw-private":
            continue
        projected_dir = output_dir / "projections" / profile
        projected_dir.mkdir(parents=True, exist_ok=True)
        projected_path = projected_dir / "messages.jsonl"
        redaction_count = 0
        with projected_path.open("w", encoding="utf-8", newline="\n") as f:
            for item in messages:
                projected = project_clean_source_row(
                    item,
                    profile=profile,
                    project_root=project_root,
                )
                policy = projected.get("redaction_policy") or {}
                redaction_count += int(policy.get("redaction_count") or 0)
                f.write(json.dumps(projected, ensure_ascii=False) + "\n")
        profile_outputs[profile] = {
            "messages_jsonl": str(projected_path),
            "source_fidelity": "projection",
            "canonical_messages_jsonl": str(canonical_messages_path),
            "redaction_count": redaction_count,
        }
        profile_summary[profile] = profile_outputs[profile]
    return profile_outputs, profile_summary
