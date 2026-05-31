#!/usr/bin/env python3
"""Compatibility shim for packaged storage capacity diagnostics."""

from __future__ import annotations

import sys

from aippocampus_runtime.ops import storage_capacity_report as _impl

if __name__ != "__main__":
    sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(_impl.main())
