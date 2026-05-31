#!/usr/bin/env python3
"""Compatibility shim for packaged vault dashboard rendering."""

from __future__ import annotations

import sys

from aippocampus_runtime.vault import dashboard as _impl

if __name__ != "__main__":
    sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(0)
