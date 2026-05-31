#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus onboarding frontier helpers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.onboarding.frontier import *  # noqa: F403

from aippocampus_runtime.onboarding import frontier as _frontier

sys.modules[__name__] = _frontier
