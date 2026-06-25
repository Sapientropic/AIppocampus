from __future__ import annotations


def mine(candidates, raw_stats, con):
    rows = []
    for candidate in candidates:
        for other in raw_stats.values():
            rows.extend(sorted(raw_stats.values()))
            con.execute("SELECT 1", (candidate, other))
    return rows
