"""Docs-health guard for the AIppocampus product profile boundary."""

from __future__ import annotations

from pathlib import Path

PRODUCT_PROFILES_DOC = "docs/architecture/product-profiles.md"
PUBLIC_CORE_BOUNDARY_DOC = "docs/guides/public-core-boundary.md"

REQUIRED_PRODUCT_PROFILE_TERMS = {
    "`personal_default`": "product profile doc missing personal_default tag",
    "`power_user_optional`": "product profile doc missing power_user_optional tag",
    "`enterprise_governed`": "product profile doc missing enterprise_governed tag",
    "purpose-bound memory access tokens": "product profile doc missing purpose-token boundary",
    "not baseline ceremony": "product profile doc missing non-ceremony boundary",
    "pause / forget / do-not-use-here / export / why-not": "product profile doc missing personal controls",
}

PRODUCT_PROFILE_POINTER_DOCS = (
    "docs/README.md",
    "docs/guides/public-api.md",
    "docs/guides/install-guide.md",
    "docs/guides/coding-agent-memory.md",
    "docs/architecture/high-risk-answer-gates.md",
    PUBLIC_CORE_BOUNDARY_DOC,
)

REQUIRED_PUBLIC_CORE_PROFILE_TERMS = {
    "## Product Profile Boundary": "public core boundary missing product profile boundary",
    "### Personal/Core Default": "public core boundary missing Personal/Core default profile",
    "### Power-User Optional": "public core boundary missing Power-user optional profile",
    "### Enterprise/High-Risk Governed": (
        "public core boundary missing Enterprise/high-risk governed profile"
    ),
    "Purpose-bound memory access tokens are not a personal-default prerequisite": (
        "public core boundary missing purpose-token opt-in boundary"
    ),
    "pause, forget, do-not-use-here, export, and why-not diagnostics": (
        "public core boundary missing simple default controls"
    ),
    "why-recall and why-not-recall remain diagnostics": (
        "public core boundary missing advanced diagnostics optionality"
    ),
}


def product_profile_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    profile_doc = repo_root / PRODUCT_PROFILES_DOC
    if not profile_doc.exists():
        return [f"missing product profile boundary doc: {PRODUCT_PROFILES_DOC}"]

    profile_text = profile_doc.read_text(encoding="utf-8")
    for term, message in REQUIRED_PRODUCT_PROFILE_TERMS.items():
        if term not in profile_text:
            issues.append(message)

    for rel_path in PRODUCT_PROFILE_POINTER_DOCS:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing product profile pointer doc: {rel_path}")
            continue
        if "product-profiles.md" not in path.read_text(encoding="utf-8"):
            issues.append(f"{rel_path} missing product profile boundary pointer")

    return issues


def public_core_product_profile_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    public_core = repo_root / PUBLIC_CORE_BOUNDARY_DOC
    if not public_core.exists():
        return [f"missing public core boundary doc: {PUBLIC_CORE_BOUNDARY_DOC}"]

    text = public_core.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())
    for term, issue in REQUIRED_PUBLIC_CORE_PROFILE_TERMS.items():
        if term not in text and " ".join(term.split()) not in normalized_text:
            issues.append(issue)

    return issues
