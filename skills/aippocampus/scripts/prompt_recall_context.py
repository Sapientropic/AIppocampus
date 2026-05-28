#!/usr/bin/env python3
"""Hook-safe input preparation for prompt recall decisions.

This module keeps path resolution and lightweight local input loading out of
`assess_prompt()`. Maintainers: keep scoring, suppression, ranking, and evidence
policy in `prompt_recall_decision.py` / `prompt_recall_core.py`; this layer only
prepares deterministic inputs that are safe to read from the foreground hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build_associations import (
    default_associations_path,
    load_associations,
    match_associations,
    source_text_is_noise,
)
from build_cognitive_map import (
    default_cognitive_map_path,
    load_cognitive_map,
    match_cognitive_map,
)
from build_concept_graph import default_concept_graph_path
from memory_candidate_router import (
    default_working_memory_path,
    load_working_memory,
    match_working_memory,
)
from prompt_cues import (
    ASSOCIATIVE_CUES,
    IMPORTANCE_CUES,
    association_term_is_generic,
    explicit_recall_terms,
    matched_terms,
)
from prompt_recall_core import (
    current_project_label,
    registry_json_path,
)
from registry import load_registry
from retrieval import CONCEPT_TRIGGERS
from semantic_recall_gate import default_semantic_triggers_path


@dataclass(frozen=True)
class RecallDecisionContext:
    prompt: str
    cwd_path: Path
    registry_path: Path
    associations_path: Path
    cognitive_map_path: Path
    concept_graph_path: Path
    working_memory_path: Path
    semantic_triggers_path: Path
    is_noise: bool
    registry: dict[str, Any]
    project_label: str | None
    associations: dict[str, Any]
    association_matches: list[dict[str, Any]]
    cognitive_map: dict[str, Any]
    cognitive_map_matches: list[dict[str, Any]]
    working_memory_rows: list[dict[str, Any]]
    working_memory_matches: list[dict[str, Any]]
    pre_explicit: list[str]
    pre_associative: list[str]
    pre_important: list[str]

    def hook_path_fields(self) -> dict[str, str]:
        return {
            "cwd": str(self.cwd_path),
            "registry": str(self.registry_path),
            "associations": str(self.associations_path),
            "cognitive_map_path": str(self.cognitive_map_path),
            "concept_graph": str(self.concept_graph_path),
            "working_memory_path": str(self.working_memory_path),
            "semantic_triggers_path": str(self.semantic_triggers_path),
        }


def _resolve_context_paths(
    *,
    cwd: Path | str,
    registry_path: Path | str | None,
    registry_dir: Path | str | None,
    associations_path: Path | str | None,
    cognitive_map_path: Path | str | None,
    concept_graph_path: Path | str | None,
    working_memory_path: Path | str | None,
    semantic_triggers_path: Path | str | None,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    cwd_path = Path(cwd).resolve()
    path = registry_json_path(
        Path(registry_path).resolve() if registry_path else None,
        Path(registry_dir).resolve() if registry_dir else None,
    )
    association_file = (
        Path(associations_path).resolve()
        if associations_path
        else default_associations_path(registry_path=path)
    )
    concept_file = (
        Path(concept_graph_path).resolve()
        if concept_graph_path
        else default_concept_graph_path(registry_path=path)
    )
    cognitive_map_file = (
        Path(cognitive_map_path).resolve()
        if cognitive_map_path
        else default_cognitive_map_path(registry_path=path)
    )
    working_memory_file = (
        Path(working_memory_path).resolve()
        if working_memory_path
        else default_working_memory_path(registry_path=path)
    )
    semantic_triggers_file = (
        Path(semantic_triggers_path).resolve()
        if semantic_triggers_path
        else default_semantic_triggers_path(registry_path=path)
    )
    return (
        cwd_path,
        path,
        association_file,
        cognitive_map_file,
        concept_file,
        working_memory_file,
        semantic_triggers_file,
    )


def build_recall_decision_context(
    prompt: str,
    *,
    cwd: Path | str,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    associations_path: Path | str | None = None,
    cognitive_map_path: Path | str | None = None,
    concept_graph_path: Path | str | None = None,
    working_memory_path: Path | str | None = None,
    semantic_triggers_path: Path | str | None = None,
    use_cognitive_map: bool = True,
) -> RecallDecisionContext:
    prompt = str(prompt or "").strip()
    (
        cwd_path,
        path,
        association_file,
        cognitive_map_file,
        concept_file,
        working_memory_file,
        semantic_triggers_file,
    ) = _resolve_context_paths(
        cwd=cwd,
        registry_path=registry_path,
        registry_dir=registry_dir,
        associations_path=associations_path,
        cognitive_map_path=cognitive_map_path,
        concept_graph_path=concept_graph_path,
        working_memory_path=working_memory_path,
        semantic_triggers_path=semantic_triggers_path,
    )
    is_noise = source_text_is_noise(prompt)
    registry: dict[str, Any] = {}
    project_label: str | None = None
    associations: dict[str, Any] = {}
    association_matches: list[dict[str, Any]] = []
    cognitive_map: dict[str, Any] = {}
    cognitive_map_matches: list[dict[str, Any]] = []
    working_memory_rows: list[dict[str, Any]] = []
    working_memory_matches: list[dict[str, Any]] = []
    pre_explicit: list[str] = []
    pre_associative: list[str] = []
    pre_important: list[str] = []

    if not is_noise:
        registry = load_registry(path)
        project_label = current_project_label(registry, cwd_path)
        cognitive_map = (
            load_cognitive_map(cognitive_map_file)
            if use_cognitive_map and cognitive_map_file.exists()
            else {}
        )
        cognitive_map_matches = (
            match_cognitive_map(prompt, cognitive_map, project_label=project_label)
            if prompt and cognitive_map
            else []
        )
        working_memory_rows = (
            load_working_memory(working_memory_file) if working_memory_file.exists() else []
        )
        working_memory_matches = (
            match_working_memory(
                prompt,
                working_memory_rows,
                project_label=project_label,
            )
            if prompt and working_memory_rows
            else []
        )
        associations = load_associations(association_file)
        association_matches = [
            match
            for match in (match_associations(prompt, associations) if prompt else [])
            if not association_term_is_generic(match)
        ]
        pre_explicit = explicit_recall_terms(prompt)
        pre_associative = matched_terms(prompt, set(CONCEPT_TRIGGERS) | ASSOCIATIVE_CUES)
        pre_important = matched_terms(prompt, IMPORTANCE_CUES)

    return RecallDecisionContext(
        prompt=prompt,
        cwd_path=cwd_path,
        registry_path=path,
        associations_path=association_file,
        cognitive_map_path=cognitive_map_file,
        concept_graph_path=concept_file,
        working_memory_path=working_memory_file,
        semantic_triggers_path=semantic_triggers_file,
        is_noise=is_noise,
        registry=registry,
        project_label=project_label,
        associations=associations,
        association_matches=association_matches,
        cognitive_map=cognitive_map,
        cognitive_map_matches=cognitive_map_matches,
        working_memory_rows=working_memory_rows,
        working_memory_matches=working_memory_matches,
        pre_explicit=pre_explicit,
        pre_associative=pre_associative,
        pre_important=pre_important,
    )
