#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious consolidation worker."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.worker import *  # noqa: F403

from aippocampus_runtime.subconscious import worker as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
