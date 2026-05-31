"""Package import bridge for the legacy semantic_scope_suppressed_recovery CLI.

The direct script remains the single implementation for this model-output-heavy
maintenance path. Moving the whole body here made GitHub default CodeQL treat
existing sanitized CLI output as newly added sensitive-output surface, which is
orthogonal to Issue #144's package/API ownership goal.
"""

from __future__ import annotations

import sys

import semantic_scope_suppressed_recovery as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

sys.modules[__name__] = _impl
