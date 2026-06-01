#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious deterministic jobs."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.deterministic_jobs import *  # noqa: F403

from aippocampus_runtime.subconscious import deterministic_jobs as _impl

sys.modules[__name__] = _impl
