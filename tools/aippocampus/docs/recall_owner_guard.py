"""Docs-health guard for recall runtime owner classification.

The owner map is an inventory for existing flat recall modules, not permission
to add another top-level file. The guard therefore treats the legacy flat-file
inventory as sealed: new runtime code should live under an owner subpackage, and
the rare flat exception must carry owner/removal/default-import metadata.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

OWNER_MAP = "docs/architecture/recall/owner-map.md"
RECALL_RUNTIME_DIR = "skills/aippocampus/scripts/aippocampus_runtime/recall"
REQUIRED_OWNER_HEADINGS = {
    "### Prompt Recall",
    "### Ambient",
    "### Active Recall And Locks",
    "### APW And Route Walking",
    "### Semantic",
    "### Source Open And Deepen",
    "### Foreground Projection",
    "### Scoring And Retrieval",
    "### Feedback",
    "### Continuity And Life Cues",
    "### Background Findings",
    "### Diagnostics And Recovery",
}
REQUIRED_FEEDBACK_PACKAGE_TERMS = {
    "`feedback/__init__.py`",
    "`feedback/associative_path.py`",
    "`feedback/capture.py`",
    "`feedback/events.py`",
    "`feedback/outcome.py`",
    "No flat compatibility wrappers",
}
FLAT_PY_RE = re.compile(r"`(?P<name>[A-Za-z_][A-Za-z0-9_]*\.py)`")
LEGACY_COUNT_RE = re.compile(r"^\s*-\s*sealed_count:\s*(?P<count>\d+)\s*$", re.M)
LEGACY_SHA_RE = re.compile(r"^\s*-\s*sealed_sha256:\s*(?P<sha>[0-9a-f]{64})\s*$", re.M)
CURRENT_FLAT_HEADING_RE = re.compile(r"^Current flat files:\s*$")
MARKDOWN_HEADING_RE = re.compile(r"^#{2,6}\s+")
EXCEPTION_ROW_RE = re.compile(r"^\|\s*`(?P<file>[A-Za-z_][A-Za-z0-9_]*\.py)`\s*\|(?P<rest>.*)\|\s*$")
EXCEPTION_KINDS = {"entrypoint", "temporary_compatibility_wrapper"}
OWNER_FILE_RE = re.compile(r"^\s*-\s*`(?P<path>[^`]+\.py)`\s*$")


def _flat_recall_modules(repo_root: Path) -> set[str]:
    recall_dir = repo_root / RECALL_RUNTIME_DIR
    if not recall_dir.exists():
        return set()
    return {
        path.name
        for path in recall_dir.glob("*.py")
        if path.name != "__init__.py"
    }


def _documented_flat_modules(text: str) -> set[str]:
    return {match.group("name") for match in FLAT_PY_RE.finditer(text)}


def _legacy_flat_modules(text: str) -> set[str]:
    """Return names from the sealed legacy `Current flat files` inventory.

    Only these sections are part of the historical flat-module baseline. Names
    in the explicit exception table are intentionally excluded so a rare wrapper
    can be reviewed without mutating the sealed legacy hash.
    """

    modules: set[str] = set()
    in_current_flat_files = False
    for line in text.splitlines():
        if CURRENT_FLAT_HEADING_RE.match(line):
            in_current_flat_files = True
            continue
        if in_current_flat_files and MARKDOWN_HEADING_RE.match(line):
            in_current_flat_files = False
        if not in_current_flat_files:
            continue
        match = FLAT_PY_RE.search(line)
        if match:
            modules.add(match.group("name"))
    return modules


def _flat_inventory_hash(modules: set[str]) -> str:
    payload = "\n".join(sorted(modules)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sealed_inventory(text: str) -> tuple[int | None, str | None]:
    count_match = LEGACY_COUNT_RE.search(text)
    sha_match = LEGACY_SHA_RE.search(text)
    count = int(count_match.group("count")) if count_match else None
    sha = sha_match.group("sha") if sha_match else None
    return count, sha


def _flat_exceptions(text: str) -> tuple[set[str], list[str]]:
    """Parse the explicit exception table for new flat recall files."""

    exceptions: set[str] = set()
    issues: list[str] = []
    for line in text.splitlines():
        match = EXCEPTION_ROW_RE.match(line)
        if not match:
            continue
        name = match.group("file")
        if name.lower() == "file.py":
            continue
        cells = [cell.strip() for cell in match.group("rest").split("|")]
        if len(cells) < 4:
            issues.append(
                f"flat recall exception missing owner/removal/default-import metadata: {name}"
            )
            continue
        kind, owner, removal, default_import = cells[:4]
        if set(kind) <= {"-", ":"}:
            continue
        missing_fields = [
            label
            for label, value in (
                ("kind", kind),
                ("owner", owner),
                ("removal condition", removal),
                ("default import guidance", default_import),
            )
            if not value or value in {"-", "n/a", "N/A"}
        ]
        if kind not in EXCEPTION_KINDS:
            issues.append(
                f"flat recall exception has unsupported kind for {name}: {kind}"
            )
            continue
        if missing_fields:
            issues.append(
                "flat recall exception missing "
                f"{', '.join(missing_fields)} metadata: {name}"
            )
            continue
        exceptions.add(name)
    return exceptions, issues


def _owner_family_inventory(text: str) -> list[dict[str, object]]:
    families: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    section: str | None = None
    for line in text.splitlines():
        if line.startswith("### "):
            if current is not None:
                families.append(current)
            current = {
                "owner": line.removeprefix("### ").strip(),
                "flat_files": [],
                "owner_package_files": [],
            }
            section = None
            continue
        if current is None:
            continue
        if line.strip() == "Current flat files:":
            section = "flat_files"
            continue
        if line.strip() == "Current owner package:":
            section = "owner_package_files"
            continue
        if MARKDOWN_HEADING_RE.match(line):
            section = None
            continue
        file_match = OWNER_FILE_RE.match(line)
        if section and file_match:
            cast_list = current[section]
            if isinstance(cast_list, list):
                cast_list.append(file_match.group("path"))
    if current is not None:
        families.append(current)
    for family in families:
        flat_files = family.get("flat_files")
        package_files = family.get("owner_package_files")
        family["flat_file_count"] = len(flat_files) if isinstance(flat_files, list) else 0
        family["owner_package_file_count"] = (
            len(package_files) if isinstance(package_files, list) else 0
        )
    return families


def _int_inventory_value(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def recall_fragmentation_inventory(repo_root: Path) -> dict[str, object]:
    """Return a compact, auditable inventory of recall owner fragmentation."""

    owner_map = repo_root / OWNER_MAP
    if not owner_map.exists():
        return {
            "kind": "recall_fragmentation_inventory",
            "owner_map": OWNER_MAP,
            "issues": [f"missing recall owner map: {OWNER_MAP}"],
        }
    text = owner_map.read_text(encoding="utf-8")
    families = _owner_family_inventory(text)
    legacy_modules = _legacy_flat_modules(text)
    flat_modules = _flat_recall_modules(repo_root)
    return {
        "kind": "recall_fragmentation_inventory",
        "owner_map": OWNER_MAP,
        "new_flat_files_rejected_by_default": True,
        "sealed_legacy_flat_count": len(legacy_modules),
        "current_flat_module_count": len(flat_modules),
        "owner_package_file_count": sum(
            _int_inventory_value(family.get("owner_package_file_count"))
            for family in families
        ),
        "unclassified_flat_modules": sorted(flat_modules - legacy_modules),
        "owner_families": families,
        "issues": recall_owner_map_issues(repo_root),
    }


def recall_owner_map_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    owner_map = repo_root / OWNER_MAP
    if not owner_map.exists():
        return [f"missing recall owner map: {OWNER_MAP}"]

    text = owner_map.read_text(encoding="utf-8")
    for heading in sorted(REQUIRED_OWNER_HEADINGS):
        if heading not in text:
            issues.append(f"recall owner map missing owner family: {heading.removeprefix('### ')}")
    for term in sorted(REQUIRED_FEEDBACK_PACKAGE_TERMS):
        if term not in text:
            issues.append(f"recall owner map missing feedback boundary term: {term}")

    legacy_modules = _legacy_flat_modules(text)
    sealed_count, sealed_sha = _sealed_inventory(text)
    if sealed_count is None or sealed_sha is None:
        issues.append(
            "recall owner map missing sealed legacy flat inventory count/hash"
        )
    else:
        actual_count = len(legacy_modules)
        actual_sha = _flat_inventory_hash(legacy_modules)
        if actual_count != sealed_count or actual_sha != sealed_sha:
            issues.append(
                "recall owner map legacy flat inventory changed; "
                "new recall files must use owner subpackages or explicit flat exception metadata"
            )

    flat_exceptions, exception_issues = _flat_exceptions(text)
    issues.extend(exception_issues)

    flat_modules = _flat_recall_modules(repo_root)
    documented = _documented_flat_modules(text)
    allowed_flat_modules = legacy_modules | flat_exceptions
    missing = sorted(flat_modules - allowed_flat_modules)
    stale = sorted(
        name
        for name in documented - flat_modules
        if not (repo_root / RECALL_RUNTIME_DIR / "feedback" / name).exists()
    )
    for name in missing:
        issues.append(
            "new flat recall module rejected by default; use an owner subpackage "
            f"or add explicit entrypoint/wrapper metadata in {OWNER_MAP}: {name}"
        )
    for name in sorted(flat_exceptions - flat_modules):
        issues.append(
            f"recall owner map lists missing flat exception file: {name}"
        )
    for name in stale:
        issues.append(
            f"recall owner map lists missing flat module or package file: {name}"
        )
    return issues


__all__ = ["recall_fragmentation_inventory", "recall_owner_map_issues"]
