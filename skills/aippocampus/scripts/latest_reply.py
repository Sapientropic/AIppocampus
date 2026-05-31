#!/usr/bin/env python3
"""Compatibility shim for the packaged latest-reply helper."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.source.latest_reply import *  # noqa: F403

from aippocampus_runtime.source import latest_reply as _latest_reply

sys.modules[__name__] = _latest_reply

if __name__ == "__main__":
    raise SystemExit(_latest_reply.main())
