#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious job validation helpers."""

from __future__ import annotations

from aippocampus_runtime.subconscious.job_validation import (
    ALLOWED_FRONTIER_TYPES as ALLOWED_FRONTIER_TYPES,
)
from aippocampus_runtime.subconscious.job_validation import (
    ALLOWED_QUESTION_FINDING_KINDS as ALLOWED_QUESTION_FINDING_KINDS,
)
from aippocampus_runtime.subconscious.job_validation import (
    QUESTION_TEXT_MAX_CHARS as QUESTION_TEXT_MAX_CHARS,
)
from aippocampus_runtime.subconscious.job_validation import (
    canonical_scope_labels as canonical_scope_labels,
)
from aippocampus_runtime.subconscious.job_validation import (
    compact_source_message_refs as compact_source_message_refs,
)
from aippocampus_runtime.subconscious.job_validation import (
    compact_string_list as compact_string_list,
)
from aippocampus_runtime.subconscious.job_validation import (
    estimate_finding_quality as estimate_finding_quality,
)
from aippocampus_runtime.subconscious.job_validation import (
    exact_message_refs_for_semantic_label as exact_message_refs_for_semantic_label,
)
from aippocampus_runtime.subconscious.job_validation import (
    finding_fingerprint as finding_fingerprint,
)
from aippocampus_runtime.subconscious.job_validation import (
    normalize_for_fingerprint as normalize_for_fingerprint,
)
from aippocampus_runtime.subconscious.job_validation import (
    normalize_ref_id as normalize_ref_id,
)
from aippocampus_runtime.subconscious.job_validation import (
    quality_bucket as quality_bucket,
)
from aippocampus_runtime.subconscious.job_validation import (
    refs_for_finding as refs_for_finding,
)
from aippocampus_runtime.subconscious.job_validation import (
    safe_nonnegative_int as safe_nonnegative_int,
)
from aippocampus_runtime.subconscious.job_validation import (
    scope_label_fields_from_source_refs as scope_label_fields_from_source_refs,
)
from aippocampus_runtime.subconscious.job_validation import (
    short_question_fallback as short_question_fallback,
)
from aippocampus_runtime.subconscious.job_validation import (
    validate_cognitive_map_fields as validate_cognitive_map_fields,
)
from aippocampus_runtime.subconscious.job_validation import (
    validate_findings as validate_findings,
)
from aippocampus_runtime.subconscious.job_validation import (
    validate_question_fields as validate_question_fields,
)
from aippocampus_runtime.subconscious.job_validation import (
    validate_semantic_scope_label_fields as validate_semantic_scope_label_fields,
)
from aippocampus_runtime.subconscious.job_validation import (
    validate_theme_candidate_fields as validate_theme_candidate_fields,
)
from aippocampus_runtime.subconscious.job_validation import (
    where_context_from_source_refs as where_context_from_source_refs,
)
