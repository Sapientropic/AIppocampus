"""Compatibility wrapper for the doctors owner package.

Sunset: keep this public module while release smokes and external users import
`aippocampus_runtime.ops.spend_doctor`; new implementation imports should use
`aippocampus_runtime.ops.doctors.spend_doctor`.
"""

from __future__ import annotations

from aippocampus_runtime.ops.doctors.spend_doctor import *  # noqa: F403
from aippocampus_runtime.ops.doctors.spend_doctor_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
