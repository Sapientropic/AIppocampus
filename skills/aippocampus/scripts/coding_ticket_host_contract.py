#!/usr/bin/env python3
"""Compatibility shim for the packaged coding ticket host contract."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.coding.host_contract import *  # noqa: F403

from aippocampus_runtime.coding import host_contract as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
