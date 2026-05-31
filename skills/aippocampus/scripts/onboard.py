#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus onboarding facade."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.onboarding.facade import *  # noqa: F403

from aippocampus_runtime.onboarding import facade as _facade

sys.modules[__name__] = _facade

if __name__ == "__main__":
    raise SystemExit(_facade.main())
