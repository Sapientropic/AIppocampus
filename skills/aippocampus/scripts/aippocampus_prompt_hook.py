#!/usr/bin/env python3
"""Compatibility shim for the packaged AIppocampus prompt hook."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aippocampus_runtime.hooks.prompt import *  # noqa: F403

try:
    from aippocampus_runtime.hooks import prompt as _prompt
except ModuleNotFoundError:
    # Codex hooks can briefly point at a half-copied skill directory during
    # install/update. Preserve the historical fail-open boundary: the hook may
    # skip recall, but it must not block the user's prompt just because the
    # package owner has not landed yet.
    def main(argv: list[str] | None = None) -> int:
        args = list(sys.argv[1:] if argv is None else argv)
        if "--json" in args:
            print(
                json.dumps(
                    {"decision": "skip", "error": "aippocampus_runtime_unavailable"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

else:
    sys.modules[__name__] = _prompt

    if __name__ == "__main__":
        raise SystemExit(_prompt.main())

if __name__ == "__main__":
    raise SystemExit(main())
