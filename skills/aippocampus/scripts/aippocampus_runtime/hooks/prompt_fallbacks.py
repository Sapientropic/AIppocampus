"""Fail-open prompt-hook helpers kept off the hot entrypoint body."""

from __future__ import annotations

from typing import Any

OPTIONAL_RUNTIME_EXCEPTIONS = (ImportError, ModuleNotFoundError)


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
