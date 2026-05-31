#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious consolidation worker."""

from __future__ import annotations

from aippocampus_runtime.subconscious.worker import (
    ALLOWED_EDGE_TYPES as ALLOWED_EDGE_TYPES,
)
from aippocampus_runtime.subconscious.worker import DEFAULT_BASE_URL as DEFAULT_BASE_URL
from aippocampus_runtime.subconscious.worker import DEFAULT_MAX_TURNS as DEFAULT_MAX_TURNS
from aippocampus_runtime.subconscious.worker import DEFAULT_MODEL as DEFAULT_MODEL
from aippocampus_runtime.subconscious.worker import PROMPT_VERSION as PROMPT_VERSION
from aippocampus_runtime.subconscious.worker import SYSTEM_PROMPT as SYSTEM_PROMPT
from aippocampus_runtime.subconscious.worker import (
    append_staging_edges as append_staging_edges,
)
from aippocampus_runtime.subconscious.worker import call_deepseek as call_deepseek
from aippocampus_runtime.subconscious.worker import clamp_confidence as clamp_confidence
from aippocampus_runtime.subconscious.worker import (
    default_project_timeline_path as default_project_timeline_path,
)
from aippocampus_runtime.subconscious.worker import default_staging_path as default_staging_path
from aippocampus_runtime.subconscious.worker import load_json as load_json
from aippocampus_runtime.subconscious.worker import main as main
from aippocampus_runtime.subconscious.worker import parse_model_json as parse_model_json
from aippocampus_runtime.subconscious.worker import run_worker as run_worker
from aippocampus_runtime.subconscious.worker import (
    select_timeline_turns as select_timeline_turns,
)
from aippocampus_runtime.subconscious.worker import user_prompt_for_turns as user_prompt_for_turns
from aippocampus_runtime.subconscious.worker import validate_edges as validate_edges

if __name__ == "__main__":
    raise SystemExit(main())
