"""Package import bridge for the legacy subconscious_review CLI.

The direct script remains the single implementation for this model-output-heavy
review path. Keep package imports available without duplicating the semantic
review logic under a second file.
"""

from __future__ import annotations

import sys

import subconscious_review as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

sys.modules[__name__] = _impl
