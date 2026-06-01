#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious question diagnostics."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.question_diagnostics import *  # noqa: F403

from aippocampus_runtime.subconscious import question_diagnostics as _impl

sys.modules[__name__] = _impl
