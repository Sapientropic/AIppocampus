#!/usr/bin/env python3
"""Compatibility shim for packaged dream precision policies."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.dream.precision_policy import *  # noqa: F403

from aippocampus_runtime.dream import precision_policy as _impl

sys.modules[__name__] = _impl
