from __future__ import annotations

from typing import Any, Callable


def handler(
    render_profiled_result: Callable[..., dict[str, Any]],
    public_payload: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return render_profiled_result(
        public_payload({"status": "needs_input"}),
        detail="full",
        is_error=True,
    )
