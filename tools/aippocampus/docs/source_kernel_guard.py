#!/usr/bin/env python3
"""Guard the canonical source-backed kernel contract in architecture docs."""

from __future__ import annotations

from pathlib import Path

SOURCE_KERNEL_CONTRACT_DOC = "docs/architecture/architecture-overview.md"

REQUIRED_SOURCE_KERNEL_CONTRACT_TERMS = {
    "## Source-Backed Kernel Contract": (
        "architecture overview missing source-backed kernel contract section"
    ),
    (
        "ConversationProvider -> CleanSource -> SourceRef/Registry -> "
        "Rebuildable Index -> RecallCandidate -> RecallDecision -> "
        "SourceReopen -> BoundedEvidence"
    ): "source-backed kernel contract missing canonical chain",
    "Clean source is the truth substrate": (
        "source-backed kernel contract missing clean-source truth substrate boundary"
    ),
    "Indexes are rebuildable caches, not truth": (
        "source-backed kernel contract missing rebuildable-index boundary"
    ),
    "Source reopen is the transition from route/context to claim-supporting evidence": (
        "source-backed kernel contract missing source-reopen authority transition"
    ),
    "Authority rings": "source-backed kernel contract missing authority rings",
    "Truth substrate": "source-backed kernel contract missing truth substrate ring",
    "Rebuildable cache": "source-backed kernel contract missing rebuildable cache ring",
    "Navigation sidecar": "source-backed kernel contract missing navigation sidecar ring",
    "Foreground packet": "source-backed kernel contract missing foreground packet ring",
    "Bounded / source-open evidence": (
        "source-backed kernel contract missing bounded/source-open evidence ring"
    ),
    "Dream, Journey, subconscious jobs, semantic sidecars, ambient recall, sync,": (
        "source-backed kernel contract missing major non-kernel sidecar families"
    ),
    "vault, Observatory": "source-backed kernel contract missing vault/Observatory boundary",
    "Generated findings must not replace clean source": (
        "source-backed kernel contract missing generated-finding replacement guard"
    ),
}

SOURCE_KERNEL_POINTER_DOCS = {
    "docs/README.md": "docs README missing source-backed kernel contract pointer",
    "docs/architecture/README.md": (
        "architecture index missing source-backed kernel contract pointer"
    ),
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "stage readiness missing source-backed kernel contract pointer"
    ),
    "docs/evidence/readiness/proof-slice-maturity.md": (
        "proof-slice maturity board missing source-backed kernel contract pointer"
    ),
}

UNSUPPORTED_SOURCE_KERNEL_REPLACEMENT_PHRASES = {
    "generated findings replace clean source": (
        "docs claim generated findings replace clean source; route them as navigation"
    ),
    "summaries replace clean source": (
        "docs claim summaries replace clean source; summaries must remain source-routed"
    ),
    "sidecars replace clean source": (
        "docs claim sidecars replace clean source; sidecars must remain lower authority"
    ),
    "indexes are truth": (
        "docs claim indexes are truth; indexes are rebuildable caches"
    ),
    "generated sidecars as source truth": (
        "docs claim generated sidecars are source truth; reopen source instead"
    ),
}


def source_kernel_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    contract = repo_root / SOURCE_KERNEL_CONTRACT_DOC
    if not contract.exists():
        return [f"missing source-backed kernel contract: {SOURCE_KERNEL_CONTRACT_DOC}"]
    text = contract.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())
    for term, issue in REQUIRED_SOURCE_KERNEL_CONTRACT_TERMS.items():
        normalized_term = " ".join(term.split())
        if term not in text and normalized_term not in normalized_text:
            issues.append(issue)

    for rel_path, issue in SOURCE_KERNEL_POINTER_DOCS.items():
        path = repo_root / rel_path
        if not path.exists():
            continue
        pointer_text = path.read_text(encoding="utf-8")
        if (
            "source-backed-kernel-contract" not in pointer_text
            and "source-backed kernel contract" not in pointer_text.lower()
        ):
            issues.append(issue)

    for path in sorted((repo_root / "docs").rglob("*.md")):
        rel = path.relative_to(repo_root).as_posix()
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase, issue in UNSUPPORTED_SOURCE_KERNEL_REPLACEMENT_PHRASES.items():
            if phrase in lowered:
                issues.append(f"{issue}: {rel}")
    return issues
