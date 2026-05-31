#!/usr/bin/env python3
"""Compatibility shim for packaged question health diagnostics."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.question.health import *  # noqa: F403

from aippocampus_runtime.question import health as _health

sys.modules[__name__] = _health

if __name__ == "__main__":
    raise SystemExit(_health.main())
