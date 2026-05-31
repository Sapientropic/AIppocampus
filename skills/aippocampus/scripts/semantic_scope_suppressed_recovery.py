#!/usr/bin/env python3
"""Compatibility shim for packaged semantic-scope suppressed recovery."""

from __future__ import annotations

import sys

from aippocampus_runtime.source import semantic_scope_suppressed_recovery as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(getattr(_impl, "main", lambda: 0)())
