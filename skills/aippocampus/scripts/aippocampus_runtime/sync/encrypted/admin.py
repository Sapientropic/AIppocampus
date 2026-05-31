"""Package import bridge for the legacy encrypted_sync_admin CLI.

The direct script remains the single implementation for this credential-adjacent
operator command. Package imports stay available while avoiding a second copied
security-analysis surface.
"""

from __future__ import annotations

import sys

import encrypted_sync_admin as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

sys.modules[__name__] = _impl
