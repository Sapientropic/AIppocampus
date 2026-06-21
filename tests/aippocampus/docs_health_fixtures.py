from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_doc_tool_module

classifier_policy_guard = import_doc_tool_module("classifier_policy_guard")

@contextmanager
def docs_health_repo() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)

def write_origin_essays(repo: Path) -> None:
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "未干的地图.md").write_text(
        "生命还能变成什么，而我能不能在变化后仍然是我。",
        encoding="utf-8",
    )
    (docs / "the-unfinished-map.md").write_text(
        "What else can life become, and can I still be myself after the change?",
        encoding="utf-8",
    )

def write_development_status_pyproject(
    repo: Path,
    classifier: str = classifier_policy_guard.ALPHA_CLASSIFIER,
    version: str = "0.2.0",
) -> None:
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                f'version = "{version}"',
                "classifiers = [",
                f'    "{classifier}",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )

def write_classifier_policy(repo: Path) -> None:
    path = repo / "docs" / "evidence" / "readiness" / "classifier-policy.md"
    path.parent.mkdir(parents=True)
    required_terms = "\n".join(
        [
            *classifier_policy_guard.CLASSIFIER_POLICY_REQUIRED_TERMS,
            *classifier_policy_guard.CURRENT_ALPHA_POLICY_TERMS,
        ]
    )
    path.write_text(
        "\n".join(
            [
                "# Alpha/Beta/Stable Classifier Policy",
                "",
                "```text",
                "current_classifier: Development Status :: 3 - Alpha",
                "beta_readiness_decision: not_approved",
                "earliest_beta_classifier_release: 0.3.0 or later",
                "approved_classifier_release: none",
                "decision_date: none",
                "```",
                "",
                required_terms,
                "",
            ]
        ),
        encoding="utf-8",
    )

def write_classifier_release_checklist(repo: Path) -> None:
    path = repo / "docs" / "guides" / "setup" / "release-checklist.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(classifier_policy_guard.CLASSIFIER_RELEASE_CHECKLIST_TERMS) + "\n",
        encoding="utf-8",
    )


def write_legacy_alias_fixture(
    repo: Path,
    *,
    inventory_text: str,
    script_text: str,
    script_name: str = "new_surface.py",
    public_doc_text: str | None = None,
) -> None:
    inventory = repo / "docs" / "architecture" / "ops" / "legacy-alias-inventory.md"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(inventory_text, encoding="utf-8")
    script = repo / "skills" / "aippocampus" / "scripts" / script_name
    script.parent.mkdir(parents=True)
    script.write_text(script_text, encoding="utf-8")
    if public_doc_text is not None:
        install_doc = repo / "docs" / "guides" / "install-guide.md"
        install_doc.parent.mkdir(parents=True)
        install_doc.write_text(public_doc_text, encoding="utf-8")
