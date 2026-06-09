"""Navigation-only concept-kind inference for concept graph labels."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.navigation.associations import normalize_term

ALLOWED_CONCEPT_KINDS = {
    "artifact",
    "decision",
    "library",
    "person",
    "place",
    "project",
    "topic",
    "tool",
    "workflow",
}
SUPPLIED_KIND_REVIEW_STATUSES = {"reviewed", "verified", "source_backed", "source-backed"}

ARTIFACT_TOKENS = {
    ".json",
    ".jsonl",
    ".md",
    ".sqlite",
    ".yaml",
    ".yml",
    "dataset",
    "fixture",
    "manifest",
    "readme",
    "report",
    "schema",
    "snapshot",
    "报告",
    "记录",
    "夹具",
    "快照",
    "清单",
    "索引",
    "文档",
    "数据集",
}

TOOL_TOKENS = {
    " api",
    " cli",
    " mcp",
    " sdk",
    " tool",
    "agent sdk",
    "claude code",
    "codex cli",
    "deepseek",
    "mypy",
    "pyinstaller",
    "pytest",
    "ruff",
    "uvx",
    "工具",
    "接口",
}

WORKFLOW_TOKENS = {
    "calibration",
    "deployment",
    "migration",
    "onboarding",
    "pipeline",
    "registration",
    "release",
    "sync",
    "workflow",
    "发布",
    "工作流",
    "校准",
    "流程",
    "管道",
    "节奏",
    "路线",
    "迁移",
    "部署",
}

DECISION_TOKENS = {
    "boundary",
    "contract",
    "decision",
    "gate",
    "policy",
    "principle",
    "requirement",
    "strategy",
    "tradeoff",
    "准入",
    "决策",
    "原则",
    "取舍",
    "契约",
    "方案",
    "策略",
    "约束",
    "边界",
}


def concept_kind_source_boundary() -> dict[str, bool]:
    return {
        "concept_kind_is_navigation_only": True,
        "concept_kind_is_not_evidence": True,
        "uncertain_kind_does_not_block_recall": True,
    }


def normalize_concept_kind(value: Any) -> str:
    kind = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    return kind if kind in ALLOWED_CONCEPT_KINDS else ""


def re_like_project(label: str) -> bool:
    low = label.casefold()
    return low in {"t-sense", "aippocampus"} or low.startswith("project:")


def deterministic_concept_kind(label: str) -> str:
    normalized = normalize_term(label).casefold()
    low = f"{normalized} {label.casefold()}"
    if re_like_project(label):
        return "project"
    if any(token in low for token in ARTIFACT_TOKENS):
        return "artifact"
    if "/" in label:
        return "library"
    if "." in label and not any(ch.isspace() for ch in label):
        return "library"
    if any(token in low for token in TOOL_TOKENS):
        return "tool"
    if any(token in low for token in WORKFLOW_TOKENS):
        return "workflow"
    if any(token in low for token in DECISION_TOKENS):
        return "decision"
    return "topic"


def classify_concept_kind(
    label: str,
    *,
    supplied_kind: Any = None,
    supplied_kind_status: Any = None,
    source_backed_kind: bool = False,
) -> dict[str, Any]:
    kind = normalize_concept_kind(supplied_kind)
    status = str(supplied_kind_status or "").strip().casefold()
    if kind and status in {"reviewed", "verified"}:
        return {
            "kind": kind,
            "kind_source": "supplied_reviewed",
            "kind_confidence": 1.0,
        }
    if kind and source_backed_kind and (
        status in {"", "source_backed", "source-backed"} or status in SUPPLIED_KIND_REVIEW_STATUSES
    ):
        return {
            "kind": kind,
            "kind_source": "supplied_source_backed",
            "kind_confidence": 0.92,
        }
    inferred = deterministic_concept_kind(label)
    if inferred == "topic":
        return {"kind": "topic", "kind_source": "fallback", "kind_confidence": 0.35}
    return {"kind": inferred, "kind_source": "deterministic", "kind_confidence": 0.72}


def infer_concept_kind(label: str) -> str:
    return str(classify_concept_kind(label)["kind"])
