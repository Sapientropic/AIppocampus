#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious question diagnostics."""

from __future__ import annotations

from aippocampus_runtime.subconscious.question_diagnostics import (
    QUESTION_AUDIT_FIELDS as QUESTION_AUDIT_FIELDS,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    QUESTION_CORE_AXIS_FIELDS as QUESTION_CORE_AXIS_FIELDS,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    QUESTION_EXTRACTION_FIELD_CONTRACT as QUESTION_EXTRACTION_FIELD_CONTRACT,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    field_presence_counts as field_presence_counts,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    final_attempt_findings as final_attempt_findings,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    question_axis_repair_feedback as question_axis_repair_feedback,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    question_extraction_quality_diagnostics as question_extraction_quality_diagnostics,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    raw_required_field_presence as raw_required_field_presence,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    raw_to_validated_retention as raw_to_validated_retention,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    should_request_question_axis_repair as should_request_question_axis_repair,
)
