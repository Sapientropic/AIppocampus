#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus MCP server."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.mcp.server import *  # noqa: F403

from aippocampus_runtime.mcp import server as _server

sys.modules[__name__] = _server


if __name__ == "__main__":
    raise SystemExit(_server.main())
