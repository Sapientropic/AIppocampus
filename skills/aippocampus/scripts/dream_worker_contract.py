#!/usr/bin/env python3
"""Compatibility shim for the packaged dream worker prompt contract."""

from __future__ import annotations

from aippocampus_runtime.dream.worker_contract import PROMPT_ORDER as PROMPT_ORDER
from aippocampus_runtime.dream.worker_contract import PROMPT_VERSION as PROMPT_VERSION
from aippocampus_runtime.dream.worker_contract import (
    stable_worker_contract as stable_worker_contract,
)
from aippocampus_runtime.dream.worker_contract import (
    variable_run_directive as variable_run_directive,
)
