#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious deterministic jobs."""

from __future__ import annotations

from aippocampus_runtime.subconscious.deterministic_jobs import (
    DETERMINISTIC_QUESTION_RESOLUTION_RUNNER as DETERMINISTIC_QUESTION_RESOLUTION_RUNNER,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    DETERMINISTIC_QUESTION_TRACKING_RUNNER as DETERMINISTIC_QUESTION_TRACKING_RUNNER,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    DETERMINISTIC_RUNNERS as DETERMINISTIC_RUNNERS,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    DETERMINISTIC_THEME_EMERGENCE_RUNNER as DETERMINISTIC_THEME_EMERGENCE_RUNNER,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    run_deterministic_job as run_deterministic_job,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    run_question_resolution_job as run_question_resolution_job,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    run_question_tracking_job as run_question_tracking_job,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    run_theme_emergence_job as run_theme_emergence_job,
)
