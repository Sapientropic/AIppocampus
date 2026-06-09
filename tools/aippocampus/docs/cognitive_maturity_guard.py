"""Proof-slice maturity and cognitive-mechanism public-claim guards."""

from __future__ import annotations

from pathlib import Path

PROOF_SLICE_MATURITY_DOC = "docs/evidence/readiness/proof-slice-maturity.md"

REQUIRED_PROOF_SLICE_MATURITY_TERMS = {
    "`design_only`": "proof-slice maturity board missing design_only status",
    "`deterministic_smoke`": (
        "proof-slice maturity board missing deterministic_smoke status"
    ),
    "`public_safe_fixture`": (
        "proof-slice maturity board missing public_safe_fixture status"
    ),
    "`second_user`": "proof-slice maturity board missing second_user status",
    "`release_claimable`": (
        "proof-slice maturity board missing release_claimable status"
    ),
    "last_checked": "proof-slice maturity board missing last_checked field",
    "Cannot claim": "proof-slice maturity board missing cannot-claim column",
    "Owner / evidence": "proof-slice maturity board missing owner/evidence column",
    "## Cognitive Layer Graduation Ladder": (
        "proof-slice maturity board missing cognitive layer graduation ladder"
    ),
    "`metaphor`": "proof-slice maturity board missing metaphor cognitive rung",
    "`prototype`": "proof-slice maturity board missing prototype cognitive rung",
    "`fixture_tested`": (
        "proof-slice maturity board missing fixture_tested cognitive rung"
    ),
    "`benchmark_supported`": (
        "proof-slice maturity board missing benchmark_supported cognitive rung"
    ),
    "`dogfooded`": "proof-slice maturity board missing dogfooded cognitive rung",
    "`public_contract`": (
        "proof-slice maturity board missing public_contract cognitive rung"
    ),
    "private dogfood evidence": (
        "proof-slice maturity board missing private/public evidence boundary"
    ),
    "public reproducible evidence": (
        "proof-slice maturity board missing public reproducibility boundary"
    ),
    "## Flagship Cognitive Mechanism Gate": (
        "proof-slice maturity board missing flagship cognitive mechanism gate"
    ),
    "Awake SWR / online consolidation tagging": (
        "proof-slice maturity board missing Awake SWR maturity row"
    ),
    "Retrieval-induced reconsolidation": (
        "proof-slice maturity board missing retrieval reconsolidation maturity row"
    ),
    "Preplay / state-dependent routing": (
        "proof-slice maturity board missing preplay maturity row"
    ),
}

PROOF_SLICE_MATURITY_POINTER_DOCS = {
    "docs/README.md": "docs README missing proof-slice maturity board pointer",
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "stage readiness missing proof-slice maturity board pointer"
    ),
}

COGNITIVE_PUBLIC_CLAIM_DOCS = (
    "README.md",
    "docs/README.md",
    "docs/guides/public-api.md",
)

PREMATURE_COGNITIVE_PUBLIC_CLAIMS = {
    "implements awake swr": "implements Awake SWR",
    "awake swr as default": "Awake SWR as default",
    "retrieval-induced reconsolidation is implemented": (
        "retrieval-induced reconsolidation is implemented"
    ),
    "general retrieval reconsolidation is implemented": (
        "general retrieval reconsolidation is implemented"
    ),
    "predictive preplay runtime": "predictive preplay runtime",
    "preplay is default": "preplay is default",
    "state-dependent routing is default": "state-dependent routing is default",
}


def proof_slice_maturity_board_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    board = repo_root / PROOF_SLICE_MATURITY_DOC
    if not board.exists():
        issues.append(f"missing proof-slice maturity board: {PROOF_SLICE_MATURITY_DOC}")
    else:
        text = board.read_text(encoding="utf-8")
        for term, issue in REQUIRED_PROOF_SLICE_MATURITY_TERMS.items():
            if term not in text:
                issues.append(issue)

    for rel_path, issue in PROOF_SLICE_MATURITY_POINTER_DOCS.items():
        path = repo_root / rel_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        docs_relative = PROOF_SLICE_MATURITY_DOC.removeprefix("docs/")
        if path.exists() and PROOF_SLICE_MATURITY_DOC not in text and docs_relative not in text:
            issues.append(issue)
    return issues


def cognitive_mechanism_public_claim_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path in COGNITIVE_PUBLIC_CLAIM_DOCS:
        path = repo_root / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for phrase, label in PREMATURE_COGNITIVE_PUBLIC_CLAIMS.items():
            if phrase in text:
                issues.append(f"{rel_path} has premature cognitive mechanism claim: {label}")
    return issues
