#!/usr/bin/env python3
"""Compatibility shim for the packaged dream one-sidedness gate."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.dream.one_sidedness import *  # noqa: F403

from aippocampus_runtime.dream import one_sidedness as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
