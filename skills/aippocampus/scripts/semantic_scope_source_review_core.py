#!/usr/bin/env python3
"""Compatibility shim for packaged semantic-scope source review core."""

from __future__ import annotations

import sys

from aippocampus_runtime.source import semantic_scope_source_review_core as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(getattr(_impl, "main", lambda: 0)())
