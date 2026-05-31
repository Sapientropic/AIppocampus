#!/usr/bin/env python3
"""Compatibility shim for the packaged fresh-thread recall demo runner."""

from __future__ import annotations

from aippocampus_runtime.recall import fresh_thread_demo as _impl

globals().update(
    {
        name: getattr(_impl, name)
        for name in dir(_impl)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
__all__ = [name for name in globals() if not name.startswith("_")]


if __name__ == "__main__":
    raise SystemExit(_impl.main())
