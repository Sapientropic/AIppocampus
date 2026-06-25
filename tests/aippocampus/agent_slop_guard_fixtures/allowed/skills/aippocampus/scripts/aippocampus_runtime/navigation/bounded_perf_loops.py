from __future__ import annotations

MAX_RELATED_PER_TERM = 8


def report(candidates, raw_stats, resolver, con, limit):
    counts = {}
    for status in ("active", "parked"):
        counts[status] = counts.get(status, 0) + 1
    for candidate in candidates[:limit]:
        counts[candidate] = counts.get(candidate, 0) + 1
    for item in raw_stats[:limit]:
        rows = list(item.get("sample_terms") or [])
        counts[str(item)] = len(rows)
    for related in raw_stats[:MAX_RELATED_PER_TERM]:
        resolver.resolve(con, related, status="staging")
    return {"diagnostic": counts}
