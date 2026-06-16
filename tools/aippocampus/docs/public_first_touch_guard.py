"""Reader-first public entrypoint order checks."""

from __future__ import annotations

from pathlib import Path


def public_first_touch_order_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    receipt_command = (
        'aippocampus search "without pretending it has innate memory" '
        "--clean-source-dir ./examples/public-memory-bundle/clean-source --json"
    )
    readme = repo_root / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        receipt_index = text.find(receipt_command)
        proof_indices = [
            text.find("Can-Claim Ladder"),
            text.find("Public Provenance And Current Value Ledger"),
        ]
        if receipt_index < 0:
            issues.append("README.md missing first source-backed receipt command")
        elif any(index >= 0 and index < receipt_index for index in proof_indices):
            issues.append("README.md must lead with the executable receipt before proof-map links")
    install = repo_root / "docs" / "guides" / "install-guide.md"
    if install.exists():
        text = install.read_text(encoding="utf-8")
        install_index = text.find("aippocampus plugin install --codex --verify")
        receipt_index = text.find(receipt_command)
        reference_index = text.find("public-api.md")
        if install_index < 0 or receipt_index < 0:
            issues.append("install-guide.md missing agent-mediated install card or first receipt")
        elif reference_index >= 0 and reference_index < receipt_index:
            issues.append("install-guide.md must show install/receipt before reference-owner links")
    magic = repo_root / "docs" / "evidence" / "magic-moments.md"
    if magic.exists():
        text = magic.read_text(encoding="utf-8")
        first = text.find("## First Useful Shape")
        role = text.find("Role: product and human evidence")
        status = text.find("Status: current claim-bounded")
        if first < 0:
            issues.append("magic-moments.md missing First Useful Shape receipt section")
        elif (role >= 0 and role < first) or (status >= 0 and status < first):
            issues.append("magic-moments.md must lead with receipt before role/status caveats")
    return issues
