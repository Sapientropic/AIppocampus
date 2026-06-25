from __future__ import annotations


def upsert_concept(con, related, *, status):
    return (con, related, status)


def build_edges(related_terms, con):
    for related in related_terms:
        upsert_concept(con, related, status="staging")
