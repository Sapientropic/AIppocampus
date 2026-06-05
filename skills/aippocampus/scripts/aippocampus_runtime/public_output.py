"""Small helpers for emitting already-public CLI output.

Runtime commands often hold private source paths, model output, or env-derived
state in local variables before projecting them into public reports. Keep the
actual stdout/stderr sink behind one helper so future edits have a single place
to document that only projected, non-secret text should cross this boundary.
"""

from __future__ import annotations

import sys
from typing import TextIO


def emit_public_text(text: str, *, end: str = "\n", stream: TextIO | None = None) -> None:
    """Write public report text without reintroducing raw diagnostic values."""

    target = stream or sys.stdout
    # The caller owns redaction before this point. Do not pass raw exception
    # text, local paths, source snippets, or env-derived values here.
    target.write(text)
    if end and not text.endswith(end):
        target.write(end)
