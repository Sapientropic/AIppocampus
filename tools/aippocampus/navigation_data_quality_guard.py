#!/usr/bin/env python3
"""Compatibility CLI wrapper for the package-owned navigation data guard."""

from __future__ import annotations

from aippocampus_runtime.navigation.data_quality_guard import main

if __name__ == "__main__":
    raise SystemExit(main())
