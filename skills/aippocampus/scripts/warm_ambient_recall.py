#!/usr/bin/env python3
"""Compatibility shim for packaged warm ambient recall runtime."""

from __future__ import annotations

import sys

from aippocampus_runtime.warm_ambient import recall as _impl

if __name__ != "__main__":
    sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(_impl.main())
