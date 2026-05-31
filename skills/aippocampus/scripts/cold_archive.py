#!/usr/bin/env python3
"""Compatibility shim for packaged cold archive creation."""

from __future__ import annotations

import sys

from aippocampus_runtime.ops import cold_archive as _impl

if __name__ != "__main__":
    sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(_impl.main())
