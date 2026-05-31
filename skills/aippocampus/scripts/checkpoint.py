#!/usr/bin/env python3
"""Compatibility shim for packaged checkpoint artifact."""

from __future__ import annotations

import sys

from aippocampus_runtime.artifacts import checkpoint as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(getattr(_impl, "main", lambda: 0)())
