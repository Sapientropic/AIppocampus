#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus registry API."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.registry.api import *  # noqa: F403

from aippocampus_runtime.registry import api as _api

sys.modules[__name__] = _api


if __name__ == "__main__":
    raise SystemExit(_api.main())
