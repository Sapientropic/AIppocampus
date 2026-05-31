#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus Codex onboarding runner."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.onboarding.codex import *  # noqa: F403

from aippocampus_runtime.onboarding import codex as _codex

sys.modules[__name__] = _codex

if __name__ == "__main__":
    raise SystemExit(_codex.main())
