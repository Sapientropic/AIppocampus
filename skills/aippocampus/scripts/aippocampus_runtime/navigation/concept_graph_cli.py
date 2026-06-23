#!/usr/bin/env python3
"""CLI wrapper for concept graph build and expansion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aippocampus_runtime.navigation.associations import default_associations_path
from aippocampus_runtime.navigation.concept_graph import (
    DEFAULT_MAX_RELATED_PER_TERM,
    build_concept_graph,
    concept_graph_health,
    expand_concepts,
)
from aippocampus_runtime.navigation.concept_graph_schema import (
    default_concept_graph_path,
    default_project_timeline_path,
    default_subconscious_edges_path,
)
from aippocampus_runtime.registry.api import registry_paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--associations")
    parser.add_argument("--project-timeline")
    parser.add_argument("--subconscious-edges")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--output")
    parser.add_argument("--max-related-per-term", type=int, default=DEFAULT_MAX_RELATED_PER_TERM)
    parser.add_argument("--expand", nargs="*", help="Dry-run concept expansion for seed terms.")
    parser.add_argument("--health", action="store_true", help="Report privacy-safe graph quality diagnostics.")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    associations_path = (
        Path(args.associations).resolve()
        if args.associations
        else default_associations_path(registry_path=registry_path)
    )
    project_timeline_path = (
        Path(args.project_timeline).resolve()
        if args.project_timeline
        else default_project_timeline_path(registry_path=registry_path)
    )
    subconscious_edges_path = (
        Path(args.subconscious_edges).resolve()
        if args.subconscious_edges
        else default_subconscious_edges_path(registry_path=registry_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else default_concept_graph_path(registry_path=registry_path)
    )

    if args.health:
        payload = concept_graph_health(output_path)
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"concept graph health: {payload.get('status')}")
            print(f"concepts: {payload.get('concept_count', 0)}")
            print(f"edges: {payload.get('edge_count', 0)}")
            warnings = payload.get("warnings") or []
            if warnings:
                print("warnings: " + ", ".join(str(item.get("code")) for item in warnings))
        return 0 if payload.get("ok") else 1

    if args.expand:
        rows = expand_concepts(output_path, args.expand, depth=args.depth)
        payload = {"concept_graph": str(output_path), "seed_terms": args.expand, "expansions": rows}
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for row in rows:
                print(
                    f"- {row['term']} | score {row['score']} | depth {row['depth']} | {' -> '.join(row['path'])}"
                )
        return 0

    result = build_concept_graph(
        associations_path,
        output_path,
        project_timeline_path=project_timeline_path if project_timeline_path.exists() else None,
        subconscious_edges_path=subconscious_edges_path
        if subconscious_edges_path.exists()
        else None,
        max_related_per_term=args.max_related_per_term,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"concept graph: {output_path}")
        print(f"concepts: {result['concept_count']}")
        print(f"edges: {result['edge_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
