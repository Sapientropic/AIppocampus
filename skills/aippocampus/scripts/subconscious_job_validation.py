#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious job validation helpers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.job_validation import *  # noqa: F403

from aippocampus_runtime.subconscious import job_validation as _impl

sys.modules[__name__] = _impl
