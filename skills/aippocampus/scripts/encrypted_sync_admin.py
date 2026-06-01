#!/usr/bin/env python3
"""Compatibility shim for packaged encrypted sync admin."""

from __future__ import annotations

import sys

from aippocampus_runtime.sync.encrypted import admin as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
