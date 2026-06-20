"""Information-architecture pressure diagnostics for repository docs."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypedDict

Severity = Literal["failure", "warning"]

DOCS_README_WORD_BUDGET = 1600
MISSING_INDEX_MARKDOWN_THRESHOLD = 5
FOLDER_PRESSURE_MARKDOWN_THRESHOLD = 12
ROLE_STATUS_FOLDERS = {"architecture", "evidence", "planning", "research"}
ROLE_STATUS_RE = re.compile(r"^(role|status|state|文档状态)\s*[:：]", re.IGNORECASE)
DATED_REPORT_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ARCHIVE_POINTER_MARKERS = (
    "current owner",
    "current contract",
    "current queue",
    "current executable work",
    "docs/README.md",
    "../README.md",
    "roadmap",
    "current claims",
    "readiness",
)
FOLDER_PRESSURE_OWNER_MARKERS = (
    "folder pressure owner:",
    "folder pressure next action:",
)


@dataclass(frozen=True)
class IADiagnostic:
    severity: Severity
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class IAReport(TypedDict):
    failures: list[dict[str, str]]
    warnings: list[dict[str, str]]
    metrics: dict[str, object]


def _repo_rel(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _has_role_or_status(text: str) -> bool:
    return any(ROLE_STATUS_RE.match(line.strip()) for line in text.splitlines()[:12])


def _is_archived_text(text: str) -> bool:
    return any(
        re.match(r"^(state|status|role)\s*[:：]\s*archiv", line.strip(), re.IGNORECASE)
        for line in text.splitlines()[:12]
    )


def _is_dated_report(path: Path) -> bool:
    return bool(DATED_REPORT_RE.search(path.name))


def _archive_has_current_pointer(text: str) -> bool:
    early = "\n".join(text.splitlines()[:40]).casefold()
    return any(marker.casefold() in early for marker in ARCHIVE_POINTER_MARKERS)


def _folder_pressure_is_owned(folder: Path) -> bool:
    readme = folder / "README.md"
    if not readme.exists():
        return False
    early = "\n".join(readme.read_text(encoding="utf-8").splitlines()[:40]).casefold()
    return all(marker in early for marker in FOLDER_PRESSURE_OWNER_MARKERS)


def information_architecture_diagnostics(
    repo_root: Path,
    *,
    allowed_root_markdown: set[str],
    allowed_root_directories: set[str],
) -> IAReport:
    docs_dir = repo_root / "docs"
    diagnostics: list[IADiagnostic] = []
    folder_counts: dict[str, int] = {}
    docs_readme_words = 0

    if not docs_dir.exists():
        return {
            "failures": [],
            "warnings": [],
            "metrics": {
                "docs_readme_words": docs_readme_words,
                "folder_markdown_counts": folder_counts,
            },
        }

    readme = docs_dir / "README.md"
    if readme.exists():
        docs_readme_words = _word_count(readme.read_text(encoding="utf-8"))
        if docs_readme_words > DOCS_README_WORD_BUDGET:
            diagnostics.append(
                IADiagnostic(
                    severity="warning",
                    code="docs_readme_reader_hub_pressure",
                    path="docs/README.md",
                    message=(
                        "docs/README.md has "
                        f"{docs_readme_words} words; keep the reader hub <= "
                        f"{DOCS_README_WORD_BUDGET} or move detail to child indexes"
                    ),
                )
            )

    for path in sorted(docs_dir.glob("*.md")):
        if path.name not in allowed_root_markdown:
            diagnostics.append(
                IADiagnostic(
                    severity="failure",
                    code="docs_root_markdown_sprawl",
                    path=f"docs/{path.name}",
                    message=(
                        f"docs root has unclassified markdown file: docs/{path.name}; "
                        "move it under docs/architecture, docs/guides, docs/evidence, "
                        "docs/planning, or docs/research"
                    ),
                )
            )
    for path in sorted(item for item in docs_dir.iterdir() if item.is_dir()):
        if path.name not in allowed_root_directories:
            diagnostics.append(
                IADiagnostic(
                    severity="failure",
                    code="docs_root_directory_sprawl",
                    path=f"docs/{path.name}",
                    message=(
                        f"docs root has unclassified directory: docs/{path.name}; "
                        "use docs/architecture, docs/guides, docs/evidence, "
                        "docs/planning, docs/research, or docs/archive"
                    ),
                )
            )

    for folder in sorted(path for path in docs_dir.rglob("*") if path.is_dir()):
        markdown_files = sorted(folder.glob("*.md"))
        if not markdown_files:
            continue
        rel_folder = _repo_rel(repo_root, folder)
        folder_counts[rel_folder] = len(markdown_files)
        if folder == docs_dir:
            continue
        if len(markdown_files) >= MISSING_INDEX_MARKDOWN_THRESHOLD and not (
            folder / "README.md"
        ).exists():
            diagnostics.append(
                IADiagnostic(
                    severity="warning",
                    code="docs_folder_missing_index",
                    path=rel_folder,
                    message=(
                        f"{rel_folder} has {len(markdown_files)} Markdown files "
                        "but no local README.md; add an index or split/archive the folder"
                    ),
                )
            )
        if (
            len(markdown_files) >= FOLDER_PRESSURE_MARKDOWN_THRESHOLD
            and not _folder_pressure_is_owned(folder)
        ):
            diagnostics.append(
                IADiagnostic(
                    severity="warning",
                    code="docs_folder_file_count_pressure",
                    path=rel_folder,
                    message=(
                        f"{rel_folder} has {len(markdown_files)} Markdown files; "
                        "verify the local README keeps reader paths clear"
                    ),
                )
            )

    for folder_name in sorted(ROLE_STATUS_FOLDERS):
        folder = docs_dir / folder_name
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name == "README.md" or _is_dated_report(path):
                continue
            text = path.read_text(encoding="utf-8")
            if _is_archived_text(text):
                continue
            if not _has_role_or_status(text):
                rel = _repo_rel(repo_root, path)
                diagnostics.append(
                    IADiagnostic(
                        severity="warning",
                        code="active_doc_missing_role_status",
                        path=rel,
                        message=(
                            f"{rel} lacks a Role/Status line near the top; "
                            "add one or mark the note archived"
                        ),
                    )
                )

    archive_dir = docs_dir / "archive"
    if archive_dir.exists():
        for path in sorted(archive_dir.rglob("*.md")):
            if path.name == "README.md":
                continue
            text = path.read_text(encoding="utf-8")
            if not _archive_has_current_pointer(text):
                rel = _repo_rel(repo_root, path)
                diagnostics.append(
                    IADiagnostic(
                        severity="warning",
                        code="archive_doc_missing_current_pointer",
                        path=rel,
                        message=(
                            f"{rel} is archived but lacks an early pointer back "
                            "to a current owner"
                        ),
                    )
                )

    return {
        "failures": [
            diagnostic.to_dict() for diagnostic in diagnostics if diagnostic.severity == "failure"
        ],
        "warnings": [
            diagnostic.to_dict() for diagnostic in diagnostics if diagnostic.severity == "warning"
        ],
        "metrics": {
            "docs_readme_words": docs_readme_words,
            "docs_readme_word_budget": DOCS_README_WORD_BUDGET,
            "folder_markdown_counts": dict(sorted(folder_counts.items())),
            "missing_index_markdown_threshold": MISSING_INDEX_MARKDOWN_THRESHOLD,
            "folder_pressure_markdown_threshold": FOLDER_PRESSURE_MARKDOWN_THRESHOLD,
        },
    }


def docs_health_ia_payload(
    repo_root: Path,
    *,
    allowed_root_markdown: set[str],
    allowed_root_directories: set[str],
) -> tuple[list[str], dict[str, object]]:
    report = information_architecture_diagnostics(
        repo_root,
        allowed_root_markdown=allowed_root_markdown,
        allowed_root_directories=allowed_root_directories,
    )
    return (
        [item["message"] for item in report["failures"]],
        {
            "information_architecture": report["metrics"],
            "information_architecture_failure_count": len(report["failures"]),
            "information_architecture_warning_count": len(report["warnings"]),
            "_warnings": [item["message"] for item in report["warnings"]],
            "_diagnostics": {
                "information_architecture": {
                    "failures": report["failures"],
                    "warnings": report["warnings"],
                }
            },
        },
    )
