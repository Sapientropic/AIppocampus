#!/usr/bin/env python3
"""Compatibility shim for packaged AIppocampus maintenance."""

from __future__ import annotations

import sys

from aippocampus_runtime.ops import maintenance as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(getattr(_impl, "main", lambda: 0)())
