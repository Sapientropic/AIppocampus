from __future__ import annotations

from typing import Any, Callable


def handler(
    text_result: Callable[[dict[str, Any]], dict[str, Any]],
    public_payload: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return text_result(public_payload({"status": "needs_input"}))
