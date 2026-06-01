#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious review."""

from __future__ import annotations

import sys

from aippocampus_runtime.subconscious import review as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
