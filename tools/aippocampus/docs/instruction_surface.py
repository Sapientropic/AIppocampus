"""Instruction-surface inventory helpers for architecture debt checks."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterable
from pathlib import Path

INSTRUCTION_SURFACE_POLICY_DOC = (
    "docs/architecture/runtime/instruction-surface-policy.md"
)
INSTRUCTION_SURFACE_MARKER = "aippocampus-instruction-surface:"
INSTRUCTION_SURFACE_SCAN_PREFIXES = (
    "skills/aippocampus/scripts/aippocampus_runtime/source/",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/",
    "skills/aippocampus/scripts/aippocampus_runtime/update/",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/",
    "tests/aippocampus/",
)
INSTRUCTION_SURFACE_MIN_HITS = {
    "runtime": 3,
    "tests": 8,
}
INSTRUCTION_SURFACE_CLASSIFIED_FILES = {
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py": {
        "classification": "compact_projection_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns the compact recall card translation boundary; proof remains in "
            "detail/operator/tests, not default MCP payload expansion"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity.py": {
        "classification": "runtime_prompt_and_route_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns recall route/action selection text that later projections render"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/segment_search_extras.py": {
        "classification": "source_sidecar_boundary_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns source sidecar/read-model boundary strings; sidecars may guide "
            "search, while source-open proof stays in detail/tests/issue closeout"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/scheduler.py": {
        "classification": "lifecycle_scheduler_boundary_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns hook-safe scheduler boundary text; lifecycle foreground must "
            "stay fail-open and must not become a proof or job-output surface"
        ),
    },
    "tests/aippocampus/frontstage_assertions.py": {
        "classification": "test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns reusable compact-vs-detail assertions instead of duplicating "
            "foreground doctrine in payload tests"
        ),
    },
    "tests/aippocampus/test_architecture_boundaries.py": {
        "classification": "architecture_guard_test_owner",
        "owner": "#2636/#2651",
        "why": "owns repository-level architecture boundary tests.",
    },
}
COMPACT_DEBUG_FIELD_LITERALS = (
    "runtime_provenance",
    "source_anchor_gate",
    "operator_detail_command",
    "safe_next_actions",
    "weak_route_recovery_card",
    "apw_recovery_state",
    "last_recall_cache_available",
    "recall_selector_id",
    "route_count",
)
INSTRUCTION_SURFACE_TERMS = (
    "must",
    "should",
    "never",
    "always",
    "do not",
    "don't",
    "instruction",
    "prompt",
    "policy",
    "contract",
    "canonical",
    "claim_boundary",
    "cannot_claim",
    "foreground",
    "operator",
    "detail",
    "diagnostic",
    "source-backed",
    "source backed",
    "proof",
    "evidence",
)


def repo_relative(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def instruction_surface_scan_scope(rel_path: str) -> bool:
    return rel_path.startswith(INSTRUCTION_SURFACE_SCAN_PREFIXES)


def instruction_surface_threshold(rel_path: str) -> int:
    return (
        INSTRUCTION_SURFACE_MIN_HITS["tests"]
        if rel_path.startswith("tests/aippocampus/")
        else INSTRUCTION_SURFACE_MIN_HITS["runtime"]
    )


def instruction_surface_classification(
    rel_path: str,
    text: str,
) -> dict[str, object] | None:
    """Return the owner classification for instruction-like text in a file."""

    explicit = INSTRUCTION_SURFACE_CLASSIFIED_FILES.get(rel_path)
    if explicit:
        return {
            "path": rel_path,
            "source": "central_classification",
            "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
            **explicit,
        }
    if INSTRUCTION_SURFACE_MARKER in text:
        line = next(
            (
                index
                for index, value in enumerate(text.splitlines(), start=1)
                if INSTRUCTION_SURFACE_MARKER in value
            ),
            0,
        )
        return {
            "path": rel_path,
            "source": "inline_marker",
            "classification": "local_marked_boundary",
            "line": line,
            "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
        }
    return None


def instruction_like_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    if len(normalized) < 12:
        return False
    if " " not in normalized:
        return False
    if normalized.startswith(("def ", "from ", "import ")):
        return False
    if re.fullmatch(r"[\w./:\\#-]+", normalized):
        return False
    return any(term in normalized for term in INSTRUCTION_SURFACE_TERMS)


def instruction_comment_hits(text: str) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except tokenize.TokenError:
        return hits
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        comment = token.string.lstrip("#").strip()
        if instruction_like_text(comment):
            hits.append(
                {
                    "line": int(token.start[0]),
                    "kind": "comment",
                    "text": comment[:160],
                }
            )
    return hits


def instruction_string_hits(path: Path, text: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    hits: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value.strip()
        if instruction_like_text(value):
            hits.append(
                {
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "kind": "string",
                    "text": re.sub(r"\s+", " ", value)[:160],
                }
            )
    return hits


def instruction_surface_hits(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    hits = [*instruction_comment_hits(text), *instruction_string_hits(path, text)]
    return sorted(hits, key=lambda item: (int(item["line"]), str(item["kind"])))


def instruction_surface_inventory(
    paths: Iterable[Path],
    *,
    repo_root: Path,
) -> dict[str, object]:
    occurrences: list[dict[str, object]] = []
    classified_files: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda item: repo_relative(repo_root, item)):
        rel_path = repo_relative(repo_root, path)
        if not instruction_surface_scan_scope(rel_path):
            continue
        text = path.read_text(encoding="utf-8")
        hits = instruction_surface_hits(path)
        if not hits:
            continue
        classification = instruction_surface_classification(rel_path, text)
        item = {
            "path": rel_path,
            "hit_count": len(hits),
            "classification": classification,
            "sample_hits": hits[:5],
        }
        occurrences.append(item)
        if classification:
            classified_files.append(item)
    occurrences.sort(key=lambda item: (-int(item["hit_count"]), str(item["path"])))
    return {
        "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
        "summary": {
            "file_count": len(occurrences),
            "hit_count": sum(int(item["hit_count"]) for item in occurrences),
            "classified_file_count": len(classified_files),
            "unclassified_file_count": len(occurrences) - len(classified_files),
        },
        "top_files": occurrences[:20],
        "classified_files": classified_files,
        "note": (
            "Instruction-like text is inventory pressure, not automatic wrongdoing. "
            "Changed-surface warnings require an owner classification or inline "
            "local-boundary marker."
        ),
    }


def changed_file_instruction_surface(
    path: Path,
    *,
    repo_root: Path,
) -> dict[str, object] | None:
    rel_path = repo_relative(repo_root, path)
    if not instruction_surface_scan_scope(rel_path):
        return None
    text = path.read_text(encoding="utf-8")
    hits = instruction_surface_hits(path)
    threshold = instruction_surface_threshold(rel_path)
    if len(hits) < threshold:
        return None
    return {
        "path": rel_path,
        "hit_count": len(hits),
        "threshold": threshold,
        "classification": instruction_surface_classification(rel_path, text),
        "sample_hits": hits[:5],
    }


def changed_file_instruction_surface_warning(
    item: dict[str, object],
) -> dict[str, object] | None:
    if item.get("classification"):
        return None
    return {
        "code": "changed_surface_instruction_surface_unclassified",
        "path": item["path"],
        "hit_count": item["hit_count"],
        "threshold": item["threshold"],
        "sample_hits": item["sample_hits"],
        "acceptance_bearing": True,
        "message": (
            "Touched hot-path/test file contains instruction-like comments or strings; "
            "classify them as local invariant, canonical-doc pointer, runtime prompt "
            "owner, detail/operator diagnostics, test contract, or delete compensatory noise."
        ),
        "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
    }
