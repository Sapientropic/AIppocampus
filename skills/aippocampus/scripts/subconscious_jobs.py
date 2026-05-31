#!/usr/bin/env python3
"""Compatibility shim for the packaged subconscious jobs runner."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.subconscious.jobs import *  # noqa: F403

from aippocampus_runtime.subconscious import jobs as _jobs

sys.modules[__name__] = _jobs


if __name__ == "__main__":
    raise SystemExit(_jobs.main())
