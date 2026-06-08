#!/usr/bin/env python3
"""Structure and temporal recall lanes for local source-backed search.

These helpers keep D5/D6 cue parsing and feature-table scoring out of the main
SQLite/FTS retrieval coordinator. Scores here are ranking hints only; callers
must still reopen source-backed messages before treating a hit as evidence.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

STRUCTURE_BOOL_COLUMNS = ("has_code_block", "has_warning", "has_list", "has_table", "is_final")
STRUCTURE_FEATURE_WEIGHTS = {
    "has_code_block": 18.0,
    "has_warning": 12.0,
    "has_list": 8.0,
    "has_table": 12.0,
    "is_final": 4.0,
}
TEMPORAL_AFFINITY_MAX = 28.0


def sqlite_has_table(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'virtual table') AND name = ?",
        (name,),
    ).fetchone()
    return bool(row)


def parse_structure_cues(prompt: str) -> dict[str, bool]:
    """Parse explicit structural recall cues into hot feature column names."""

    low = prompt.casefold()
    cues: dict[str, bool] = {}
    if re.search(r"code\s*(block|fence)|```|代码块|代码围栏", low):
        cues["has_code_block"] = True
    if re.search(r"\bwarning\b|\bcaution\b|\bwarn\b|⚠|注意|警告|重要", low):
        cues["has_warning"] = True
    if re.search(r"\b(list|bullet|checklist)\b|列表|清单", low):
        cues["has_list"] = True
    if re.search(r"\btable\b|表格|\|\s*---", low):
        cues["has_table"] = True
    if re.search(r"\bfinal\s+answer\b|\bfinal\b|最终答案|最后回答", low):
        cues["is_final"] = True
    return cues


def parse_datetime_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            parsed = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _resolve_now(now: datetime | str | None = None) -> datetime:
    if isinstance(now, datetime):
        parsed = now
    elif now is not None:
        parsed = parse_datetime_utc(now) or datetime.now(timezone.utc)
    else:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _month_start(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + months
    year = month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _relative_month_cue(
    *,
    now: datetime | str | None,
    months_ago: int,
    cue_kind: str,
    confidence: float,
    vague: bool = False,
    span_months: int = 1,
) -> dict[str, Any]:
    current_month = _month_start(_resolve_now(now))
    target = _add_months(current_month, -months_ago)
    start = _add_months(target, -1) if vague else target
    end = _add_months(target, span_months + (1 if vague else 0))
    return {
        "window_start": iso_z(start),
        "window_end": iso_z(end),
        "confidence": confidence,
        "cue_kind": cue_kind,
        "hard_filter": False,
    }


def parse_temporal_cue(
    prompt: str, *, now: datetime | str | None = None
) -> dict[str, Any] | None:
    """Parse a first deterministic subset of D6 time-window cues.

    Vague cues are ranking priors, not hard filters. Search lanes may add
    in-window candidates, but existing text candidates remain visible so source
    evidence is not hidden to make time-only recall look cleaner than it is.
    """

    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", prompt)
    if not match:
        low = prompt.casefold()
        if re.search(r"\blast\s+month\b|上个月|上月", low):
            return _relative_month_cue(
                now=now,
                months_ago=1,
                cue_kind="relative_last_month",
                confidence=0.78,
            )
        if re.search(r"半年前|半年之前|\bhalf\s+a\s+year\s+ago\b", low):
            return _relative_month_cue(
                now=now,
                months_ago=6,
                cue_kind="relative_half_year",
                confidence=0.68,
            )
        if re.search(
            r"\b(?:about|around|roughly|approx(?:imately)?)?\s*(?:six|6)\s+months?\s+ago\b",
            low,
        ):
            vague = bool(re.search(r"\b(?:about|around|roughly|approx(?:imately)?)\b", low))
            return _relative_month_cue(
                now=now,
                months_ago=6,
                cue_kind="relative_half_year",
                confidence=0.56 if vague else 0.68,
                vague=vague,
            )
        if re.search(r"几个月前|数月前|好几个月前|\b(?:a\s+few|several)\s+months?\s+ago\b", low):
            current_month = _month_start(_resolve_now(now))
            return {
                "window_start": iso_z(_add_months(current_month, -4)),
                "window_end": iso_z(_add_months(current_month, -1)),
                "confidence": 0.46,
                "cue_kind": "relative_few_months",
                "hard_filter": False,
            }
        return None
    day = parse_datetime_utc(match.group(1))
    if day is None:
        return None

    low = prompt.casefold()
    vague = any(
        token in low for token in ("around", "about", "approx", "roughly", "大概", "左右")
    )
    if any(token in low for token in ("late at night", "深夜", "late night")):
        start = day.replace(hour=20, minute=0, second=0)
        end = (day + timedelta(days=1)).replace(hour=4, minute=0, second=0)
        return {
            "window_start": iso_z(start),
            "window_end": iso_z(end),
            "confidence": 0.72 if vague else 0.84,
            "cue_kind": "date_time_of_day",
            "hard_filter": False,
        }
    if any(token in low for token in ("evening", "night", "晚上", "夜里")):
        start = day.replace(hour=18, minute=0, second=0)
        end = (day + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        return {
            "window_start": iso_z(start),
            "window_end": iso_z(end),
            "confidence": 0.68 if vague else 0.8,
            "cue_kind": "date_time_of_day",
            "hard_filter": False,
        }
    if vague:
        return {
            "window_start": iso_z(day - timedelta(days=1)),
            "window_end": iso_z(day + timedelta(days=2)),
            "confidence": 0.6,
            "cue_kind": "date_vague",
            "hard_filter": False,
        }
    return {
        "window_start": iso_z(day),
        "window_end": iso_z(day + timedelta(days=1)),
        "confidence": 0.9,
        "cue_kind": "date_exact",
        "hard_filter": True,
    }


def load_message_feature(con: sqlite3.Connection, row_id: int) -> sqlite3.Row | None:
    if not sqlite_has_table(con, "message_features"):
        return None
    try:
        return con.execute(
            "SELECT * FROM message_features WHERE message_id = ?",
            (row_id,),
        ).fetchone()
    except sqlite3.Error:
        return None


def structure_signals(
    feature: sqlite3.Row | None, structure_cues: dict[str, bool] | None
) -> dict[str, Any]:
    if not feature or not structure_cues:
        return {}
    matched: dict[str, bool] = {}
    score = 0.0
    for column in STRUCTURE_BOOL_COLUMNS:
        if not structure_cues.get(column):
            continue
        if bool(int(feature[column] or 0)):
            matched[column] = True
            score += STRUCTURE_FEATURE_WEIGHTS[column]
    if not matched:
        return {}
    return {
        "structure_match_score": round(score, 3),
        "structure_signals": matched,
    }


def temporal_affinity_score(
    row: sqlite3.Row,
    feature: sqlite3.Row | None,
    temporal_cue: dict[str, Any] | None,
) -> float:
    if not temporal_cue:
        return 0.0
    timestamp = None
    if feature is not None:
        timestamp = parse_datetime_utc(feature["active_timestamp"])
    timestamp = timestamp or parse_datetime_utc(row["timestamp"])
    start = parse_datetime_utc(temporal_cue.get("window_start"))
    end = parse_datetime_utc(temporal_cue.get("window_end"))
    if timestamp is None or start is None or end is None or end <= start:
        return 0.0
    confidence = max(0.0, min(1.0, float(temporal_cue.get("confidence") or 0.0)))
    if start <= timestamp <= end:
        return round(TEMPORAL_AFFINITY_MAX * confidence, 3)
    center = start + (end - start) / 2
    distance_days = abs((timestamp - center).total_seconds()) / 86400.0
    window_days = max((end - start).total_seconds() / 86400.0, 0.25)
    # Out-of-window matches keep a tiny decaying prior. This preserves vague
    # time cues as ranking signals without hiding text/source candidates.
    decayed = (TEMPORAL_AFFINITY_MAX * 0.25 * confidence) / (
        1.0 + distance_days / window_days
    )
    return round(decayed, 3)


def temporal_signals(
    row: sqlite3.Row,
    feature: sqlite3.Row | None,
    temporal_cue: dict[str, Any] | None,
) -> dict[str, Any]:
    if not temporal_cue:
        return {}
    score = temporal_affinity_score(row, feature, temporal_cue)
    if score <= 0.0:
        return {}
    return {
        "temporal_affinity_score": score,
        "temporal_cue_kind": temporal_cue.get("cue_kind") or "",
        "temporal_window_start": temporal_cue.get("window_start") or "",
        "temporal_window_end": temporal_cue.get("window_end") or "",
    }


def search_structure_time_connection(
    con: sqlite3.Connection,
    message_columns_sql: str,
    structure_cues: dict[str, bool] | None,
    temporal_cue: dict[str, Any] | None,
    *,
    candidate_limit: int,
) -> list[sqlite3.Row]:
    if not sqlite_has_table(con, "message_features"):
        return []
    where: list[str] = []
    params: list[Any] = []
    for column in STRUCTURE_BOOL_COLUMNS:
        if structure_cues and structure_cues.get(column):
            where.append(f"f.{column} = 1")
    if temporal_cue:
        start = temporal_cue.get("window_start")
        end = temporal_cue.get("window_end")
        if start and end:
            where.append("(f.active_timestamp >= ? AND f.active_timestamp <= ?)")
            params.extend([start, end])
    if not where:
        return []
    try:
        return con.execute(
            f"""
            SELECT {message_columns_sql}
            FROM message_features f
            JOIN messages m ON m.id = f.message_id
            WHERE {" OR ".join(where)}
            ORDER BY m.id
            LIMIT ?
            """,
            [*params, candidate_limit],
        ).fetchall()
    except sqlite3.Error:
        return []
