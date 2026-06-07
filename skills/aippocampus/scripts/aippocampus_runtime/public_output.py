"""Small helpers for emitting already-public CLI output.

Runtime commands often hold private source paths, model output, or env-derived
state in local variables before projecting them into public reports. Keep the
actual stdout/stderr sink behind one helper so future edits have a single place
to document that only projected, non-secret text should cross this boundary.
"""

from __future__ import annotations

import sys
from typing import TextIO

from aippocampus_runtime.core import sanitize_external_model_text


def _project_public_text(text: str) -> str:
    sanitized, policy = sanitize_external_model_text(str(text or ""))
    if policy.get("hard_block"):
        return "<redacted:sensitive-output>"
    return sanitized


def emit_public_text(text: str, *, end: str = "\n", stream: TextIO | None = None) -> None:
    """Write public report text without reintroducing raw diagnostic values."""

    target = stream or sys.stdout
    # The caller owns structured redaction before this point; this final text
    # projection is a defense against hand-written or future unsafe callers.
    public_text = _project_public_text(text)
    target.writelines((public_text,))
    if end and not public_text.endswith(end):
        target.writelines((end,))
