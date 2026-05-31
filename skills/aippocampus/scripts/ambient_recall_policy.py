#!/usr/bin/env python3
"""Compatibility shim for packaged ambient recall policy."""

from __future__ import annotations

from aippocampus_runtime.recall import ambient_policy as _impl

globals().update(
    {
        name: getattr(_impl, name)
        for name in dir(_impl)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
__all__ = [name for name in globals() if not name.startswith("_")]
