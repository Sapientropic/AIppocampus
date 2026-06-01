#!/usr/bin/env python3
"""Compatibility shim for packaged coding rejected-route Dream probes."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.coding.rejected_route_probes import *  # noqa: F403

from aippocampus_runtime.coding import rejected_route_probes as _impl

sys.modules[__name__] = _impl
