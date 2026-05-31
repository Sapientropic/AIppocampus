#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus lifecycle-hook installer."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.hooks.install_lifecycle import *  # noqa: F403

from aippocampus_runtime.hooks import install_lifecycle as _install_lifecycle

sys.modules[__name__] = _install_lifecycle

if __name__ == "__main__":
    raise SystemExit(_install_lifecycle.main())
