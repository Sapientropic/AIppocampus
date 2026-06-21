"""Local same-machine recall/deepen selector cache helpers.

The agent recall facade needs a convenient mutable "last recall" slot for
ordinary foreground use, plus stable selector snapshots for agents that may run
parallel diagnostics before they deepen a route. This module owns that local
navigation state so compact projection and CLI rendering do not grow into cache
policy owners.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

LAST_RECALL_CACHE_ENV = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
RECALL_SELECTOR_ID_RE = re.compile(r"^sel_[0-9a-f]{12,32}$")
LOCAL_REOPEN_TOKEN_ENCODING = "utf8_xor_v1_not_encryption"
_LOCAL_REOPEN_TOKEN_MASK = 0xA5
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)[A-Za-z0-9_]*=\S+",
    re.I,
)


def last_recall_cache_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get(LAST_RECALL_CACHE_ENV)
    if env:
        return Path(env).resolve()
    return core.aippocampus_registry_dir().resolve() / "agent" / "last-recall.json"


def recall_selector_cache_dir(last_recall_path_value: str | Path | None = None) -> Path:
    return last_recall_cache_path(last_recall_path_value).parent / "recall-selectors"


def recall_selector_cache_path(
    selector_id: str,
    *,
    last_recall_path_value: str | Path | None = None,
) -> Path:
    clean_id = str(selector_id or "").strip()
    if not RECALL_SELECTOR_ID_RE.match(clean_id):
        raise ValueError("recall selector id has an unsupported shape")
    return recall_selector_cache_dir(last_recall_path_value) / f"{clean_id}.json"


def _selector_request_seed(cache: Mapping[str, Any]) -> str:
    requests = [
        {
            "request_index": request.get("request_index"),
            "route_id": request.get("route_id"),
            "handle_sha256_12": request.get("handle_sha256_12"),
        }
        for request in cache.get("requests") or []
        if isinstance(request, Mapping)
    ]
    context_value = cache.get("context")
    context: Mapping[str, Any] = context_value if isinstance(context_value, Mapping) else {}
    return json.dumps(
        {
            "written_at": cache.get("written_at"),
            "requests": requests[:25],
            "project": context.get("project"),
            "query": context.get("query"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def write_recall_selector_snapshot(path: str | Path | None = None) -> str | None:
    """Persist an isolated same-machine selector for one recall result.

    The default last-recall cache is intentionally convenient and mutable. A
    foreground agent, however, may run diagnostics or parallel recall before it
    deepens a selected route. The selector snapshot gives compact output a
    stable local id without exposing the private reopen token or a machine path.
    """

    try:
        cache = read_last_recall_cache(path)
    except Exception:
        return None
    requests = [item for item in cache.get("requests") or [] if isinstance(item, Mapping)]
    if not requests:
        return None
    selector_id = core.stable_text_fingerprint(
        _selector_request_seed(cache),
        namespace="agent-recall-selector",
        length=16,
        prefix="sel",
    )
    snapshot = dict(cache)
    snapshot["selector_id"] = selector_id
    snapshot["selector_kind"] = "isolated_recall_selector_snapshot"
    snapshot["selector_written_at"] = core.now_utc()
    boundary = dict(snapshot.get("privacy_boundary") or {})
    boundary.update(
        {
            "selector_id_public_safe": True,
            "selector_id_exposes_local_path": False,
            "selector_snapshot_is_same_machine_only": True,
        }
    )
    snapshot["privacy_boundary"] = boundary
    try:
        target = recall_selector_cache_path(selector_id, last_recall_path_value=path)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(target, snapshot)
    except OSError:
        return None
    return selector_id


def _encode_local_reopen_token(value: Any) -> dict[str, Any]:
    """Encode a local reopen token so it is not stored as ordinary text.

    This is an accidental-disclosure guard for a same-machine cache, not a
    cryptographic promise. The handle remains local-private navigation material;
    public output should keep using `--public` / `--compact-json`.
    """

    raw_text = (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if isinstance(value, Mapping)
        else str(value or "")
    )
    raw = raw_text.encode("utf-8")
    return {
        "encoding": LOCAL_REOPEN_TOKEN_ENCODING,
        "bytes": [byte ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw],
    }


def _decode_local_reopen_token(value: Any) -> str:
    if isinstance(value, Mapping) and value.get("encoding") == LOCAL_REOPEN_TOKEN_ENCODING:
        raw_bytes = value.get("bytes")
        if not isinstance(raw_bytes, list):
            return ""
        try:
            return bytes(int(byte) ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw_bytes).decode(
                "utf-8"
            )
        except (TypeError, ValueError, UnicodeDecodeError):
            return ""
    return ""


def _local_reopen_context_token(
    *,
    cwd: str | Path | None,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    macro_state_path: str | Path | None,
) -> dict[str, Any] | None:
    context: dict[str, str] = {}
    if cwd:
        context["cwd"] = str(Path(cwd).resolve())
    if clean_source_dir:
        context["clean_source_dir"] = str(Path(clean_source_dir).resolve())
    if registry_dir:
        context["registry_dir"] = str(Path(registry_dir).resolve())
    if macro_state_path:
        context["macro_state_jsonl"] = str(Path(macro_state_path).resolve())
    if not context:
        return None
    return _encode_local_reopen_token(context)


def _decode_local_reopen_context(value: Any) -> dict[str, Any]:
    raw = _decode_local_reopen_token(value)
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _public_safe_recall_query(query: str | None) -> str:
    clean = str(redact_sensitive_values(redact_private_paths(query or ""))).strip()
    clean = SENSITIVE_ASSIGNMENT_RE.sub("", clean)
    clean = clean.replace("<sensitive-value-redacted>", "")
    clean = " ".join(clean.split())
    return clean[:240]


def public_compact_route_receipts(routes: Any) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for route in routes or []:
        if not isinstance(route, Mapping):
            continue
        action = route.get("action")
        action_map = action if isinstance(action, Mapping) else {}
        compact_action = {
            "id": action_map.get("id"),
            "tool_name": action_map.get("tool_name"),
            "arguments": action_map.get("arguments"),
            "command": action_map.get("command") or action_map.get("cli_command"),
            "command_template": action_map.get("command_template")
            or action_map.get("cli_command_template"),
            "requires": action_map.get("requires"),
            "template_only": action_map.get("template_only"),
            "route_choice_posture": action_map.get("route_choice_posture"),
            "confidence": action_map.get("confidence"),
            "claim_boundary": action_map.get("claim_boundary"),
        }
        receipts.append(
            {
                key: value
                for key, value in {
                    "index": route.get("index") or route.get("route_index"),
                    "label": route.get("label") or route.get("route_label"),
                    "why_this_route": route.get("why_this_route"),
                    "route_choice_posture": route.get("route_choice_posture"),
                    "confidence": route.get("confidence"),
                    "claim_boundary": route.get("claim_boundary"),
                    "already_opened": route.get("already_opened"),
                    "action": {
                        key: value
                        for key, value in compact_action.items()
                        if value not in (None, "", [])
                    },
                }.items()
                if value not in (None, "", [], {})
            }
        )
    return receipts


def _public_projection_route_ids(data: Mapping[str, Any]) -> dict[int, str]:
    route_ids: dict[int, str] = {}
    for route in data.get("routes") or []:
        if not isinstance(route, Mapping):
            continue
        try:
            index = int(route.get("index") or route.get("route_index") or 0)
        except (TypeError, ValueError):
            index = 0
        raw_diagnostic = route.get("diagnostic_route")
        diagnostic = raw_diagnostic if isinstance(raw_diagnostic, Mapping) else {}
        route_id = str(route.get("route_id") or diagnostic.get("route_id") or "").strip()
        if index > 0 and route_id:
            route_ids[index] = route_id
    return route_ids


def _handle_sha256_12(handle: Any) -> str:
    if handle is None:
        return ""
    handle_arg = (
        json.dumps(handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if isinstance(handle, Mapping)
        else str(handle)
    )
    return hashlib.sha256(handle_arg.encode("utf-8")).hexdigest()[:12] if handle_arg else ""


def last_recall_route_key(route_id: Any, handle_sha256_12: Any) -> str:
    route = str(route_id or "").strip()
    digest = str(handle_sha256_12 or "").strip()
    return f"{route}|{digest}" if route and digest else ""


def last_recall_route_wildcard_key(route_id: Any) -> str:
    route = str(route_id or "").strip()
    return f"{route}|*" if route else ""


def _opened_routes_by_key(cache: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    opened: dict[str, dict[str, Any]] = {}
    for item in cache.get("opened_routes") or []:
        if not isinstance(item, Mapping):
            continue
        key = last_recall_route_key(item.get("route_id"), item.get("handle_sha256_12"))
        if key:
            opened[key] = dict(item)
    return opened


def opened_route_keys_from_last_recall_cache(path: str | Path | None = None) -> set[str]:
    try:
        cache = read_last_recall_cache(path)
    except Exception:
        return set()
    keys = set(_opened_routes_by_key(cache))
    for item in cache.get("opened_routes") or []:
        if isinstance(item, Mapping):
            wildcard = last_recall_route_wildcard_key(item.get("route_id"))
            if wildcard:
                keys.add(wildcard)
    return keys


def write_last_recall_cache(
    deepen_requests: Iterable[Any],
    *,
    query: str | None = None,
    cwd: str | Path | None,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    macro_state_path: str | Path | None,
    project: str,
    max_matches: int,
    schema_version: str,
    path: str | Path | None = None,
) -> bool:
    requests: list[dict[str, Any]] = []
    target = last_recall_cache_path(path)
    try:
        previous_cache = read_last_recall_cache(path) if target.exists() else {}
    except Exception:
        previous_cache = {}
    previous_opened = _opened_routes_by_key(previous_cache)
    for request in deepen_requests:
        if not isinstance(request, Mapping) or not request.get("handle"):
            continue
        handle_digest = str(request.get("handle_sha256_12") or "").strip() or _handle_sha256_12(
            request.get("handle")
        )
        opened_key = last_recall_route_key(request.get("route_id"), handle_digest)
        opened_entry = previous_opened.get(opened_key) if opened_key else None
        requests.append(
            {
                "request_index": request.get("request_index"),
                "route_id": request.get("route_id"),
                "handle_sha256_12": handle_digest,
                "matched_cue_family": request.get("matched_cue_family"),
                "matched_cue_anchors": request.get("matched_cue_anchors"),
                "candidate_source_kind": request.get("candidate_source_kind"),
                "source_ref_digest": request.get("source_ref_digest"),
                "selected_source_ref_count": request.get("selected_source_ref_count"),
                "apw_candidate_route_id": request.get("apw_candidate_route_id"),
                "apw_candidate_id": request.get("apw_candidate_id"),
                "apw_route_identity": request.get("apw_route_identity"),
                "local_reopen_token": _encode_local_reopen_token(request.get("handle")),
                "opened": bool(opened_entry),
                "opened_at": opened_entry.get("opened_at") if opened_entry else None,
                "opened_count": opened_entry.get("opened_count") if opened_entry else 0,
            }
        )
    if not requests:
        return False
    context_token = _local_reopen_context_token(
        cwd=cwd,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        macro_state_path=macro_state_path,
    )
    cache = {
        "kind": "aippocampus_agent_last_recall",
        "schema_version": schema_version,
        "written_at": core.now_utc(),
        "requests": requests[:25],
        # This is session-local route-opened state, not a new memory layer. It
        # stores only route id plus opaque handle digest so the next foreground
        # recall does not nag the agent to reopen exactly the same source window
        # it already opened. If the handle changes, the route is eligible again.
        "opened_routes": list(previous_opened.values())[:100],
        "context": {
            "project": project,
            "max": max_matches,
            "query": _public_safe_recall_query(query),
            "path_scope": "caller_supplied_cwd_only_not_persisted",
            "local_reopen_context_token": context_token,
        },
        "privacy_boundary": {
            "local_cache_only": True,
            "default_human_output_prints_cache_path": False,
            "derived_local_source_paths_persisted": True,
            "derived_local_source_paths_plaintext_persisted": False,
            "opaque_handles_are_navigation_not_facts": True,
            "opaque_handles_cleartext_persisted": False,
            "local_reopen_context_token_persisted": bool(context_token),
            "local_reopen_token_encoding": LOCAL_REOPEN_TOKEN_ENCODING,
            "local_reopen_token_encoding_is_encryption": False,
        },
    }
    try:
        # Local-only reopen handles are not credentials, but they are still
        # intentionally private navigation tokens. The cache stores an encoded
        # token for same-machine follow-through only; keep it out of human
        # output and avoid persisting derived source/registry paths above.
        atomic_write_json(target, cache)
    except OSError:
        return False
    return True


def mark_last_recall_request_opened(
    request_index: int,
    *,
    path: str | Path | None = None,
    outcome: str = "source_open",
) -> bool:
    cache = read_last_recall_cache(path)
    requests = [dict(request) for request in cache.get("requests") or [] if isinstance(request, Mapping)]
    opened_routes = _opened_routes_by_key(cache)
    changed = False
    opened_at = core.now_utc()
    for request in requests:
        try:
            index = int(request.get("request_index") or 0)
        except (TypeError, ValueError):
            index = 0
        if index != int(request_index):
            continue
        route_id = str(request.get("route_id") or "").strip()
        digest = str(request.get("handle_sha256_12") or "").strip()
        key = last_recall_route_key(route_id, digest)
        if not key:
            continue
        opened_count = int(request.get("opened_count") or 0) + 1
        request["opened"] = True
        request["opened_at"] = opened_at
        request["opened_count"] = opened_count
        opened_routes[key] = {
            "route_id": route_id,
            "handle_sha256_12": digest,
            "opened_at": opened_at,
            "opened_count": opened_count,
            "outcome": str(outcome or "source_open"),
        }
        changed = True
        break
    if not changed:
        return False
    cache["requests"] = requests
    cache["opened_routes"] = list(opened_routes.values())[:100]
    atomic_write_json(last_recall_cache_path(path), cache)
    return True


def read_last_recall_cache(path: str | Path | None = None) -> dict[str, Any]:
    target = last_recall_cache_path(path)
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("last recall cache has an unsupported shape")
    if data.get("kind") == "aippocampus_agent_last_recall":
        return data
    if (
        path is not None
        and data.get("kind") == "aippocampus_agent_continuity_path"
        and data.get("surface") == "agent_cli_public_compact"
    ):
        default_target = last_recall_cache_path(None)
        if target != default_target and default_target.exists():
            fallback = read_last_recall_cache(None)
            fallback["public_projection_request_path"] = True
            fallback["public_projection_route_ids"] = _public_projection_route_ids(data)
            return fallback
        raise ValueError(
            "public compact recall projection needs the same-machine last recall cache; rerun agent recall"
        )
    raise ValueError("last recall cache has an unsupported shape")


def last_recall_route_choices(path: str | Path | None = None, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return route ids from the same-machine last-recall cache without handles.

    Personal controls and feedback only need the route id to write scoped,
    low-authority calibration. Keep local reopen tokens and source paths out of
    these foreground cards; those remain in deepen/explain flows.
    """

    try:
        cache = read_last_recall_cache(path)
    except Exception:
        return []
    choices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for request in cache.get("requests") or []:
        if not isinstance(request, Mapping):
            continue
        route_id = str(request.get("route_id") or "").strip()
        if not route_id or route_id in seen:
            continue
        try:
            request_index = int(request.get("request_index") or len(choices) + 1)
        except (TypeError, ValueError):
            request_index = len(choices) + 1
        choices.append(
            {
                "request_index": request_index,
                "route_id": route_id,
                "source": "last_recall_cache",
            }
        )
        seen.add(route_id)
        if len(choices) >= limit:
            break
    return choices


def handle_from_last_recall_cache(
    *,
    request_index: int,
    path: str | Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    cache = read_last_recall_cache(path)
    requests = [request for request in cache.get("requests") or [] if isinstance(request, Mapping)]
    for request in requests:
        try:
            index = int(request.get("request_index") or 0)
        except (TypeError, ValueError):
            index = 0
        if index == request_index:
            public_route_ids = cache.get("public_projection_route_ids")
            expected_route_id = (
                str(public_route_ids.get(request_index) or "").strip()
                if isinstance(public_route_ids, Mapping)
                else ""
            )
            actual_route_id = str(request.get("route_id") or "").strip()
            if expected_route_id and actual_route_id != expected_route_id:
                raise ValueError(
                    "same-machine last recall cache does not match the public recall projection"
                )
            handle = _decode_local_reopen_token(request.get("local_reopen_token"))
            if not handle and request.get("handle"):
                # Backward compatibility for caches written before the
                # local-reopen-token boundary existed.
                handle = str(request.get("handle") or "")
            context = dict(cache.get("context") or {})
            context.update(_decode_local_reopen_context(context.pop("local_reopen_context_token", None)))
            identity = request.get("apw_route_identity")
            if isinstance(identity, Mapping):
                context["apw_route_identity"] = dict(identity)
            else:
                compact_identity = {
                    "kind": "aippocampus_apw_route_identity",
                    "schema_version": 1,
                    "public_route_id": request.get("route_id"),
                    "apw_candidate_route_id": request.get("apw_candidate_route_id"),
                    "apw_candidate_id": request.get("apw_candidate_id"),
                    "source_ref_digest": request.get("source_ref_digest"),
                    "selected_source_ref_count": request.get("selected_source_ref_count"),
                    "matched_cue_anchors": request.get("matched_cue_anchors"),
                    "candidate_source_kind": request.get("candidate_source_kind"),
                    "raw_refs_redacted_from_compact_output": True,
                }
                compact_identity = {
                    key: value
                    for key, value in compact_identity.items()
                    if value not in (None, "", [], {})
                }
                if compact_identity.get("source_ref_digest"):
                    context["apw_route_identity"] = compact_identity
            return handle, context
    raise ValueError(f"last recall cache does not contain request {request_index}")


def query_from_last_recall_cache(path: str | Path | None = None) -> str | None:
    try:
        cache = read_last_recall_cache(path)
    except Exception:
        return None
    context_value = cache.get("context")
    if not isinstance(context_value, Mapping):
        return None
    context = context_value
    query = str(context.get("query") or "").strip()
    return query or None
