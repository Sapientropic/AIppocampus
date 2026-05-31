#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus prompt-hook installer."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.hooks.install_prompt import *  # noqa: F403

from aippocampus_runtime.hooks import install_prompt as _install_prompt

sys.modules[__name__] = _install_prompt

if __name__ == "__main__":
    raise SystemExit(_install_prompt.main())
