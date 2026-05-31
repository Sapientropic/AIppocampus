#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus onboarding status helpers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.onboarding.status import *  # noqa: F403

from aippocampus_runtime.onboarding import status as _status

sys.modules[__name__] = _status
