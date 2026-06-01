"""CLI error payload helpers shared by command entrypoints."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.text import compact_text


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
    return "runtime_error"


def cli_exit_code_for_error_code(code: str) -> int:
    return 2 if code in {"missing_api_key", "missing_file", "invalid_json"} else 1


def cli_error_payload(exc: BaseException) -> dict[str, Any]:
    message = compact_text(f"{type(exc).__name__}: {exc}", 800)
    code = cli_error_code_from_message(message)
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
        "data": None,
    }


def cli_error_payload_from_message(message: str) -> dict[str, Any]:
    clean_message = compact_text(str(message or ""), 800)
    return {
        "ok": False,
        "error": {
            "code": cli_error_code_from_message(clean_message),
            "message": clean_message,
        },
        "data": None,
    }
