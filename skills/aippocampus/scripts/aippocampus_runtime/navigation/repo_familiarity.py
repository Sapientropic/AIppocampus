#!/usr/bin/env python3
"""Source-backed repo familiarity cards.

This module is a deterministic pressure-test adapter for a broader familiarity
map. It produces navigation hints, not current-code truth: every foreground card
must name the source to reopen and the point where extra verification becomes
noise.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from aippocampus_runtime.core import compact_text

SCHEMA_VERSION = 1
CARD_KIND = "source_backed_familiarity_card"
PACKET_KIND = "aippocampus_repo_familiarity_packet"
DEFAULT_MAX_CARDS = 3
DEFAULT_MAX_PACKET_BYTES = 1800


def _stable_id(parts: Sequence[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "rfc_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _repo_rel(path: str | Path) -> str:
    return Path(path).as_posix()


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _file_sha256(repo_root: Path, repo_relative: str) -> str:
    try:
        return hashlib.sha256((repo_root / repo_relative).read_bytes()).hexdigest()
    except OSError:
        return ""


def _current_invalidation_files(repo_root: Path, *repo_relative_paths: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for repo_relative in sorted({_repo_rel(path) for path in repo_relative_paths}):
        digest = _file_sha256(repo_root, repo_relative)
        if digest:
            files.append({"path": repo_relative, "sha256": digest})
    return files


def _current_source_row(
    *,
    kind: str,
    landmark: str,
    route_terms: list[str],
    boundary: str,
    route: dict[str, list[str]],
    source_path: str,
    source_line: int,
    first_source_to_reopen: str,
    why_now: str,
    action_delta_required: str,
    stop_after: str,
    repo_commit: str,
    invalidation_files: list[dict[str, str]],
    do_not_use_for: list[str] | None = None,
    decision_shadow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "landmark": landmark,
        "route_terms": route_terms,
        "boundary": boundary,
        "route": route,
        "decision_shadow": decision_shadow or {},
        "source_refs": [{"path": source_path, "line": source_line}],
        "freshness": "current",
        "invalidation": {
            "commit": repo_commit,
            "files": invalidation_files,
        },
        "why_now": why_now,
        "action_delta_required": action_delta_required,
        "first_source_to_reopen": first_source_to_reopen,
        "stop_after": stop_after,
        "do_not_use_for": do_not_use_for or [],
    }


def current_checkout_source_rows(
    repo_root: str | Path,
    *,
    repo_commit: str | None = None,
) -> list[dict[str, Any]]:
    """Return small, current-checkout familiarity rows for repo-doc fallback.

    This is deliberately a short public-repo map, not an inferred knowledge
    graph. It only offers source-to-open navigation when current checkout
    fingerprints still match, so a familiarity card cannot become current-code
    truth by itself.
    """

    root = Path(repo_root).resolve()
    commit = repo_commit if repo_commit is not None else _git_commit(root)
    hook_path = _repo_rel("skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py")
    compat_doc = _repo_rel("docs/architecture/ops/compatibility-shim-inventory.md")
    legacy_doc = _repo_rel("docs/architecture/ops/legacy-alias-inventory.md")
    return [
        _current_source_row(
            kind="docs_boundary",
            landmark="source-backed memory boundary",
            route_terms=["source", "truth", "memory"],
            boundary="Source is ground; interpretation and scent remain navigation.",
            route={"docs": [_repo_rel("docs/research/source-as-world.md")]},
            source_path=_repo_rel("docs/research/source-as-world.md"),
            source_line=28,
            why_now="Relevant when a task may turn navigation hints into memory claims.",
            action_delta_required="Reopen source docs before making a memory-backed claim.",
            first_source_to_reopen=_repo_rel("docs/research/source-as-world.md"),
            stop_after="Stop once the source-vs-weather boundary is confirmed.",
            do_not_use_for=["current repo facts without reopening source"],
            repo_commit=commit,
            invalidation_files=_current_invalidation_files(root, "docs/research/source-as-world.md"),
        ),
        _current_source_row(
            kind="runtime_owner",
            landmark="foreground hook semantic budget",
            route_terms=["hook", "semantic", "budget"],
            boundary="Foreground hook must stay cheap and fail open.",
            route={
                "files": [hook_path],
                "tests": [_repo_rel("tests/aippocampus/test_aippocampus_prompt_hook.py")],
            },
            source_path=_repo_rel("docs/architecture/runtime/cognitive-runtime-architecture.md"),
            source_line=160,
            why_now="May affect hook timeout and route visibility decisions.",
            action_delta_required="Inspect hook prompt owner and hook tests before changing semantic budget.",
            first_source_to_reopen=hook_path,
            stop_after="Stop after hook owner and tests confirm the budget boundary.",
            do_not_use_for=["unrelated README/public readiness edits"],
            repo_commit=commit,
            invalidation_files=_current_invalidation_files(
                root,
                "docs/architecture/runtime/cognitive-runtime-architecture.md",
                hook_path,
            ),
        ),
        _current_source_row(
            kind="compat_shim",
            landmark="compatibility and legacy-alias inventory",
            route_terms=[
                "compat",
                "compatibility",
                "shim",
                "package",
                "owner",
                "historical",
                "fields",
                "inventory",
                "report",
                "legacy",
                "alias",
            ],
            boundary="Compatibility and legacy-alias docs are source routes, not proof without reopening.",
            route={
                "docs": [compat_doc, legacy_doc],
                "tests": [_repo_rel("tests/aippocampus/test_compat_shim_inventory.py")],
            },
            source_path=compat_doc,
            source_line=1,
            why_now="Relevant when recall/search misses compatibility inventory docs in the current repo.",
            action_delta_required="Open the compatibility inventory before changing aliases or claiming cleanup state.",
            first_source_to_reopen=compat_doc,
            stop_after="Stop after inventory explains the shim bucket and alias removal condition.",
            do_not_use_for=["current code claims without inventory output"],
            repo_commit=commit,
            invalidation_files=_current_invalidation_files(root, compat_doc, legacy_doc),
        ),
        _current_source_row(
            kind="test_boundary",
            landmark="storage governance rebuildable cache",
            route_terms=["storage", "governance", "cache"],
            boundary="Apply mode only evicts supported rebuildable caches with manifests.",
            route={
                "files": [
                    _repo_rel(
                        "skills/aippocampus/scripts/aippocampus_runtime/ops/storage_governance.py"
                    )
                ],
                "tests": [_repo_rel("tests/aippocampus/test_storage_governance.py")],
            },
            source_path=_repo_rel("docs/architecture/ops/gb-scale-roadmap.md"),
            source_line=90,
            why_now="Relevant when touching storage GC or cache eviction contracts.",
            action_delta_required="Inspect storage governance tests before changing apply behavior.",
            first_source_to_reopen=_repo_rel("tests/aippocampus/test_storage_governance.py"),
            stop_after="Stop after manifest and health degraded/rebuildable behavior are verified.",
            do_not_use_for=["raw source deletion"],
            repo_commit=commit,
            invalidation_files=_current_invalidation_files(
                root,
                "docs/architecture/ops/gb-scale-roadmap.md",
                "tests/aippocampus/test_storage_governance.py",
            ),
        ),
        _current_source_row(
            kind="decision_shadow",
            landmark="rejected registry route card",
            route_terms=["registry", "rejected", "route"],
            boundary="Rejected-route hints require current source reopen before warning.",
            route={"tests": [_repo_rel("tests/aippocampus/test_coding_ticket_host_contract.py")]},
            source_path=_repo_rel("docs/research/agent-coding-context-analysis.md"),
            source_line=313,
            why_now="Relevant when a task may repeat an old rejected registry route.",
            action_delta_required="Check the host contract before surfacing a rejected-route warning.",
            first_source_to_reopen=_repo_rel("docs/research/agent-coding-context-analysis.md"),
            stop_after="Stop after source thickness and current visibility are checked.",
            do_not_use_for=["routine README edits", "unrelated public-readiness work"],
            repo_commit=commit,
            invalidation_files=_current_invalidation_files(
                root,
                "docs/research/agent-coding-context-analysis.md",
            ),
            decision_shadow={"status": "candidate", "source_thickness": "usable"},
        ),
    ]


def _text(value: Any, limit: int = 220) -> str:
    return compact_text(str(value or "").strip(), limit)


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item, 120)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _terms(value: Any) -> set[str]:
    text = str(value or "").casefold()
    return {term for term in re.findall(r"[a-z0-9_]+", text) if len(term) > 2}


def _source_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return refs
    for item in value:
        if not isinstance(item, Mapping):
            continue
        clean = {
            "path": _text(item.get("path"), 180),
            "line": item.get("line"),
            "kind": _text(item.get("kind"), 80),
            "source_id": _text(item.get("source_id"), 140),
        }
        refs.append({key: val for key, val in clean.items() if val not in {None, ""}})
    return refs


def _navigation_source_refs(refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert repo file refs into source-reopen handles for navigation gates."""

    out: list[dict[str, Any]] = []
    for ref in refs:
        clean = dict(ref)
        path = _text(clean.get("path"), 180)
        if path and not clean.get("thread_key"):
            clean["thread_key"] = f"repo:{path}"
        if clean.get("line") and not clean.get("source_line"):
            clean["source_line"] = clean.get("line")
        out.append(clean)
    return out


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _route(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    clean: dict[str, list[str]] = {}
    for key in ("files", "tests", "docs", "commands"):
        values = _strings(value.get(key), limit=8)
        if values:
            clean[key] = values
    return clean


def _invalidation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    clean: dict[str, Any] = {}
    commit = _text(value.get("commit"), 80)
    if commit:
        clean["commit"] = commit
    files: list[dict[str, str]] = []
    raw_files = value.get("files")
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = _text(item.get("path"), 220)
            digest = _text(item.get("sha256"), 120)
            if path and digest:
                files.append({"path": path, "sha256": digest})
    if files:
        clean["files"] = files
    return clean


def fingerprints_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for row in rows:
        invalidation = row.get("invalidation")
        if not isinstance(invalidation, Mapping):
            continue
        files = invalidation.get("files")
        if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
            continue
        for item in files:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "")
            digest = str(item.get("sha256") or "")
            if path and digest:
                fingerprints[path] = digest
    return fingerprints


def current_checkout_manifest(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    commit = _git_commit(root)
    return {
        "repo_commit": commit,
        "source_rows": current_checkout_source_rows(root, repo_commit=commit),
    }


def select_current_checkout_packet(
    repo_root: str | Path,
    *,
    task: str,
    max_cards: int = 1,
    max_packet_bytes: int = DEFAULT_MAX_PACKET_BYTES,
) -> dict[str, Any]:
    manifest = current_checkout_manifest(repo_root)
    rows = [row for row in manifest.get("source_rows") or [] if isinstance(row, Mapping)]
    cards = build_repo_familiarity_cards(manifest)
    return select_repo_familiarity_packet(
        cards,
        task=task,
        current_fingerprints=fingerprints_from_rows(rows),
        current_commit=str(manifest.get("repo_commit") or ""),
        max_cards=max_cards,
        max_packet_bytes=max_packet_bytes,
    )


def build_repo_familiarity_cards(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("source_rows") or []
    repo_commit = _text(manifest.get("repo_commit"), 80)
    if not isinstance(rows, Sequence):
        return []
    cards: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        source_refs = _source_refs(row.get("source_refs"))
        if not source_refs:
            continue
        landmark = _text(row.get("landmark"), 120)
        action_delta = _text(row.get("action_delta_required"), 260)
        first_source = _text(row.get("first_source_to_reopen"), 220)
        stop_after = _text(row.get("stop_after"), 260)
        if not landmark or not action_delta or not first_source or not stop_after:
            continue
        route_terms = sorted(
            _terms(" ".join(_strings(row.get("route_terms"), limit=16))) | _terms(landmark)
        )
        card = {
            "schema_version": SCHEMA_VERSION,
            "kind": CARD_KIND,
            "domain": "repo",
            "card_id": _stable_id([landmark, first_source, source_refs[0].get("path")]),
            "landmark": landmark,
            "category": _text(row.get("kind"), 80),
            "boundary": _text(row.get("boundary"), 320),
            "route": _route(row.get("route")),
            "route_terms": route_terms,
            "decision_shadow": row.get("decision_shadow") if isinstance(row.get("decision_shadow"), Mapping) else {},
            "source_refs": source_refs,
            "freshness": _text(row.get("freshness"), 80) or "unknown",
            "invalidation": _invalidation(row.get("invalidation")),
            "why_now": _text(row.get("why_now"), 260),
            "action_delta_required": action_delta,
            "first_source_to_reopen": first_source,
            "stop_after": stop_after,
            "do_not_use_for": _strings(row.get("do_not_use_for"), limit=8),
            "injection_policy": {
                "support_level": "navigation",
                "source_reopen_required": True,
                "max_foreground_cards": DEFAULT_MAX_CARDS,
                "never_claim_current_code_without_reopen": True,
                "repo_commit": repo_commit,
            },
        }
        cards.append(card)
    return cards


def _card_bytes(card: Mapping[str, Any]) -> int:
    return len(json.dumps(card, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _task_score(card: Mapping[str, Any], task_terms: set[str]) -> int:
    card_terms = set(card.get("route_terms") or [])
    card_terms |= _terms(card.get("landmark"))
    card_terms |= _terms(card.get("why_now"))
    return len(task_terms & card_terms)


def _stale_reason(
    card: Mapping[str, Any],
    *,
    current_fingerprints: Mapping[str, str],
    current_commit: str,
) -> str:
    raw_invalidation = card.get("invalidation")
    invalidation: Mapping[str, Any] = (
        raw_invalidation if isinstance(raw_invalidation, Mapping) else {}
    )
    expected_commit = str(invalidation.get("commit") or "").strip()
    if expected_commit and current_commit and expected_commit != current_commit:
        return "commit_mismatch"
    raw_files = invalidation.get("files") or []
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "")
            expected = str(item.get("sha256") or "")
            actual = str(current_fingerprints.get(path) or "")
            if actual and expected and actual != expected:
                return "file_hash_mismatch"
    return ""


def _rejection(card: Mapping[str, Any], reason: str, detail: str = "") -> dict[str, str]:
    return {
        "card_id": str(card.get("card_id") or ""),
        "landmark": str(card.get("landmark") or ""),
        "reason": reason,
        "detail": detail,
    }


def _card_route_status(card: Mapping[str, Any], decision_shadow: Mapping[str, Any]) -> str:
    freshness = str(card.get("freshness") or "").casefold()
    if freshness in {"stale", "expired", "superseded"}:
        return "stale"
    constraint = " ".join(
        str(decision_shadow.get(key) or "")
        for key in ("route_constraint", "constraint", "status", "outcome")
    ).casefold()
    card_text = " ".join(
        str(card.get(key) or "") for key in ("category", "landmark", "action_delta_required")
    ).casefold()
    if "rejected_route" in constraint or "do_not_repeat" in constraint or "rejected route" in card_text:
        return "corrected"
    return "unresolved"


def navigation_routes_from_cards(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project already-selected repo familiarity cards into navigation routes.

    Task relevance and invalidation checks belong in ``select_repo_familiarity_packet``.
    This adapter keeps the selected card's route constraints attached so the
    shared navigation-potential layer can offer a constructive coding route
    instead of treating repo familiarity as a parallel warning channel.
    """

    routes: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, Mapping) or card.get("kind") != CARD_KIND:
            continue
        refs = _navigation_source_refs(_source_refs(card.get("source_refs")))
        if not refs:
            continue
        action_delta = _text(card.get("action_delta_required"), 360)
        first_source = _text(card.get("first_source_to_reopen"), 220)
        stop_after = _text(card.get("stop_after"), 260)
        if not action_delta or not first_source or not stop_after:
            continue
        decision_shadow = _mapping(card.get("decision_shadow"))
        status = _card_route_status(card, decision_shadow)
        source_thickness = str(decision_shadow.get("source_thickness") or "usable")
        if source_thickness not in {"thin", "usable", "strong"}:
            source_thickness = "usable"
        verb = "warn_route" if status == "corrected" else "offer_next_step"
        routes.append(
            {
                "kind": CARD_KIND,
                "route_id": card.get("card_id"),
                "route_kind": card.get("category") or "repo_familiarity",
                "title": card.get("landmark"),
                "summary": action_delta,
                "status": status,
                "frontier_proximity": "high" if status == "unresolved" else "medium",
                "route_terms": card.get("route_terms") or [],
                "source_refs": refs,
                "source_thickness": source_thickness,
                "proposed_action": {
                    "verb": verb,
                    "object": f"Reopen {first_source}; {action_delta}",
                },
                "preconditions": [
                    f"reopen first source: {first_source}",
                    f"stop after: {stop_after}",
                ],
                "do_not_do": [
                    "treat_repo_familiarity_as_current_code_truth",
                    *_strings(card.get("do_not_use_for"), limit=6),
                ],
                "repo_familiarity": {
                    "first_source_to_reopen": first_source,
                    "stop_after": stop_after,
                    "freshness": _text(card.get("freshness"), 80),
                    "invalidation_present": bool(card.get("invalidation")),
                    "decision_shadow_present": bool(decision_shadow),
                },
                "annoyance_risk": "medium",
            }
        )
    return routes


def select_repo_familiarity_packet(
    cards: Sequence[Mapping[str, Any]],
    *,
    task: str,
    current_fingerprints: Mapping[str, str] | None = None,
    current_commit: str = "",
    max_cards: int = DEFAULT_MAX_CARDS,
    max_packet_bytes: int = DEFAULT_MAX_PACKET_BYTES,
) -> dict[str, Any]:
    """Select a tiny packet that can change the next action.

    The selector rejects stale or irrelevant cards before budget selection so a
    stale familiarity map cannot become another route the foreground agent must
    audit. The report is only a deterministic cost proxy; live token or tool-call
    savings require a separate benchmark arm.
    """

    task_terms = _terms(task)
    current_fingerprints = current_fingerprints or {}
    rejected: list[dict[str, str]] = []
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for card in cards:
        if card.get("kind") != CARD_KIND:
            continue
        stale = _stale_reason(
            card,
            current_fingerprints=current_fingerprints,
            current_commit=current_commit,
        )
        if stale:
            rejected.append(_rejection(card, "stale_invalidation", stale))
            continue
        if not card.get("action_delta_required") or not card.get("stop_after"):
            rejected.append(_rejection(card, "missing_action_delta_contract"))
            continue
        score = _task_score(card, task_terms)
        if score <= 0:
            rejected.append(_rejection(card, "irrelevant_to_task"))
            continue
        candidates.append((score, card))

    candidates.sort(key=lambda item: (-item[0], str(item[1].get("card_id") or "")))
    selected: list[dict[str, Any]] = []
    packet_bytes = 0
    for _, card in candidates:
        if len(selected) >= max_cards:
            rejected.append(_rejection(card, "packet_card_budget_exceeded"))
            continue
        clean = dict(card)
        card_size = _card_bytes(clean)
        if packet_bytes + card_size > max_packet_bytes:
            rejected.append(_rejection(card, "packet_byte_budget_exceeded", str(card_size)))
            continue
        selected.append(clean)
        packet_bytes += card_size

    fast_reject_count = len([item for item in rejected if item["reason"] == "stale_invalidation"])
    irrelevant_count = len([item for item in rejected if item["reason"] == "irrelevant_to_task"])
    return {
        "ok": True,
        "kind": PACKET_KIND,
        "schema_version": SCHEMA_VERSION,
        "task_terms": sorted(task_terms),
        "selected_cards": selected,
        "rejected_cards": rejected,
        "packet_bytes": packet_bytes,
        "packet_budget": {
            "max_cards": max_cards,
            "max_packet_bytes": max_packet_bytes,
            "action_delta_required": True,
            "stop_rule_required": True,
        },
        "cost_delta_report": {
            "deterministic_proxy_only": True,
            "cannot_claim_live_cost_reduction": True,
            "selected_card_count": len(selected),
            "packet_bytes": packet_bytes,
            "estimated_reopen_count": len(
                [card for card in selected if card.get("first_source_to_reopen")]
            ),
            "fast_reject_count": fast_reject_count,
            "irrelevant_reject_count": irrelevant_count,
            "wrong_route_drag_count": 0,
        },
        "policy": {
            "source_backed_familiarity_map": True,
            "navigation_not_truth": True,
            "no_coding_only_pivot": True,
        },
    }
