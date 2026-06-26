"""Fail-open prompt-hook helpers kept off the hot entrypoint body."""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

OPTIONAL_RUNTIME_EXCEPTIONS = (ImportError, ModuleNotFoundError)
FINAL_DIAGNOSTIC_WRITE_RESERVE_MS = 450


def _has_final_diagnostic_budget(*, started: float, max_elapsed_ms: int) -> bool:
    if max_elapsed_ms <= 0:
        return True
    elapsed_ms = (time.perf_counter() - started) * 1000
    return elapsed_ms <= max(0, max_elapsed_ms - FINAL_DIAGNOSTIC_WRITE_RESERVE_MS)


def prompt_hook_audit_status(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from aippocampus_runtime.hooks.debug_log import prompt_hook_audit_status as impl  # noqa: I001, PLC0415

    return impl(*args, **kwargs)


def write_debug_log(*args: Any, **kwargs: Any) -> None:
    from aippocampus_runtime.hooks.debug_log import write_debug_log as impl  # noqa: PLC0415

    impl(*args, **kwargs)


def write_prompt_hook_audit_status(*args: Any, **kwargs: Any) -> None:
    from aippocampus_runtime.hooks.debug_log import (  # noqa: PLC0415
        write_prompt_hook_audit_status as impl,
    )

    impl(*args, **kwargs)


def write_skip_telemetry(*args: Any, **kwargs: Any) -> None:
    from aippocampus_runtime.hooks.skip_telemetry import write_skip_telemetry as impl  # noqa: I001, PLC0415

    impl(*args, **kwargs)


def load_dream_delivery_module() -> tuple[Any | None, str | None]:
    try:
        from aippocampus_runtime.dream import delivery_policy as dream_delivery  # noqa: PLC0415
    except OPTIONAL_RUNTIME_EXCEPTIONS:
        return None, "policy_unavailable"
    except Exception:
        # Dream delivery is optional foreground material. Keep prompt submission
        # fail-open, but distinguish an unexpected import bug from a partial
        # install so diagnostics do not flatten both into "unavailable".
        return None, "policy_import_error"
    return dream_delivery, None


def add_dream_delivery_arguments(parser: argparse.ArgumentParser) -> None:
    dream_delivery, _reason = load_dream_delivery_module()
    if dream_delivery is None:
        parser.add_argument("--dream-shadow-ab", action="store_true")
        parser.add_argument("--dream-shadow-log")
        parser.add_argument(
            "--dream-shadow-salt",
            default=os.environ.get("AIPPOCAMPUS_DREAM_SHADOW_AB_SALT"),
        )
        parser.add_argument("--dream-delivery-mode")
        parser.add_argument("--dream-rollout-rate", type=float, default=None)
        return
    dream_delivery.add_dream_delivery_arguments(parser)


def prepare_dream_delivery(
    *,
    prompt: str,
    hook_input: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    dream_delivery, reason = load_dream_delivery_module()
    if dream_delivery is None:
        return {
            "mode": "off",
            "event": None,
            "allow_dream": False,
            "dream_hypothesis_limit": 0,
            "reason": reason or "policy_unavailable",
        }
    return dream_delivery.prepare_dream_delivery(prompt=prompt, hook_input=hook_input, args=args)


def fallback_reason(exc: Exception) -> str:
    if isinstance(exc, OPTIONAL_RUNTIME_EXCEPTIONS):
        return "runtime_unavailable"
    return "unexpected_runtime_error"


def fallback_payload(exc: Exception) -> dict[str, Any]:
    return {
        "decision": "skip",
        "fallback_reason": fallback_reason(exc),
        "error_type": type(exc).__name__,
    }
