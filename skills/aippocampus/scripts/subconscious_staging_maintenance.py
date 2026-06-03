#!/usr/bin/env python3
"""Compatibility shim for subconscious staging maintenance reporting."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.staging_maintenance import *  # noqa: F403

from aippocampus_runtime.subconscious import staging_maintenance as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
