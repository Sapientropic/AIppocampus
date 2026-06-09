"""Guard package development-status classifiers against premature maturity claims."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# Development-status classifiers are maturity claims, not Python compatibility
# claims. Keep this as a separate guard so a future release cannot become
# "Beta" by a pyproject edit unless the dated readiness decision is updated too.
CLASSIFIER_POLICY_DOC = "docs/evidence/readiness/classifier-policy.md"
ALPHA_CLASSIFIER = "Development Status :: 3 - Alpha"
BETA_CLASSIFIER = "Development Status :: 4 - Beta"
STABLE_CLASSIFIER = "Development Status :: 5 - Production/Stable"

CLASSIFIER_POLICY_REQUIRED_TERMS = {
    "`Development Status :: 3 - Alpha`": "classifier policy missing Alpha meaning",
    "`Development Status :: 4 - Beta`": "classifier policy missing Beta meaning",
    "`Development Status :: 5 - Production/Stable`": (
        "classifier policy missing Stable meaning"
    ),
    "#978": "classifier policy missing source-backed kernel prerequisite issue",
    "#979": "classifier policy missing wheel contract prerequisite issue",
    "#980": "classifier policy missing evidence drawer prerequisite issue",
    "#981": "classifier policy missing provider conformance prerequisite issue",
    "#982": "classifier policy missing Field Continuity Eval prerequisite issue",
    "#983": "classifier policy missing cognitive-layer graduation prerequisite issue",
    "#965": "classifier policy missing docs IA prerequisite issue #965",
    "#966": "classifier policy missing docs IA prerequisite issue #966",
    "#967": "classifier policy missing docs IA prerequisite issue #967",
    "#968": "classifier policy missing docs IA prerequisite issue #968",
    "#960": "classifier policy missing benchmark remediation issue #960",
    "#961": "classifier policy missing benchmark remediation issue #961",
    "#962": "classifier policy missing benchmark remediation issue #962",
    "#963": "classifier policy missing benchmark remediation issue #963",
    "#964": "classifier policy missing benchmark remediation issue #964",
    "#949": "classifier policy missing narrative mesh issue #949",
    "#950": "classifier policy missing active-flow feedback issue #950",
    "#951": "classifier policy missing fresh-thread projection issue #951",
}

CURRENT_ALPHA_POLICY_TERMS = {
    "current_classifier: Development Status :: 3 - Alpha": (
        "classifier policy missing current Alpha classifier marker"
    ),
    "beta_readiness_decision: not_approved": (
        "classifier policy missing current not-approved Beta decision marker"
    ),
    "earliest_beta_classifier_release: 0.3.0 or later": (
        "classifier policy missing 0.3.0-or-later Beta eligibility boundary"
    ),
}

CLASSIFIER_RELEASE_CHECKLIST_TERMS = {
    "package classifier": "release checklist missing package classifier review",
    "README claims": "release checklist missing README claims/classifier alignment",
    "public API docs": "release checklist missing public API/classifier alignment",
    "release notes": "release checklist missing release notes/classifier alignment",
    "dated readiness decision": "release checklist missing dated readiness decision gate",
    "classifier-policy.md": "release checklist missing classifier policy pointer",
}


def development_status_classifier_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []

    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        return ["missing pyproject.toml for development-status classifier contract"]
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [
            "cannot parse pyproject.toml for development-status "
            f"classifier contract: {exc}"
        ]

    project = pyproject.get("project", {})
    classifiers = [str(item) for item in project.get("classifiers", [])]
    development_status_classifiers = [
        classifier
        for classifier in classifiers
        if classifier.startswith("Development Status :: ")
    ]
    if len(development_status_classifiers) != 1:
        issues.append(
            "pyproject.toml must declare exactly one Development Status classifier; "
            f"found {development_status_classifiers!r}"
        )
        active_classifier = ""
    else:
        active_classifier = development_status_classifiers[0]

    allowed_classifiers = {ALPHA_CLASSIFIER, BETA_CLASSIFIER, STABLE_CLASSIFIER}
    if active_classifier and active_classifier not in allowed_classifiers:
        issues.append(f"unsupported development-status classifier: {active_classifier}")

    policy_path = repo_root / CLASSIFIER_POLICY_DOC
    if not policy_path.exists():
        issues.append(f"missing classifier policy doc: {CLASSIFIER_POLICY_DOC}")
        policy_text = ""
    else:
        policy_text = policy_path.read_text(encoding="utf-8")
        for term, issue in CLASSIFIER_POLICY_REQUIRED_TERMS.items():
            if term not in policy_text:
                issues.append(issue)

    checklist_path = repo_root / "docs" / "guides" / "release-checklist.md"
    if not checklist_path.exists():
        issues.append("missing release checklist for classifier contract")
    else:
        checklist_text = checklist_path.read_text(encoding="utf-8")
        for term, issue in CLASSIFIER_RELEASE_CHECKLIST_TERMS.items():
            if term not in checklist_text:
                issues.append(issue)

    if active_classifier == ALPHA_CLASSIFIER:
        for term, issue in CURRENT_ALPHA_POLICY_TERMS.items():
            if term not in policy_text:
                issues.append(issue)
        if policy_text and "beta_readiness_decision: approved" in policy_text:
            issues.append(
                "classifier policy approves Beta while pyproject.toml still advertises Alpha"
            )
        return issues

    if active_classifier in {BETA_CLASSIFIER, STABLE_CLASSIFIER}:
        version = str(project.get("version") or "")
        if f"current_classifier: {active_classifier}" not in policy_text:
            issues.append(
                "classifier policy current_classifier must match pyproject.toml "
                f"development status: {active_classifier}"
            )
        if "beta_readiness_decision: approved" not in policy_text:
            issues.append(
                f"pyproject.toml cannot advertise {active_classifier} without "
                f"approved dated Beta readiness decision in {CLASSIFIER_POLICY_DOC}"
            )
        if not re.search(r"decision_date:\s*20\d\d-\d\d-\d\d", policy_text):
            issues.append("classifier policy must include a dated Beta readiness decision")
        if version and f"approved_classifier_release: {version}" not in policy_text:
            issues.append(
                "classifier policy must approve the exact pyproject release version "
                f"before advertising {active_classifier}"
            )
        if active_classifier == STABLE_CLASSIFIER and (
            "stable_readiness_decision: approved" not in policy_text
        ):
            issues.append(
                "pyproject.toml cannot advertise Production/Stable without a separate "
                "approved Stable readiness decision"
            )

    return issues
