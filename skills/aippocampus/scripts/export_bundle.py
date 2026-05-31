#!/usr/bin/env python3
"""Compatibility shim for packaged portable bundle export."""

from __future__ import annotations

import sys
from aippocampus_runtime.artifacts import export_bundle as _impl

sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(_impl.main())
