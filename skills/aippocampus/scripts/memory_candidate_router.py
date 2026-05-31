#!/usr/bin/env python3
"""Compatibility shim for the packaged subconscious candidate router."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.candidate_router import *  # noqa: F403

from aippocampus_runtime.subconscious import candidate_router as _candidate_router

sys.modules[__name__] = _candidate_router


if __name__ == "__main__":
    raise SystemExit(_candidate_router.main())
