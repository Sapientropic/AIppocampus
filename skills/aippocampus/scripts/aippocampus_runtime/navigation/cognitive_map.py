#!/usr/bin/env python3
"""Build and query the AIppocampus cognitive map sidecar.

The cognitive map is a navigation layer, not a source of truth. Routes are
materialized only from source-backed subconscious findings, so registry metadata
can place episodes on the map but cannot invent semantic routes by itself.
When those routes do not exist yet, a registry-derived far-view overview may
orient the foreground agent, but it remains a weak route context that requires
clean-source reopen before claims.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# Prefer this checkout's runtime package when the script is invoked by path.
# Otherwise a locally installed older skill can satisfy package imports and miss
# newly split sibling modules.
SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.io_mtime_cache import load_json_object
from aippocampus_runtime.navigation.associations import (
    normalize_term,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.navigation.cognitive_map_overview import (
    match_registry_overview,
    registry_overview_from_episodes,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import load_registry, registry_paths, unique_preserve
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

COGNITIVE_MAP_SCHEMA_VERSION = 1
DEFAULT_COGNITIVE_MAP_NAME = "cognitive_map.json"
DEFAULT_JOBS_NAME = "subconscious_jobs.jsonl"
MIN_ROUTE_CONFIDENCE = 0.55
MIN_ROUTE_QUALITY_BUCKETS = {"usable", "strong"}
MAX_ROUTE_TERMS = 24
MAP_QUERY_SCALES = {"far", "mid", "near"}

_MAP_SIGNATURE_BY_ID: dict[int, tuple[str, int, int]] = {}
_MATCH_CACHE: dict[tuple[tuple[str, int, int], str, tuple[str, ...], str, int], list[dict[str, Any]]] = {}

GENERIC_MAP_TERMS = {
    "memory",
    "project",
    "source",
    "candidate",
    "thread",
    "route",
    "landmark",
    "region",
    "记忆",
    "项目",
    "来源",
    "候选",
    "线程",
    "路线",
    "地标",
    "区域",
}


def default_cognitive_map_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_COGNITIVE_MAP_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_COGNITIVE_MAP_NAME


def default_jobs_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_JOBS_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_JOBS_NAME


def load_cognitive_map_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_jsonl_dict_rows(path).rows


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_cognitive_map(path: Path | str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = load_json_object(target)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    try:
        stat = target.stat()
        _MAP_SIGNATURE_BY_ID[id(data)] = (str(target.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        pass
    return data


def load_cognitive_map_findings(path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in load_cognitive_map_rows(path):
        if row.get("kind") != "aippocampus_subconscious_job_finding":
            continue
        if row.get("job") != "cognitive_map":
            continue
        if row.get("finding_kind") != "cognitive_map_route":
            continue
        findings.append(row)
    return findings


def compact_string_list(values: Any, *, limit: int = 12, chars: int = 90) -> list[str]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, list):
        source = values
    else:
        source = []
    out: list[str] = []
    for value in source:
        term = normalize_term(str(value or ""))
        if not term:
            continue
        if len(term) > chars:
            term = compact_text(term, chars)
        low = term.casefold()
        if low in GENERIC_MAP_TERMS or term_is_noise(term) or source_text_is_noise(term):
            continue
        out.append(term)
    return unique_preserve(out, limit=limit)


def id_for(prefix: str, label: str) -> str:
    digest = hashlib.sha1(normalize_term(label).casefold().encode("utf-8")).hexdigest()[:18]
    return f"{prefix}_{digest}"


def route_id_for(finding: dict[str, Any], thread_keys: list[str], cues: list[str]) -> str:
    raw = "\n".join(
        [
            str(finding.get("fingerprint") or ""),
            str(finding.get("title") or ""),
            "|".join(thread_keys),
            "|".join(cues),
        ]
    )
    digest = hashlib.sha1(raw.casefold().encode("utf-8")).hexdigest()[:18]
    return f"cmr_{digest}"


def source_refs(finding: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in finding.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        thread_key = str(ref.get("thread_key") or "").strip()
        line = (
            ref.get("line")
            or ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
        )
        clean = {
            "thread_key": thread_key,
            "title": ref.get("title"),
            "project_label": ref.get("project_label"),
            "turn_index": ref.get("turn_index"),
            "line": line,
            "message_id": ref.get("message_id"),
        }
        key = (thread_key, str(line or ""), str(clean.get("message_id") or ""))
        if not thread_key or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in clean.items() if v not in {None, ""}})
    return refs[:10]


def thread_keys_for_route(
    finding: dict[str, Any], refs: list[dict[str, Any]], registry_threads: set[str]
) -> list[str]:
    ref_threads = unique_preserve(
        [str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")], limit=16
    )
    requested = unique_preserve(
        [str(value) for value in finding.get("target_thread_keys") or [] if str(value).strip()],
        limit=16,
    )
    if requested:
        valid_requested = [
            key
            for key in requested
            if key in registry_threads and (not ref_threads or key in ref_threads)
        ]
        if valid_requested:
            return valid_requested
    return [key for key in ref_threads if key in registry_threads]


def episode_from_registry(entry: dict[str, Any]) -> dict[str, Any] | None:
    thread_key = str(entry.get("thread_key") or "")
    if not thread_key:
        return None
    return {
        "thread_key": thread_key,
        "title": entry.get("title") or entry.get("workspace_name") or thread_key,
        "project_label": entry.get("project_label") or entry.get("workspace_name"),
        "updated_at": entry.get("updated_at") or (entry.get("session_meta") or {}).get("timestamp"),
        "anchor_titles": unique_preserve(
            [str(value) for value in entry.get("anchor_titles") or []], limit=6
        ),
        "keywords": unique_preserve(
            [str(value) for value in entry.get("keywords") or []], limit=10
        ),
        "summary": compact_text(str(entry.get("summary") or ""), 260),
    }


def route_terms(
    *,
    route_cues: list[str],
    landmarks: list[str],
    regions: list[str],
    finding: dict[str, Any],
) -> list[str]:
    text = "\n".join(
        [
            str(finding.get("title") or ""),
            str(finding.get("summary") or ""),
            str(finding.get("recommendation") or ""),
            " ".join(str(value) for value in finding.get("concepts") or []),
        ]
    )
    terms = (
        list(route_cues)
        + list(landmarks)
        + list(regions)
        + compact_string_list(finding.get("query_terms"), limit=12)
        + compact_string_list(finding.get("aliases"), limit=12)
        + split_query_terms([text])
    )
    return compact_string_list(terms, limit=MAX_ROUTE_TERMS)


def better_confidence(current: dict[str, Any] | None, confidence: float) -> bool:
    if not current:
        return True
    return confidence > float(current.get("confidence") or 0.0)


def quality_allows_route(finding: dict[str, Any]) -> bool:
    quality = finding.get("quality")
    if not isinstance(quality, dict):
        return True
    bucket = str(quality.get("bucket") or "")
    return bucket in MIN_ROUTE_QUALITY_BUCKETS


def build_cognitive_map(
    *, registry: dict[str, Any], job_findings: list[dict[str, Any]]
) -> dict[str, Any]:
    registry_entries = [entry for entry in registry.get("threads") or [] if isinstance(entry, dict)]
    registry_threads = {
        str(entry.get("thread_key") or "") for entry in registry_entries if entry.get("thread_key")
    }
    episodes = [episode for entry in registry_entries if (episode := episode_from_registry(entry))]
    landmarks_by_id: dict[str, dict[str, Any]] = {}
    regions_by_id: dict[str, dict[str, Any]] = {}
    routes_by_id: dict[str, dict[str, Any]] = {}

    for finding in job_findings:
        confidence = float(finding.get("confidence") or 0.0)
        if confidence < MIN_ROUTE_CONFIDENCE:
            continue
        if not quality_allows_route(finding):
            continue
        refs = source_refs(finding)
        if not refs:
            continue
        thread_keys = thread_keys_for_route(finding, refs, registry_threads)
        if not thread_keys:
            continue
        landmarks = compact_string_list(
            finding.get("landmarks") or finding.get("concepts"), limit=10
        )
        route_cues = compact_string_list(
            finding.get("route_cues") or finding.get("aliases"), limit=16
        )
        if not landmarks or not route_cues:
            continue
        regions = compact_string_list(finding.get("regions"), limit=8)
        if not regions:
            regions = unique_preserve(
                [str(ref.get("project_label") or "") for ref in refs if ref.get("project_label")],
                limit=4,
            )
        region_ids = [id_for("cmg", region) for region in regions]
        landmark_ids = [id_for("cml", landmark) for landmark in landmarks]

        for region, region_id in zip(regions, region_ids, strict=True):
            existing = regions_by_id.get(region_id)
            if better_confidence(existing, confidence):
                regions_by_id[region_id] = {
                    "region_id": region_id,
                    "label": region,
                    "thread_keys": unique_preserve(thread_keys, limit=20),
                    "confidence": round(confidence, 4),
                    "source": str(finding.get("source") or "deepseek_subconscious_jobs"),
                    "source_finding_ids": unique_preserve(
                        [str(finding.get("fingerprint") or "")], limit=8
                    ),
                }
            elif existing:
                existing["thread_keys"] = unique_preserve(
                    list(existing.get("thread_keys") or []) + thread_keys, limit=20
                )

        for landmark, landmark_id in zip(landmarks, landmark_ids, strict=True):
            existing = landmarks_by_id.get(landmark_id)
            aliases = unique_preserve(
                compact_string_list(finding.get("aliases"), limit=12) + route_cues, limit=16
            )
            if better_confidence(existing, confidence):
                landmarks_by_id[landmark_id] = {
                    "landmark_id": landmark_id,
                    "label": landmark,
                    "aliases": aliases,
                    "region_ids": region_ids,
                    "thread_keys": unique_preserve(thread_keys, limit=20),
                    "confidence": round(confidence, 4),
                    "source": str(finding.get("source") or "deepseek_subconscious_jobs"),
                    "source_finding_ids": unique_preserve(
                        [str(finding.get("fingerprint") or "")], limit=8
                    ),
                    "source_refs": refs[:5],
                }
            elif existing:
                existing["aliases"] = unique_preserve(
                    list(existing.get("aliases") or []) + aliases, limit=16
                )
                existing["thread_keys"] = unique_preserve(
                    list(existing.get("thread_keys") or []) + thread_keys, limit=20
                )
                existing["region_ids"] = unique_preserve(
                    list(existing.get("region_ids") or []) + region_ids, limit=12
                )

        terms = route_terms(
            route_cues=route_cues, landmarks=landmarks, regions=regions, finding=finding
        )
        route: dict[str, Any] = {
            "route_id": route_id_for(finding, thread_keys, route_cues),
            "kind": "cognitive_map_route",
            "route_kind": compact_text(str(finding.get("route_kind") or "association"), 40),
            "title": compact_text(str(finding.get("title") or ""), 140),
            "summary": compact_text(str(finding.get("summary") or ""), 420),
            "source": str(finding.get("source") or "deepseek_subconscious_jobs"),
            "model": finding.get("model"),
            "landmark_ids": landmark_ids,
            "landmark_labels": landmarks,
            "region_ids": region_ids,
            "region_labels": regions,
            "route_cues": route_cues,
            "negative_cues": compact_string_list(finding.get("negative_cues"), limit=10),
            "query_terms": terms,
            "thread_keys": thread_keys,
            "confidence": round(confidence, 4),
            "source_finding_id": finding.get("fingerprint"),
            "source_refs": refs[:8],
        }
        route_id = str(route["route_id"])
        existing_route = routes_by_id.get(route_id)
        if better_confidence(existing_route, confidence):
            routes_by_id[route_id] = route

    routes = sorted(
        routes_by_id.values(),
        key=lambda item: (float(item.get("confidence") or 0.0), str(item.get("title") or "")),
        reverse=True,
    )
    landmark_rows = sorted(
        landmarks_by_id.values(),
        key=lambda item: (float(item.get("confidence") or 0.0), str(item.get("label") or "")),
        reverse=True,
    )
    region_rows = sorted(
        regions_by_id.values(),
        key=lambda item: (float(item.get("confidence") or 0.0), str(item.get("label") or "")),
        reverse=True,
    )
    registry_overview = registry_overview_from_episodes(episodes)
    registry_overview_count = int(registry_overview.get("cluster_count") or 0)
    status = (
        "active"
        if routes
        else (
            "needs_subconscious_with_registry_overview"
            if registry_overview_count
            else "needs_subconscious"
        )
    )
    return {
        "schema_version": COGNITIVE_MAP_SCHEMA_VERSION,
        "kind": "aippocampus_cognitive_map",
        "created_at": now_utc(),
        "status": status,
        "source": "deepseek_subconscious_jobs",
        "source_registry_updated_at": registry.get("updated_at"),
        "episode_count": len(episodes),
        "landmark_count": len(landmark_rows),
        "region_count": len(region_rows),
        "route_count": len(routes),
        "registry_overview_count": registry_overview_count,
        "episodes": episodes,
        "registry_overview": registry_overview,
        "landmarks": landmark_rows,
        "regions": region_rows,
        "routes": routes,
        "rules": {
            "source_boundary": "Routes are model-organized navigation hints, not facts. Verify exact claims against clean source.",
            "no_route_from_registry_only": True,
            "registry_overview_navigation_only": True,
        },
    }


def cue_matches(prompt_low: str, prompt_terms: list[str], cue: str) -> bool:
    cue_low = str(cue or "").casefold().strip()
    if not cue_low:
        return False
    if cue_low in prompt_low:
        return True
    cue_terms = [term.casefold() for term in split_query_terms([cue]) if len(term.strip()) >= 3]
    return any(term and term in prompt_terms for term in cue_terms)


def cue_score(cue: str) -> float:
    length = len(str(cue or "").strip())
    return min(4.0, max(0.8, length / 8.0))


def match_cognitive_map(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    project_label: str | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not prompt or not cognitive_map:
        return []
    prompt_low = prompt.casefold()
    prompt_terms = [
        term.casefold() for term in split_query_terms([prompt]) if len(term.strip()) >= 3
    ]
    signature = _MAP_SIGNATURE_BY_ID.get(id(cognitive_map))
    cache_key = (
        signature,
        prompt_low,
        tuple(prompt_terms),
        str(project_label or "").casefold(),
        int(limit),
    ) if signature else None
    if cache_key is not None and cache_key in _MATCH_CACHE:
        return copy.deepcopy(_MATCH_CACHE[cache_key])
    matches: list[dict[str, Any]] = []
    for route in cognitive_map.get("routes") or []:
        if not isinstance(route, dict):
            continue
        negative = compact_string_list(route.get("negative_cues"), limit=12)
        if any(cue_matches(prompt_low, prompt_terms, cue) for cue in negative):
            continue
        cues = unique_preserve(
            compact_string_list(route.get("route_cues"), limit=16)
            + compact_string_list(route.get("landmark_labels"), limit=10)
            + compact_string_list(route.get("region_labels"), limit=8)
            + compact_string_list(route.get("query_terms"), limit=16),
            limit=36,
        )
        matched = [cue for cue in cues if cue_matches(prompt_low, prompt_terms, cue)]
        if not matched:
            continue
        project_boost = 0.0
        if project_label:
            labels = [str(value) for value in route.get("region_labels") or []]
            labels.extend(
                str(ref.get("project_label") or "")
                for ref in route.get("source_refs") or []
                if isinstance(ref, dict)
            )
            if any(label and label.casefold() == project_label.casefold() for label in labels):
                project_boost = 1.5
        score = min(
            30.0,
            sum(cue_score(cue) for cue in matched)
            + float(route.get("confidence") or 0.0) * 8.0
            + project_boost,
        )
        matches.append(
            {
                "route_id": route.get("route_id"),
                "route_kind": route.get("route_kind"),
                "title": route.get("title"),
                "landmark_labels": route.get("landmark_labels") or [],
                "region_labels": route.get("region_labels") or [],
                "route_cues": route.get("route_cues") or [],
                "matched_cues": unique_preserve(matched, limit=8),
                "query_terms": unique_preserve(
                    [str(value) for value in route.get("query_terms") or []], limit=16
                ),
                "thread_keys": unique_preserve(
                    [str(value) for value in route.get("thread_keys") or []], limit=8
                ),
                "confidence": route.get("confidence"),
                "score": round(score, 3),
                "source": route.get("source"),
                "source_refs": route.get("source_refs") or [],
            }
        )
    matches.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            float(item.get("confidence") or 0.0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    if not matches and not (cognitive_map.get("routes") or []):
        matches = match_registry_overview(
            prompt_low, prompt_terms, cognitive_map, project_label=project_label, limit=limit
        )
    result = matches[:limit]
    if cache_key is not None:
        _MATCH_CACHE[cache_key] = copy.deepcopy(result)
    return result


def query_cognitive_map(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    scale: str = "near",
    project_label: str | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    from aippocampus_runtime.navigation.cognitive_map_query import (
        query_cognitive_map as _query_cognitive_map,
    )

    return _query_cognitive_map(
        prompt,
        cognitive_map,
        scale=scale,
        project_label=project_label,
        limit=limit,
        near_matcher=match_cognitive_map,
    )


def build_from_files(
    *, registry_path: Path, jobs_path: Path, output_path: Path | None = None
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    findings = load_cognitive_map_findings(jobs_path)
    result = build_cognitive_map(registry=registry, job_findings=findings)
    target = output_path or default_cognitive_map_path(registry_path=registry_path)
    write_json(target, result)
    return summarize_result(result, output_path=target, jobs_path=jobs_path)


def summarize_result(
    result: dict[str, Any], *, output_path: Path, jobs_path: Path
) -> dict[str, Any]:
    return {
        "schema_version": result.get("schema_version"),
        "kind": result.get("kind"),
        "created_at": result.get("created_at"),
        "status": result.get("status"),
        "source": result.get("source"),
        "source_registry_updated_at": result.get("source_registry_updated_at"),
        "episode_count": result.get("episode_count"),
        "landmark_count": result.get("landmark_count"),
        "region_count": result.get("region_count"),
        "route_count": result.get("route_count"),
        "registry_overview_count": result.get("registry_overview_count"),
        "output": str(output_path),
        "source_jobs": str(jobs_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs")
    parser.add_argument("--output")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--query", help="Optional prompt to query the built cognitive map.")
    parser.add_argument(
        "--scale",
        choices=sorted(MAP_QUERY_SCALES),
        default="near",
        help="Explicit map query scale for --query.",
    )
    parser.add_argument("--limit", type=int, default=4, help="Maximum rows in query output.")
    parser.add_argument("--project-label", help="Optional project label boost for map queries.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve() if args.registry else None
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    if not registry_path:
        registry_path = registry_paths(registry_dir)[0]
    jobs_path = (
        Path(args.jobs).resolve() if args.jobs else default_jobs_path(registry_path=registry_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else default_cognitive_map_path(registry_path=registry_path)
    )
    registry = load_registry(registry_path)
    findings = load_cognitive_map_findings(jobs_path)
    result = build_cognitive_map(registry=registry, job_findings=findings)
    if not args.no_write:
        write_json(output_path, result)
    if args.query:
        query_result = query_cognitive_map(
            args.query,
            result,
            scale=args.scale,
            project_label=args.project_label,
            limit=args.limit,
        )
        if args.json_output:
            print(json.dumps(query_result, ensure_ascii=False, indent=2))
        else:
            print(f"cognitive map query scale: {query_result['scale']}")
            print(json.dumps(query_result.get("coverage") or {}, ensure_ascii=False))
        return 0
    result = summarize_result(result, output_path=output_path, jobs_path=jobs_path)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"cognitive map routes: {result['route_count']}")
        print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
