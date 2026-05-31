#!/usr/bin/env python3
"""Compatibility shim for packaged recall segment building."""

from __future__ import annotations

import sys

from aippocampus_runtime.recall import segment_builder as _impl

sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(_impl.main())
