"""CLI error payload helpers shared by command entrypoints."""

from __future__ import annotations

from typing import Any, Mapping

from aippocampus_runtime.text import compact_text

STABLE_CLI_ERROR_CODE_CLASSES = {
    "usage_error": "usage_error",
    "unsupported_operation": "usage_error",
    "invalid_json": "validation_error",
    "validation_error": "validation_error",
    "missing_api_key": "missing_prerequisite",
    "missing_file": "missing_prerequisite",
    "missing_prerequisite": "missing_prerequisite",
    "privacy_blocked": "privacy_block",
    "runtime_error": "runtime_error",
}

CALLER_ACTIONABLE_ERROR_CLASSES = {
    "usage_error",
    "validation_error",
    "missing_prerequisite",
    "privacy_block",
}


def cli_error_code_from_message(message: str) -> str:
    low = str(message or "").casefold()
    if "missing deepseek api key" in low or "missing api key" in low or (
        "missing" in low and "api key" in low
    ):
        return "missing_api_key"
    if "no such file" in low or "cannot find the file" in low or "filenotfounderror" in low:
        return "missing_file"
    if "jsondecodeerror" in low or "invalid json" in low:
        return "invalid_json"
    if "privacy" in low and ("blocked" in low or "forbidden" in low or "denied" in low):
        return "privacy_blocked"
    if "unsupported" in low:
        return "unsupported_operation"
    return "runtime_error"


def cli_error_class_for_error_code(code: str) -> str:
    return STABLE_CLI_ERROR_CODE_CLASSES.get(str(code or ""), "runtime_error")


def cli_exit_code_for_error_code(code: str) -> int:
    error_class = cli_error_class_for_error_code(code)
    return 2 if error_class in CALLER_ACTIONABLE_ERROR_CLASSES else 1


def cli_error_object(code: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "class": cli_error_class_for_error_code(code),
        "message": message,
    }


def _stable_public_error_code(value: Any) -> str:
    text = str(value or "").strip()
    safe = "".join(char for char in text[:80] if char.isalnum() or char in {"_", "-"})
    return safe if safe in STABLE_CLI_ERROR_CODE_CLASSES else "runtime_error"


def cli_public_error_object(error: Mapping[str, Any] | None) -> dict[str, str] | None:
    """Return the stable CLI error fields allowed in public JSON projections.

    Public subconscious outputs deliberately omit exception messages and private
    model artifacts. Keep this projection tied to the stable code taxonomy so a
    future local-only error value cannot accidentally become a public contract.
    """

    if not isinstance(error, Mapping):
        return None
    code = _stable_public_error_code(error.get("code"))
    return {
        "code": code,
        "class": cli_error_class_for_error_code(code),
    }


def cli_error_payload(exc: BaseException) -> dict[str, Any]:
    message = compact_text(f"{type(exc).__name__}: {exc}", 800)
    code = cli_error_code_from_message(message)
    return {
        "ok": False,
        "error": cli_error_object(code, message),
        "data": None,
    }


def cli_error_payload_from_message(message: str) -> dict[str, Any]:
    clean_message = compact_text(str(message or ""), 800)
    return {
        "ok": False,
        "error": cli_error_object(cli_error_code_from_message(clean_message), clean_message),
        "data": None,
    }
