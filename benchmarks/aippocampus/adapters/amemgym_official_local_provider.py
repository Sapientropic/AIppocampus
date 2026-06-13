#!/usr/bin/env python3
"""Local deterministic provider shim for the official AMemGym bridge.

This helper is deliberately not a model benchmark. It exists to let the
repository run the upstream AMemGym entrypoints end-to-end on the full public
dataset without provider cost, then prove that output discovery, score
normalization, and public report boundaries work before expensive live-model
runs are attempted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LOCAL_SCRIPTED_PROVIDER = "local-scripted"
LOCAL_SCRIPTED_MODEL = "aippocampus-local-scripted-json-choice-v1"
LOCAL_SCRIPTED_CHOICE_ENV = "AIPPOCAMPUS_AMEMGYM_LOCAL_SCRIPTED_CHOICE"
LOCAL_SCRIPTED_ENABLED_ENV = "AIPPOCAMPUS_AMEMGYM_LOCAL_SCRIPTED"
LOCAL_SCRIPTED_NO_SLEEP_ENV = "AIPPOCAMPUS_AMEMGYM_LOCAL_SCRIPTED_NO_SLEEP"


def local_scripted_provider_env(*, choice_index: int = 1, no_sleep: bool = True) -> dict[str, str]:
    return {
        LOCAL_SCRIPTED_ENABLED_ENV: "1",
        LOCAL_SCRIPTED_CHOICE_ENV: str(choice_index),
        LOCAL_SCRIPTED_NO_SLEEP_ENV: "1" if no_sleep else "0",
    }


def local_scripted_public_status(*, choice_index: int = 1) -> dict[str, Any]:
    return {
        "provider": LOCAL_SCRIPTED_PROVIDER,
        "credential_status": "not_required",
        "base_url": "not_used",
        "model": LOCAL_SCRIPTED_MODEL,
        "choice_index": choice_index,
        "score_kind": "official_protocol_full_output_not_llm_quality",
    }


def local_scripted_llm_config_update() -> dict[str, Any]:
    return {
        "llm_model": LOCAL_SCRIPTED_MODEL,
        "base_url": None,
        "api_key": None,
        "source": "agent:local-scripted-official-bridge",
    }


def provider_plan_environment(provider: str) -> dict[str, str]:
    if provider == LOCAL_SCRIPTED_PROVIDER:
        return {
            "provider_credential": "not required for local-scripted protocol runs",
            "provider_base_url": "not used for local-scripted protocol runs",
            "provider_mode": "local scripted call_llm patch; no provider credentials or live model calls",
        }
    return {
        "provider_credential": "OPENAI_API_KEY required for overall and upperbound; never written to reports",
        "provider_base_url": "OPENAI_BASE_URL optional; redacted from reports",
        "provider_mode": "external or environment-backed provider",
    }


def write_local_scripted_provider_overlay(output_root: Path | str) -> dict[str, Any]:
    overlay_dir = Path(output_root) / "local-scripted-provider"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    sitecustomize = overlay_dir / "sitecustomize.py"
    sitecustomize.write_text(SITE_CUSTOMIZE, encoding="utf-8")
    return {
        "status": "ready",
        "pythonpath": str(overlay_dir),
        "label": "local-scripted-provider",
        "model": LOCAL_SCRIPTED_MODEL,
        "patch_surface": "sitecustomize patches amemgym.utils.call_llm during official subprocess startup",
    }


def provider_runtime_for_provider(provider: str, *, output_root: Path | str) -> dict[str, Any]:
    if provider != LOCAL_SCRIPTED_PROVIDER:
        return {
            "status": "not_required",
            "pythonpath_entries": [],
            "metadata": {"local_scripted_overlay": False},
        }
    overlay = write_local_scripted_provider_overlay(output_root)
    entries = [str(overlay["pythonpath"])] if overlay.get("pythonpath") else []
    return {
        "status": overlay["status"],
        "pythonpath_entries": entries,
        "metadata": {
            "local_scripted_overlay": overlay["status"] == "ready",
            "overlay_label": overlay.get("label"),
            "model": overlay.get("model"),
            "patch_surface": overlay.get("patch_surface"),
        },
    }


SITE_CUSTOMIZE = r'''"""Installed by AIppocampus for local AMemGym protocol runs."""

from __future__ import annotations

import json as _json
import os as _os
import re as _re
import time as _time
from typing import Any as _Any


def _configured_choice() -> int:
    raw = _os.environ.get("AIPPOCAMPUS_AMEMGYM_LOCAL_SCRIPTED_CHOICE", "1")
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _last_message_content(messages: list[dict[str, _Any]] | tuple[dict[str, _Any], ...]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return str(last.get("content") or "")
    return str(last)


def _choice_count(prompt: str) -> int:
    matches = [int(match) for match in _re.findall(r"(?m)^\s*(\d+)\s*:", prompt)]
    return max(matches, default=1)


def _looks_like_choice_question(prompt: str) -> bool:
    lowered = prompt.casefold()
    return '"answer": int' in prompt or "please select the most suitable answer" in lowered


def _scripted_call_llm(
    messages: list[dict[str, _Any]] | tuple[dict[str, _Any], ...],
    llm_config: dict[str, _Any],
    json: bool = False,
    return_token_usage: bool = False,
) -> str | tuple[str, dict[str, _Any]]:
    del llm_config
    prompt = _last_message_content(messages)
    choice = min(_configured_choice(), _choice_count(prompt))
    if json or _looks_like_choice_question(prompt):
        content = _json.dumps({"answer": choice})
    else:
        content = "I understand and will keep that in mind."
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "time_elapsed": 0.0,
        "provider": "local-scripted",
    }
    if return_token_usage:
        return content, usage
    return content


if _os.environ.get("AIPPOCAMPUS_AMEMGYM_LOCAL_SCRIPTED") == "1":
    import amemgym.utils as _utils
    import amemgym.utils.llm_utils as _llm_utils

    _utils.call_llm = _scripted_call_llm
    _llm_utils.call_llm = _scripted_call_llm

    if _os.environ.get("AIPPOCAMPUS_AMEMGYM_LOCAL_SCRIPTED_NO_SLEEP") == "1":
        _time.sleep = lambda _seconds: None
'''
