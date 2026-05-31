#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus lifecycle hook."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.hooks.lifecycle import *  # noqa: F403

from aippocampus_runtime.hooks import lifecycle as _lifecycle

sys.modules[__name__] = _lifecycle

if __name__ == "__main__":
    raise SystemExit(_lifecycle.main())
