"""Shared query-term expansion for clean-source exact search surfaces."""

from __future__ import annotations

from aippocampus_runtime.recall.query_policy import cjk_query_sidecar_terms, split_query_terms


def search_query_terms(patterns: list[str]) -> list[str]:
    """Return exact-search terms with the same CJK sidecar used by recall.

    Search is the foreground "I remember the wording" fallback. For CJK text,
    a user can be one character off and still clearly point at the same source
    phrase, so keep search aligned with recall's measured ngram sidecar instead
    of making Chinese exact search strictly weaker than the recall route.
    """

    seen: set[str] = set()
    terms: list[str] = []
    for term in [
        *split_query_terms(patterns),
        *[
            sidecar
            for pattern in patterns
            for sidecar in cjk_query_sidecar_terms(str(pattern or ""))
        ],
    ]:
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms
