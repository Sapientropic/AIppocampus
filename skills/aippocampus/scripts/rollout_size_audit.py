#!/usr/bin/env python3
"""Compatibility shim for packaged raw-rollout size diagnostics."""

from __future__ import annotations

import sys

from aippocampus_runtime.ops import rollout_size_audit as _impl

if __name__ != "__main__":
    sys.modules[__name__] = _impl


if __name__ == "__main__":
    raise SystemExit(_impl.main())
