from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = REPO_ROOT / "docs" / "research" / "memory-system-pain-taxonomy.md"


def test_memory_system_taxonomy_records_rolling_public_incident_corpus() -> None:
    text = TAXONOMY.read_text(encoding="utf-8")

    for phrase in (
        "Rolling Public Incident Corpus",
        "3-day rolling sweep",
        "rohitg00/agentmemory#843",
        "rohitg00/agentmemory#926",
        "rohitg00/agentmemory#930",
        "rohitg00/agentmemory#911",
        "existing_guard_or_issue",
        "public metadata and short failure-class summaries only",
    ):
        assert phrase in text
