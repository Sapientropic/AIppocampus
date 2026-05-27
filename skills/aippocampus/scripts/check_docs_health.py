#!/usr/bin/env python3
"""Lightweight guardrails for keeping AIppocampus docs maintainable."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from build_clean_source import SCOPE_LABEL_ORDER, infer_scope_labels


MAX_SKILL_LINES = 220
MAX_SKILL_WORDS = 2600
MAX_SKILL_CODE_FENCES = 2

REQUIRED_REFERENCES = [
    "ambient-hooks.md",
    "retrieval-and-storage.md",
    "maintenance-and-operations.md",
    "subconscious-jobs.md",
]

REQUIRED_PROJECT_DOCS = [
    "docs/README.md",
    "docs/roadmap.md",
    "docs/stage-0-5-readiness.md",
    "docs/next-iteration-plan.md",
    "docs/gb-scale-roadmap.md",
    "docs/wukong-mining-notes.md",
    "docs/technical-differentiation-analysis.md",
]

REQUIRED_PUBLIC_READINESS_DOCS = [
    "CONTRIBUTING.md",
    "docs/architecture-overview.md",
    "docs/install-guide.md",
    "docs/demo-scenarios.md",
    "docs/privacy-security-checklist.md",
    "docs/public-readiness-verification.md",
]

PUBLIC_EXAMPLE_BUNDLE_FILES = [
    "bundle_manifest.json",
    "handoff.md",
    "clean-source/manifest.json",
    "clean-source/messages.jsonl",
    "clean-source/turns.jsonl",
    "clean-source/semantic-scope-labels.jsonl",
    "index/manifest.json",
    "index/messages.jsonl",
    "index/graph.json",
    "registry/threads.json",
    "registry/subconscious_jobs.jsonl",
]
PUBLIC_EXAMPLE_BUNDLE_ALLOWED_FILES = set(PUBLIC_EXAMPLE_BUNDLE_FILES)

REQUIRED_PRIVATE_GITIGNORE_PATTERNS = [
    ".aippocampus/",
    "aippocampus-registry/",
    "thread-anchors.md",
]

REPO_MARKDOWN_EXCLUDED_PARTS = {
    ".git",
    ".tmp",
    "__pycache__",
}

ORIGIN_PHRASES = [
    "生命还能变成什么，而我能不能在变化后仍然是我。",
]

SECRET_OR_LOCAL_PATH_RE = re.compile(
    r"([A-Za-z]:\\|sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{20,}|"
    r"\b(api[_-]?key|secret|token|password|cookie|authorization)\b\s*[:=])",
    re.IGNORECASE,
)


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def find_repo_root(skill_root: Path) -> Path | None:
    for candidate in [skill_root.parent.parent, *skill_root.parents]:
        if (candidate / "README.md").exists() and (candidate / "skills" / skill_root.name).exists():
            return candidate
    return None


def check_repo_docs(repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    metrics: dict[str, Any] = {"repo_docs_checked": True}

    origin_stub = repo_root / "docs" / "origin.md"
    if origin_stub.exists():
        issues.append("docs/origin.md duplicates the origin essay; link docs/未干的地图.md instead")

    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        issues.append("missing .gitignore for private generated memory artifacts")
    else:
        ignored = {
            line.strip().strip("/")
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for pattern in REQUIRED_PRIVATE_GITIGNORE_PATTERNS:
            if pattern.strip("/") not in ignored:
                issues.append(f"private generated artifact is not gitignored: {pattern}")

    essay = repo_root / "docs" / "未干的地图.md"
    english_essay = repo_root / "docs" / "the-unfinished-map.md"
    if not essay.exists():
        issues.append("missing canonical Chinese origin essay: docs/未干的地图.md")
        return issues, metrics
    if not english_essay.exists():
        issues.append("missing English origin essay transcreation: docs/the-unfinished-map.md")
        return issues, metrics

    for rel_path in REQUIRED_PUBLIC_READINESS_DOCS:
        if not (repo_root / rel_path).exists():
            issues.append(f"missing public-readiness doc: {rel_path}")

    example_bundle = repo_root / "examples" / "public-memory-bundle"
    if not example_bundle.exists():
        issues.append("missing public example memory bundle")
    else:
        for path in example_bundle.rglob("*"):
            if path.is_file():
                rel = path.relative_to(example_bundle).as_posix()
                if rel not in PUBLIC_EXAMPLE_BUNDLE_ALLOWED_FILES:
                    issues.append(f"unexpected public example bundle file: examples/public-memory-bundle/{rel}")
        for rel_path in PUBLIC_EXAMPLE_BUNDLE_FILES:
            if not (example_bundle / rel_path).exists():
                issues.append(f"missing public example bundle file: examples/public-memory-bundle/{rel_path}")
        manifest = {}
        manifest_path = example_bundle / "bundle_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                issues.append(f"invalid public example bundle manifest: {type(exc).__name__}")
        if manifest.get("raw_rollout_included"):
            issues.append("public example memory bundle must not include raw rollout")
        if (example_bundle / "rollout.jsonl").exists():
            issues.append("public example memory bundle must not contain rollout.jsonl")
        clean_manifest_path = example_bundle / "clean-source" / "manifest.json"
        if clean_manifest_path.exists():
            try:
                clean_manifest = json.loads(clean_manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                issues.append(f"invalid public example clean-source manifest: {type(exc).__name__}")
                clean_manifest = {}
            if not clean_manifest.get("scope_label_policy"):
                issues.append("public example clean-source manifest must document scope_label_policy")
        public_messages_by_id: dict[str, dict[str, Any]] = {}
        for rel_path in ["clean-source/messages.jsonl", "clean-source/turns.jsonl"]:
            jsonl_path = example_bundle / rel_path
            if not jsonl_path.exists():
                continue
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    try:
                        item = json.loads(line)
                    except Exception as exc:
                        issues.append(f"invalid public example JSONL {rel_path}:{line_no}: {type(exc).__name__}")
                        continue
                    if not isinstance(item.get("scope_labels"), list):
                        issues.append(f"public example JSONL missing scope_labels: examples/public-memory-bundle/{rel_path}:{line_no}")
                        continue
                    scope_labels = [label for label in item.get("scope_labels", []) if isinstance(label, str)]
                    if scope_labels != [label for label in SCOPE_LABEL_ORDER if label in set(scope_labels)]:
                        issues.append(f"public example JSONL has non-canonical scope_labels order: examples/public-memory-bundle/{rel_path}:{line_no}")
                    if rel_path == "clean-source/messages.jsonl":
                        expected = infer_scope_labels(str(item.get("text") or ""))
                        if scope_labels != expected:
                            issues.append(
                                f"public example message scope_labels do not match current generator: "
                                f"examples/public-memory-bundle/{rel_path}:{line_no}"
                            )
                        public_messages_by_id[str(item.get("message_id") or item.get("id") or "")] = item
                    elif rel_path == "clean-source/turns.jsonl":
                        expected_set = {
                            label
                            for message_id in item.get("message_ids", [])
                            for label in public_messages_by_id.get(str(message_id), {}).get("scope_labels", [])
                            if isinstance(label, str)
                        }
                        expected = [label for label in SCOPE_LABEL_ORDER if label in expected_set]
                        if scope_labels != expected:
                            issues.append(
                                f"public example turn scope_labels do not match message union: "
                                f"examples/public-memory-bundle/{rel_path}:{line_no}"
                            )
        for path in example_bundle.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
                text = path.read_text(encoding="utf-8")
                if SECRET_OR_LOCAL_PATH_RE.search(text):
                    rel = path.relative_to(repo_root).as_posix()
                    issues.append(f"public example bundle contains secret-like or local-path text: {rel}")

    markdown_files = [
        path
        for path in repo_root.rglob("*.md")
        if not any(part in REPO_MARKDOWN_EXCLUDED_PARTS for part in path.parts)
    ]
    metrics["repo_markdown_files"] = len(markdown_files)
    for phrase in ORIGIN_PHRASES:
        owners = [
            path.relative_to(repo_root).as_posix()
            for path in markdown_files
            if phrase in path.read_text(encoding="utf-8")
        ]
        if owners != ["docs/未干的地图.md"]:
            issues.append(
                f"origin phrase should live only in docs/未干的地图.md; found in {owners}"
            )
    return issues, metrics


def check_docs(root: Path) -> dict[str, Any]:
    root = root.resolve()
    skill_path = root / "SKILL.md"
    issues: list[str] = []

    if not skill_path.exists():
        return {
            "ok": False,
            "issues": [f"missing {skill_path}"],
            "metrics": {},
        }

    text = skill_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    word_count = count_words(text)
    code_fence_count = text.count("```")
    metrics = {
        "skill_lines": len(lines),
        "skill_words": word_count,
        "skill_code_fences": code_fence_count,
        "required_references": len(REQUIRED_REFERENCES),
    }

    if len(lines) > MAX_SKILL_LINES:
        issues.append(f"SKILL.md has {len(lines)} lines; keep it <= {MAX_SKILL_LINES}")
    if word_count > MAX_SKILL_WORDS:
        issues.append(f"SKILL.md has {word_count} words; keep it <= {MAX_SKILL_WORDS}")
    if code_fence_count > MAX_SKILL_CODE_FENCES:
        issues.append(
            f"SKILL.md has {code_fence_count} code-fence markers; move command dumps to references"
        )

    references_dir = root / "references"
    for filename in REQUIRED_REFERENCES:
        ref_path = references_dir / filename
        if not ref_path.exists():
            issues.append(f"missing reference: references/{filename}")
        if filename not in text:
            issues.append(f"SKILL.md does not link references/{filename}")

    if "changelog" in text.lower() and "Do not append changelog-style notes" not in text:
        issues.append("SKILL.md mentions changelog without the stable-entrypoint guardrail")

    repo_root = find_repo_root(root)
    if repo_root:
        for rel_path in REQUIRED_PROJECT_DOCS:
            if not (repo_root / rel_path).exists():
                issues.append(f"missing project doc: {rel_path}")
        repo_issues, repo_metrics = check_repo_docs(repo_root)
        issues.extend(repo_issues)
        metrics.update(repo_metrics)
    else:
        metrics["repo_docs_checked"] = False

    return {
        "ok": not issues,
        "issues": issues,
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="AIppocampus skill root. Defaults to this script's parent skill directory.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    result = check_docs(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "OK" if result["ok"] else "FAILED"
        print(f"docs health: {status}")
        for key, value in result["metrics"].items():
            print(f"{key}: {value}")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
