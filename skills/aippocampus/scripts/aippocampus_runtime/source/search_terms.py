"""Shared query-term expansion for clean-source exact search surfaces."""

from __future__ import annotations

import re

from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    SENSITIVE_ASSIGNMENT_RE,
    SENSITIVE_VALUE_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.recall.query_policy import cjk_query_sidecar_terms, split_query_terms
from aippocampus_runtime.source.relationship_origin import relationship_origin_expansion_terms

_REDACTION_ARTIFACT_RE = re.compile(
    r"<(?:local-path-redacted|sensitive-value-redacted|redacted:[^>]+|path-anchor[^>]*)>"
)


def searchable_query_text(value: str) -> str:
    """Return cue text safe for retrieval, without public-output redaction artifacts.

    Public projections preserve some redaction context for humans. Retrieval
    must not treat that context as evidence: local paths, credential keys, and
    redaction markers are high-weight noise that can block the real source cue.
    """

    # Public redaction intentionally preserves auth-bearing key names such as
    # "SECRET_TOKEN=". Search queries need the opposite behavior: credential
    # assignments are not useful anchors, and letting the key survive can
    # outvote the real cue. Drop the whole assignment before exact-search term
    # generation, then apply the public redactors for paths and standalone keys.
    without_sensitive_assignments = SENSITIVE_ASSIGNMENT_RE.sub(" ", str(value or ""))
    redacted = str(
        redact_sensitive_values(redact_private_paths(without_sensitive_assignments)) or ""
    )
    redacted = _REDACTION_ARTIFACT_RE.sub(" ", redacted)
    return (
        redacted.replace(LOCAL_PATH_REDACTION, " ")
        .replace(SENSITIVE_VALUE_REDACTION, " ")
        .replace("<", " ")
        .replace(">", " ")
        .strip()
    )


def search_query_terms(patterns: list[str]) -> list[str]:
    """Return exact-search terms with the same CJK sidecar used by recall.

    Search is the foreground "I remember the wording" fallback. For CJK text,
    a user can be one character off and still clearly point at the same source
    phrase, so keep search aligned with recall's measured ngram sidecar instead
    of making Chinese exact search strictly weaker than the recall route.
    """

    seen: set[str] = set()
    terms: list[str] = []
    searchable_patterns = [searchable_query_text(str(pattern or "")) for pattern in patterns]
    for term in [
        *split_query_terms(searchable_patterns),
        *[
            sidecar
            for pattern in searchable_patterns
            for sidecar in cjk_query_sidecar_terms(str(pattern or ""))
        ],
        *[
            term
            for pattern in searchable_patterns
            for term in relationship_origin_expansion_terms(str(pattern or ""))
        ],
    ]:
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms
