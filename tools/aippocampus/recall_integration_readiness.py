#!/usr/bin/env python3
"""Thin foreground-callability gate for recall-related surfaces."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from report_provenance import git_worktree_evidence

READY_STATUSES = {
    "callable",
    "useful",
    "diagnostic_only",
    "proxy_only",
    "blocked",
}

DEFAULT_SOURCE_CHAIN_CUE = "最早那条机械飞升和海马体的讨论"
DEFAULT_SOURCE_CHAIN_ANCHORS = ["机械飞升", "基因飞升"]
DEFAULT_SOURCE_CHAIN_EXPECTED_REFS = [
    {
        "thread_key": "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
        "message_id": "msg_b2dfe27431403cdc8ffa",
        "line": 88,
    }
]
SOURCE_CHAIN_PROBE_SPECS = (
    {
        "probe_label": "live_registry_source_chain:mechanical_origin",
        "cue": DEFAULT_SOURCE_CHAIN_CUE,
        "anchors": DEFAULT_SOURCE_CHAIN_ANCHORS,
        "expected_source_refs": DEFAULT_SOURCE_CHAIN_EXPECTED_REFS,
    },
    {
        "probe_label": "live_registry_source_chain:canonical_origin_doc",
        "cue": "未干的地图 origin essay source-backed continuity",
        "anchors": ["未干的地图"],
        "expected_source_refs": [
            {
                "thread_key": "session:019e6071-5a9b-71d2-b15a-27f6ba211494",
                "message_id": "msg_ea1e9e5ea23db0e8519e",
                "line": 6726,
            }
        ],
    },
)


def _surface(
    surface_id: str,
    *,
    status: str,
    owner_issue: str,
    foreground_callable: bool,
    cli_wired: bool,
    mcp_wired: bool,
    claim: str,
    command: str = "",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "surface_id": surface_id,
        "status": status,
        "owner_issue": owner_issue,
        "foreground_callable": foreground_callable,
        "cli_wired": cli_wired,
        "mcp_wired": mcp_wired,
        "claim": claim,
        "command": command,
        "reason": reason,
    }


def default_surfaces() -> list[dict[str, Any]]:
    return [
        _surface(
            "apw_fallback",
            status="callable",
            owner_issue="#2561",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="APW fallback is callable as opt-in/weak-recall recovery, not default ranking.",
            command="aippocampus agent recall <cue> --apw-fallback --json",
        ),
        _surface(
            "mcp_agent_recall_deepen_parity",
            status="callable",
            owner_issue="#2561/#2602",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim=(
                "MCP agent_recall can emit a deepen action that MCP agent_deepen follows "
                "to the expected source-chain target."
            ),
        ),
        _surface(
            "low_specificity_recall_recovery",
            status="callable",
            owner_issue="#2562",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="Weak compact labels keep low-confidence choices and a safer recovery action.",
        ),
        _surface(
            "known_artifact_recall_dogfood",
            status="diagnostic_only",
            owner_issue="#2556",
            foreground_callable=False,
            cli_wired=True,
            mcp_wired=False,
            claim="Dogfood reports static setup separately from live recall/search discoverability.",
            command="python tools/aippocampus/smoke/known_artifact_recall_dogfood.py --json",
        ),
        _surface(
            "repo_familiarity_fallback",
            status="callable",
            owner_issue="#2557",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="Current-checkout repo familiarity can become a source-open action for repo-doc weak recall.",
        ),
        _surface(
            "ambient_tiny_agent_recall_affordance",
            status="callable",
            owner_issue="#2554",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim=(
                "Ambient tiny recall can emit an action-only agent_recall hint after "
                "source-open and drag-control gates pass; it is not default source evidence."
            ),
            command="aippocampus agent recall <distinctive continuity cue> --json",
            reason="host-replay tiny affordance gate passed; default foreground evidence remains diagnostic-only",
        ),
        _surface(
            "wrong_route_feedback_demotion",
            status="callable",
            owner_issue="#2553/#2560",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="Wrong-route feedback can target APW route identity aliases and suppress reruns.",
        ),
    ]


def _clean_surfaces(extra_surfaces: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    surfaces = [dict(surface) for surface in default_surfaces()]
    for raw in extra_surfaces or []:
        if isinstance(raw, Mapping):
            surfaces.append(dict(raw))
    return surfaces


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    scripts = repo_root / "skills" / "aippocampus" / "scripts"
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(scripts) if not prior else str(scripts) + os.pathsep + prior
    return env


def _run_source_cli_json(
    repo_root: Path,
    args: list[str],
    *,
    timeout: float = 30,
    stdin: str | None = None,
) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=stdin,
        capture_output=True,
        timeout=timeout,
        env=_source_env(repo_root),
        check=False,
    )
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        payload.setdefault("stderr_present", True)
    return payload


def _mcp_tool_payload(repo_root: Path, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    request = {
        "jsonrpc": "2.0",
        "id": f"readiness-{name}",
        "method": "tools/call",
        "params": {"name": name, "arguments": dict(arguments)},
    }
    response = _run_source_cli_json(
        repo_root,
        ["mcp"],
        stdin=json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n",
    )
    raw_result = response.get("result")
    result: Mapping[str, Any] = raw_result if isinstance(raw_result, Mapping) else {}
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return {"ok": False, "error": "mcp_response_missing_content", "response": response}
    first = content[0] if isinstance(content[0], Mapping) else {}
    text = str(first.get("text") or "")
    try:
        payload = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": "mcp_tool_payload_not_json", "response": response}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "mcp_tool_payload_not_object", "response": response}
    payload.setdefault("ok", not bool(result.get("isError")))
    return payload


def _apw_candidate_input(payload: Mapping[str, Any]) -> bool:
    policy = payload.get("associative_path_policy")
    if not isinstance(policy, Mapping):
        return False
    return bool(policy.get("apw_candidate_input_available"))


def _apw_fallback_status(payload: Mapping[str, Any]) -> str:
    fallback = payload.get("associative_path_fallback")
    if not isinstance(fallback, Mapping):
        return ""
    return str(fallback.get("status") or fallback.get("decision") or "")


def _action_id(payload: Mapping[str, Any]) -> str:
    action = payload.get("foreground_action")
    if not isinstance(action, Mapping):
        return ""
    return str(action.get("id") or "")


def _action_arguments(payload: Mapping[str, Any]) -> dict[str, Any]:
    action = payload.get("foreground_action")
    if not isinstance(action, Mapping):
        return {}
    arguments = action.get("arguments")
    return dict(arguments) if isinstance(arguments, Mapping) else {}


def _source_text_from_deepen(payload: Mapping[str, Any]) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else payload
    if not isinstance(result, Mapping):
        return ""
    source_window = result.get("source_window")
    if isinstance(source_window, Mapping):
        messages = source_window.get("messages")
        if isinstance(messages, list):
            return "\n".join(
                str(message.get("text") or "")
                for message in messages
                if isinstance(message, Mapping)
            )
        if source_window.get("text"):
            return str(source_window.get("text") or "")
    snippet = result.get("primary_source_snippet")
    if isinstance(snippet, Mapping):
        return str(snippet.get("text") or "")
    return ""


def _source_refs_from_deepen(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else payload
    if not isinstance(result, Mapping):
        return []
    refs = [dict(ref) for ref in result.get("source_refs") or [] if isinstance(ref, Mapping)]
    source_window = result.get("source_window")
    if isinstance(source_window, Mapping):
        messages = source_window.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, Mapping):
                    continue
                refs.append(
                    {
                        key: message.get(key)
                        for key in (
                            "thread_key",
                            "source_id",
                            "message_id",
                            "turn_id",
                            "turn_index",
                            "line",
                            "source_line",
                        )
                        if message.get(key) not in (None, "")
                    }
                )
    return refs


def _target_source_matched(
    opened_refs: Iterable[Mapping[str, Any]],
    expected_refs: Iterable[Mapping[str, Any]],
) -> bool | None:
    expected = [
        {key: str(value) for key, value in ref.items() if value not in (None, "")}
        for ref in expected_refs
        if isinstance(ref, Mapping)
    ]
    if not expected:
        return None
    opened = [
        {key: str(value) for key, value in ref.items() if value not in (None, "")}
        for ref in opened_refs
        if isinstance(ref, Mapping)
    ]
    for target in expected:
        for ref in opened:
            if all(ref.get(key) == value for key, value in target.items()):
                return True
    return False


def _anchor_hits(text: str, anchors: Iterable[str]) -> int:
    haystack = str(text or "")
    return sum(1 for anchor in anchors if str(anchor or "") and str(anchor) in haystack)


def _recall_selector(payload: Mapping[str, Any]) -> str:
    selector = str(payload.get("recall_selector_id") or "").strip()
    if selector:
        return selector
    action = payload.get("foreground_action")
    if not isinstance(action, Mapping):
        action = payload.get("foreground_action_card")
    if not isinstance(action, Mapping):
        return ""
    arguments = action.get("arguments")
    if not isinstance(arguments, Mapping):
        canonical = action.get("canonical_action")
        arguments = canonical.get("arguments") if isinstance(canonical, Mapping) else None
    if not isinstance(arguments, Mapping):
        return ""
    return str(arguments.get("recall_selector") or "").strip()


def _source_chain_role(payload: Mapping[str, Any]) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    for item in (payload, result):
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("source_chain_role") or "").strip()
        if role:
            return role
        gate = item.get("source_anchor_gate")
        if isinstance(gate, Mapping):
            role = str(gate.get("source_chain_role") or "").strip()
            if role:
                return role
    return ""


def _target_source_gate(payload: Mapping[str, Any]) -> bool | None:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    for item in (payload, result):
        if not isinstance(item, Mapping):
            continue
        if "target_source_matched" in item:
            return bool(item.get("target_source_matched"))
        gate = item.get("source_anchor_gate")
        if isinstance(gate, Mapping) and "target_source_matched" in gate:
            return bool(gate.get("target_source_matched"))
        recall_gate = item.get("recall_gate_context")
        if isinstance(recall_gate, Mapping) and "target_source_matched" in recall_gate:
            return bool(recall_gate.get("target_source_matched"))
    return None


def _optional_path_args(
    *,
    cwd: Path,
    clean_source_dir: Path | None = None,
    registry_dir: Path | None = None,
    last_recall_path: Path | None = None,
) -> list[str]:
    args = ["--cwd", str(cwd)]
    if clean_source_dir is not None:
        args.extend(["--clean-source-dir", str(clean_source_dir)])
    if registry_dir is not None:
        args.extend(["--registry-dir", str(registry_dir)])
    if last_recall_path is not None:
        args.extend(["--last-recall-path", str(last_recall_path)])
    return args


def _cli_apw_deepen(
    repo_root: Path,
    action: Mapping[str, Any],
    *,
    cwd: Path,
    clean_source_dir: Path | None,
    registry_dir: Path | None,
    last_recall_path: Path | None,
) -> tuple[dict[str, Any], str]:
    raw_arguments = action.get("arguments")
    arguments: Mapping[str, Any] = raw_arguments if isinstance(raw_arguments, Mapping) else {}
    request_index = arguments.get("request_index")
    recall_selector = arguments.get("recall_selector")
    if request_index is None or not recall_selector:
        return {}, ""
    args = [
        "agent",
        "deepen",
        "--request",
        str(request_index),
        "--recall-selector",
        str(recall_selector),
        "--json",
        "--detail",
        "full",
        *_optional_path_args(
            cwd=cwd,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
            last_recall_path=last_recall_path,
        ),
    ]
    return _run_source_cli_json(repo_root, args), " ".join(["aippocampus", *args])


def _mcp_apw_deepen(
    repo_root: Path,
    action: Mapping[str, Any],
    *,
    cwd: Path,
    clean_source_dir: Path | None,
    registry_dir: Path | None,
    last_recall_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_arguments = action.get("arguments")
    arguments: Mapping[str, Any] = raw_arguments if isinstance(raw_arguments, Mapping) else {}
    request_index = arguments.get("request_index")
    recall_selector = arguments.get("recall_selector")
    if request_index is None or not recall_selector:
        return {}, {}
    tool_args: dict[str, Any] = {
        "request_index": request_index,
        "recall_selector": recall_selector,
        "cwd": str(cwd),
        "detail": "full",
    }
    if clean_source_dir is not None:
        tool_args["clean_source_dir"] = str(clean_source_dir)
    if registry_dir is not None:
        tool_args["registry_dir"] = str(registry_dir)
    if last_recall_path is not None:
        tool_args["last_recall_path"] = str(last_recall_path)
    return _mcp_tool_payload(repo_root, "agent_deepen", tool_args), tool_args


def _source_chain_identity_probe(
    repo_root: Path,
    *,
    cue: str = DEFAULT_SOURCE_CHAIN_CUE,
    anchors: Iterable[str] = DEFAULT_SOURCE_CHAIN_ANCHORS,
    expected_source_refs: Iterable[Mapping[str, Any]] = DEFAULT_SOURCE_CHAIN_EXPECTED_REFS,
    probe_label: str = "live_registry_source_chain",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Verify a real source-chain route opens the intended source on CLI and MCP.

    The APW fixture probe checks tool wiring and source-open mechanics in a
    portable clean-source sandbox. This probe guards the stricter closeout bar
    from #2602: default cwd/registry recall must not become route-positive while
    deepening a nearby or generic source. It intentionally records only source
    ids/lines and anchor counts, never private paths.
    """

    workspace = cwd or repo_root
    anchors = list(anchors)
    expected_refs = list(expected_source_refs)
    failures: list[dict[str, Any]] = []

    cli_recall_args = [
        "agent",
        "recall",
        cue,
        "--json",
        "--detail",
        "full",
        "--cwd",
        str(workspace),
    ]
    cli_recall = _run_source_cli_json(repo_root, cli_recall_args, timeout=45)
    cli_selector = _recall_selector(cli_recall)
    cli_deepen_args: list[str] = []
    cli_deepen: dict[str, Any] = {}
    if cli_recall.get("status") != "ok":
        failures.append(
            {
                "surface": "cli",
                "reason": "cli_source_chain_recall_not_ok",
                "status": cli_recall.get("status"),
            }
        )
    elif not cli_selector:
        failures.append({"surface": "cli", "reason": "cli_source_chain_selector_missing"})
    else:
        cli_deepen_args = [
            "agent",
            "deepen",
            "--request",
            "1",
            "--recall-selector",
            cli_selector,
            "--json",
            "--detail",
            "full",
            "--cwd",
            str(workspace),
        ]
        cli_deepen = _run_source_cli_json(repo_root, cli_deepen_args, timeout=45)

    mcp_recall_args: dict[str, Any] = {
        "query": cue,
        "cwd": str(workspace),
        "detail": "full",
        "max": 5,
    }
    mcp_recall = _mcp_tool_payload(repo_root, "agent_recall", mcp_recall_args)
    mcp_selector = _recall_selector(mcp_recall)
    mcp_deepen_args: dict[str, Any] = {}
    mcp_deepen: dict[str, Any] = {}
    if mcp_recall.get("status") != "ok":
        failures.append(
            {
                "surface": "mcp",
                "reason": "mcp_source_chain_recall_not_ok",
                "status": mcp_recall.get("status"),
            }
        )
    elif not mcp_selector:
        failures.append({"surface": "mcp", "reason": "mcp_source_chain_selector_missing"})
    else:
        mcp_deepen_args = {
            "request_index": 1,
            "recall_selector": mcp_selector,
            "cwd": str(workspace),
            "detail": "full",
        }
        mcp_deepen = _mcp_tool_payload(repo_root, "agent_deepen", mcp_deepen_args)

    def evaluate(surface: str, recall: Mapping[str, Any], deepen: Mapping[str, Any]) -> dict[str, Any]:
        text = _source_text_from_deepen(deepen)
        opened_refs = _source_refs_from_deepen(deepen)
        target_ref_matched = _target_source_matched(opened_refs, expected_refs)
        gate_matched = _target_source_gate(deepen)
        opened_anchor_hits = _anchor_hits(text, anchors)
        if deepen and deepen.get("status") != "ok":
            failures.append(
                {
                    "surface": surface,
                    "reason": f"{surface}_source_chain_deepen_not_ok",
                    "status": deepen.get("status"),
                }
            )
        if target_ref_matched is False:
            failures.append(
                {
                    "surface": surface,
                    "reason": f"{surface}_source_chain_deepen_opened_wrong_source",
                    "target_source_matched": False,
                }
            )
        if gate_matched is False:
            failures.append(
                {
                    "surface": surface,
                    "reason": f"{surface}_source_chain_gate_rejected_target_source",
                    "target_source_matched": False,
                }
            )
        if opened_anchor_hits < len(anchors):
            failures.append(
                {
                    "surface": surface,
                    "reason": f"{surface}_source_chain_anchor_hits_incomplete",
                    "opened_anchor_hits": opened_anchor_hits,
                    "required_anchor_hits": len(anchors),
                }
            )
        repo_familiarity = recall.get("repo_familiarity_fallback")
        return {
            "recall_status": recall.get("status"),
            "deepen_status": deepen.get("status") if deepen else None,
            "recall_selector_available": bool(_recall_selector(recall)),
            "source_chain_role": _source_chain_role(deepen),
            "target_source_matched": target_ref_matched,
            "gate_target_source_matched": gate_matched,
            "opened_anchor_hits": opened_anchor_hits,
            "required_anchor_hits": len(anchors),
            "repo_familiarity_status": (
                repo_familiarity.get("status") if isinstance(repo_familiarity, Mapping) else None
            ),
            "source_refs": opened_refs[:3],
        }

    cli_summary = evaluate("cli", cli_recall, cli_deepen)
    mcp_summary = evaluate("mcp", mcp_recall, mcp_deepen)
    status = "blocked" if failures else "passed"
    return {
        "kind": "aippocampus_source_chain_identity_probe",
        "probe_label": probe_label,
        "cue": cue,
        "status": status,
        "ok": not failures,
        "failures": failures,
        "commands": {
            "cli_recall": " ".join(["aippocampus", *cli_recall_args]),
            "cli_deepen": " ".join(["aippocampus", *cli_deepen_args]) if cli_deepen_args else "",
            "mcp_agent_recall_arguments": mcp_recall_args,
            "mcp_agent_deepen_arguments": mcp_deepen_args,
        },
        "expected_source_refs": expected_refs,
        "anchors": anchors,
        "cli": cli_summary,
        "mcp": mcp_summary,
        "claim_boundary": (
            "live registry/source-chain probe; source claims still require the returned source window"
        ),
    }


def _source_chain_identity_probe_suite(repo_root: Path) -> dict[str, Any]:
    probes = [
        _source_chain_identity_probe(
            repo_root,
            cue=str(spec["cue"]),
            anchors=cast(Iterable[str], spec["anchors"]),
            expected_source_refs=cast(
                Iterable[Mapping[str, Any]],
                spec["expected_source_refs"],
            ),
            probe_label=str(spec["probe_label"]),
        )
        for spec in SOURCE_CHAIN_PROBE_SPECS
    ]
    failures: list[dict[str, Any]] = []
    for probe in probes:
        for failure in probe.get("failures") or []:
            if not isinstance(failure, Mapping):
                continue
            failures.append(
                {
                    **dict(failure),
                    "probe_label": probe.get("probe_label"),
                    "cue": probe.get("cue"),
                }
            )
    status = "blocked" if failures else "passed"
    return {
        "kind": "aippocampus_source_chain_identity_probe_suite",
        "probe_label": "live_registry_source_chain_suite",
        "cue": " | ".join(str(probe.get("cue") or "") for probe in probes),
        "status": status,
        "ok": not failures,
        "failures": failures,
        "probes": probes,
        "commands": {
            str(probe.get("probe_label") or index): probe.get("commands")
            for index, probe in enumerate(probes, start=1)
        },
        "expected_source_refs": {
            str(probe.get("probe_label") or index): probe.get("expected_source_refs")
            for index, probe in enumerate(probes, start=1)
        },
        "anchors": {
            str(probe.get("probe_label") or index): probe.get("anchors")
            for index, probe in enumerate(probes, start=1)
        },
        "cli": {
            "probe_count": len(probes),
            "all_target_source_matched": all(
                bool((probe.get("cli") or {}).get("target_source_matched"))
                for probe in probes
            ),
        },
        "mcp": {
            "probe_count": len(probes),
            "all_target_source_matched": all(
                bool((probe.get("mcp") or {}).get("target_source_matched"))
                for probe in probes
            ),
        },
        "claim_boundary": (
            "live registry/source-chain probe suite; source claims still require each "
            "returned source window"
        ),
    }


def _apw_mcp_probe(
    repo_root: Path,
    *,
    cue: str,
    anchors: Iterable[str],
    cwd: Path | None = None,
    clean_source_dir: Path | None = None,
    registry_dir: Path | None = None,
    last_recall_path: Path | None = None,
    expected_source_refs: Iterable[Mapping[str, Any]] | None = None,
    probe_label: str = "live",
) -> dict[str, Any]:
    """Run the APW path through source CLI and stdio MCP, then compare posture.

    This is not a broad recall-quality claim. It catches the specific closeout
    failure class from #2541/#2550/#2561/#2563: CLI or fixtures looking wired
    while the agent-facing MCP action either cannot see APW input, cannot be
    followed, or opens a source window that does not match the advertised cue.
    """

    workspace = cwd or repo_root
    cli_recall_args = [
        "agent",
        "recall",
        cue,
        "--json",
        "--apw-fallback",
        *_optional_path_args(
            cwd=workspace,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
            last_recall_path=last_recall_path,
        ),
    ]
    cli = _run_source_cli_json(repo_root, cli_recall_args)
    mcp_recall_args: dict[str, Any] = {
        "query": cue,
        "cwd": str(workspace),
        "apw_fallback": True,
        "include_associative_fallback": True,
        "max": 5,
    }
    if clean_source_dir is not None:
        mcp_recall_args["clean_source_dir"] = str(clean_source_dir)
    if registry_dir is not None:
        mcp_recall_args["registry_dir"] = str(registry_dir)
    if last_recall_path is not None:
        mcp_recall_args["last_recall_path"] = str(last_recall_path)
    mcp = _mcp_tool_payload(
        repo_root,
        "agent_recall",
        mcp_recall_args,
    )
    cli_input = _apw_candidate_input(cli)
    mcp_input = _apw_candidate_input(mcp)
    cli_status = _apw_fallback_status(cli)
    mcp_status = _apw_fallback_status(mcp)
    failures: list[dict[str, Any]] = []
    if (cli_input or cli_status == "route_candidate") and not (
        mcp_input or mcp_status == "route_candidate"
    ):
        failures.append(
            {
                "reason": "cli_apw_candidate_missing_from_mcp",
                "cli_candidate_input": cli_input,
                "cli_fallback_status": cli_status,
                "mcp_candidate_input": mcp_input,
                "mcp_fallback_status": mcp_status,
            }
        )

    raw_cli_action = cli.get("foreground_action")
    cli_action: Mapping[str, Any] = (
        raw_cli_action if isinstance(raw_cli_action, Mapping) else {}
    )
    cli_action_id = _action_id(cli)
    cli_opened_anchor_hits: int | None = None
    cli_target_source_matched: bool | None = None
    cli_deepen_command = ""
    if cli_action_id == "deepen_associative_path_fallback":
        if not _action_arguments(cli):
            failures.append({"reason": "cli_apw_action_missing_selector_or_request"})
        else:
            cli_deepen, cli_deepen_command = _cli_apw_deepen(
                repo_root,
                cli_action,
                cwd=workspace,
                clean_source_dir=clean_source_dir,
                registry_dir=registry_dir,
                last_recall_path=last_recall_path,
            )
            cli_opened_anchor_hits = _anchor_hits(_source_text_from_deepen(cli_deepen), anchors)
            cli_target_source_matched = _target_source_matched(
                _source_refs_from_deepen(cli_deepen),
                expected_source_refs or [],
            )
            if cli_opened_anchor_hits <= 0:
                failures.append(
                    {
                        "reason": "cli_apw_deepen_opened_source_without_advertised_anchors",
                        "opened_anchor_hits": cli_opened_anchor_hits,
                    }
                )
            if cli_target_source_matched is False:
                failures.append(
                    {
                        "reason": "cli_apw_deepen_opened_wrong_target_source",
                        "target_source_matched": False,
                    }
                )
    elif cli_input or cli_status == "route_candidate":
        failures.append(
            {
                "reason": "cli_apw_candidate_without_followthrough_action",
                "cli_foreground_action_id": cli_action_id,
            }
        )

    raw_mcp_action = mcp.get("foreground_action")
    mcp_action: Mapping[str, Any] = (
        raw_mcp_action if isinstance(raw_mcp_action, Mapping) else {}
    )
    mcp_action_id = _action_id(mcp)
    mcp_opened_anchor_hits: int | None = None
    mcp_target_source_matched: bool | None = None
    mcp_deepen_args: dict[str, Any] = {}
    if mcp_action_id == "deepen_associative_path_fallback":
        if not _action_arguments(mcp):
            failures.append({"reason": "mcp_apw_action_missing_selector_or_request"})
        else:
            mcp_deepen, mcp_deepen_args = _mcp_apw_deepen(
                repo_root,
                mcp_action,
                cwd=workspace,
                clean_source_dir=clean_source_dir,
                registry_dir=registry_dir,
                last_recall_path=last_recall_path,
            )
            mcp_opened_anchor_hits = _anchor_hits(_source_text_from_deepen(mcp_deepen), anchors)
            mcp_target_source_matched = _target_source_matched(
                _source_refs_from_deepen(mcp_deepen),
                expected_source_refs or [],
            )
            if mcp_opened_anchor_hits <= 0:
                failures.append(
                    {
                        "reason": "mcp_apw_deepen_opened_source_without_advertised_anchors",
                        "opened_anchor_hits": mcp_opened_anchor_hits,
                    }
                )
            if mcp_target_source_matched is False:
                failures.append(
                    {
                        "reason": "mcp_apw_deepen_opened_wrong_target_source",
                        "target_source_matched": False,
                    }
                )
    elif mcp_input or mcp_status == "route_candidate":
        failures.append(
            {
                "reason": "mcp_apw_candidate_without_followthrough_action",
                "mcp_foreground_action_id": mcp_action_id,
            }
        )

    safe_abstain = not failures and not (cli_input or mcp_input) and (
        mcp_status in {"", "abstained", "abstain"} and cli_status in {"", "abstained", "abstain"}
    )
    status = "blocked" if failures else "safe_abstain" if safe_abstain else "passed"
    return {
        "kind": "aippocampus_mcp_first_apw_probe",
        "probe_label": probe_label,
        "cue": cue,
        "status": status,
        "ok": not failures,
        "failures": failures,
        "commands": {
            "cli_recall": " ".join(["aippocampus", *cli_recall_args]),
            "cli_deepen": cli_deepen_command,
            "mcp_agent_recall_arguments": mcp_recall_args,
            "mcp_agent_deepen_arguments": mcp_deepen_args,
        },
        "cli": {
            "status": cli.get("status"),
            "apw_candidate_input_available": cli_input,
            "fallback_status": cli_status,
            "foreground_action_id": cli_action_id,
            "opened_anchor_hits": cli_opened_anchor_hits,
            "target_source_matched": cli_target_source_matched,
        },
        "mcp": {
            "status": mcp.get("status"),
            "apw_candidate_input_available": mcp_input,
            "fallback_status": mcp_status,
            "foreground_action_id": mcp_action_id,
            "opened_anchor_hits": mcp_opened_anchor_hits,
            "target_source_matched": mcp_target_source_matched,
        },
        "claim_boundary": (
            "APW probe checks foreground action wiring only; it is not a broad recall quality benchmark."
        ),
    }


def _write_apw_fixture(root: Path) -> tuple[Path, Path, Path]:
    clean = root / ".aippocampus" / "clean-source"
    registry = root / "registry"
    clean.mkdir(parents=True)
    registry.mkdir()
    rows = [
        {
            "message_id": "msg-control",
            "turn_id": "turn-control",
            "turn_index": 1,
            "source_id": "src-control",
            "source_line": 2,
            "role": "developer",
            "phase": "commentary",
            "source_use_class": "control_only",
            "text": "<goal_context> 黏菌 联想回忆 探索算法 should not be selected.",
        },
        {
            "message_id": "msg-apw",
            "turn_id": "turn-apw",
            "turn_index": 2,
            "source_id": "src-apw",
            "source_line": 3,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "公开 fixture 锚点：黏菌 联想回忆 探索算法，供 readiness gate 追踪。",
        },
    ]
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    turns = [
        {"turn_id": "turn-control", "turn_index": 1, "message_ids": ["msg-control"]},
        {"turn_id": "turn-apw", "turn_index": 2, "message_ids": ["msg-apw"]},
    ]
    with (clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in turns:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return clean, registry, root / "last-recall.json"


def _fixture_apw_mcp_probe(repo_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aippocampus-apw-readiness-") as tmp:
        root = Path(tmp)
        clean, registry, last_recall = _write_apw_fixture(root)
        return _apw_mcp_probe(
            repo_root,
            cue="黏菌 联想回忆 探索算法",
            anchors=["黏菌", "联想回忆", "探索算法"],
            cwd=root,
            clean_source_dir=clean,
            registry_dir=registry,
            last_recall_path=last_recall,
            expected_source_refs=[{"message_id": "msg-apw", "source_id": "src-apw"}],
            probe_label="fixture_current_clean_source",
        )


def _dogfood_report(repo_root: Path) -> dict[str, Any]:
    script = repo_root / "tools" / "aippocampus" / "smoke" / "known_artifact_recall_dogfood.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo_root), "--json"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("ok", False)
    payload.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        payload.setdefault("stderr_present", True)
    return payload


def _apply_dogfood_report(
    surfaces: list[dict[str, Any]],
    dogfood_report: Mapping[str, Any] | None,
) -> None:
    if dogfood_report is None:
        return
    dogfood_ok = bool(dogfood_report.get("ok"))
    for surface in surfaces:
        if surface.get("surface_id") != "known_artifact_recall_dogfood":
            continue
        surface["live_dogfood_ok"] = dogfood_ok
        surface["live_failed_owners"] = list(dogfood_report.get("failing_owners") or [])
        surface["live_case_count"] = dogfood_report.get("case_count")
        surface["live_passed_count"] = dogfood_report.get("passed_count")
        if dogfood_ok:
            surface["status"] = "diagnostic_only"
            surface["foreground_callable"] = False
            surface["reason"] = "live known-artifact dogfood passed"
        else:
            surface["status"] = "blocked"
            surface["foreground_callable"] = False
            surface["reason"] = "live known-artifact dogfood failed"
        break


def _apply_apw_probe(
    surfaces: list[dict[str, Any]],
    apw_probe: Mapping[str, Any] | None,
) -> None:
    if apw_probe is None:
        return
    failures = list(apw_probe.get("failures") or [])
    status = str(apw_probe.get("status") or "")
    probe_label = str(apw_probe.get("probe_label") or "")
    probe_scope = "fixture" if probe_label.startswith("fixture_") else "live_current_context"
    for surface in surfaces:
        if surface.get("surface_id") not in {"apw_fallback", "mcp_agent_recall_deepen_parity"}:
            continue
        surface["mcp_first_apw_probe"] = {
            "status": status,
            "ok": bool(apw_probe.get("ok")),
            "probe_label": probe_label or None,
            "probe_scope": probe_scope,
            "cue": apw_probe.get("cue"),
            "failure_reasons": [failure.get("reason") for failure in failures if isinstance(failure, Mapping)],
            "cli": apw_probe.get("cli"),
            "mcp": apw_probe.get("mcp"),
            "claim_boundary": (
                "fixture probe verifies CLI/MCP wiring, not live historical usefulness"
                if probe_scope == "fixture"
                else "live probe verifies current-context follow-through for this cue"
            ),
        }
        if failures:
            surface["status"] = "blocked"
            surface["foreground_callable"] = False
            surface["mcp_wired"] = False
            surface["reason"] = "MCP-first APW probe failed"
        elif status == "safe_abstain" and surface.get("surface_id") == "apw_fallback":
            surface["reason"] = (
                "live APW dogfood abstained safely; no APW source-open action is claimed for this cue"
            )
        elif status == "safe_abstain" and surface.get("surface_id") == "mcp_agent_recall_deepen_parity":
            surface["reason"] = (
                "MCP stayed aligned with CLI by abstaining from APW source-open for the live dogfood cue"
            )


def _apply_source_chain_probe(
    surfaces: list[dict[str, Any]],
    source_chain_probe: Mapping[str, Any] | None,
) -> None:
    if source_chain_probe is None:
        return
    failures = [
        failure
        for failure in source_chain_probe.get("failures") or []
        if isinstance(failure, Mapping)
    ]
    for surface in surfaces:
        if surface.get("surface_id") != "mcp_agent_recall_deepen_parity":
            continue
        surface["source_chain_identity_probe"] = {
            "status": source_chain_probe.get("status"),
            "ok": bool(source_chain_probe.get("ok")),
            "probe_label": source_chain_probe.get("probe_label"),
            "cue": source_chain_probe.get("cue"),
            "failure_reasons": [
                failure.get("reason") for failure in failures if failure.get("reason")
            ],
            "commands": source_chain_probe.get("commands"),
            "expected_source_refs": source_chain_probe.get("expected_source_refs"),
            "anchors": source_chain_probe.get("anchors"),
            "cli": source_chain_probe.get("cli"),
            "mcp": source_chain_probe.get("mcp"),
            "probes": source_chain_probe.get("probes"),
            "claim_boundary": source_chain_probe.get("claim_boundary"),
        }
        if failures:
            surface["status"] = "blocked"
            surface["foreground_callable"] = False
            surface["mcp_wired"] = False
            surface["reason"] = "live source-chain identity probe failed"
        else:
            surface["status"] = "useful"
            surface["reason"] = (
                "live source-chain cue passed CLI and MCP recall->deepen identity checks"
            )
        break


def _apply_foreground_mcp_failure(
    surfaces: list[dict[str, Any]],
    foreground_mcp_failure: str | None,
) -> None:
    failure = str(foreground_mcp_failure or "").strip()
    if not failure:
        return
    for surface in surfaces:
        if surface.get("surface_id") != "mcp_agent_recall_deepen_parity":
            continue
        surface["status"] = "blocked"
        surface["foreground_callable"] = False
        surface["mcp_wired"] = False
        surface["reason"] = "foreground MCP transport failed"
        surface["foreground_mcp_failure"] = failure[:200]
        surface["claim"] = (
            "MCP parity cannot be claimed while the current foreground MCP transport fails."
        )
        break


def build_recall_integration_readiness(
    extra_surfaces: Iterable[Mapping[str, Any]] | None = None,
    *,
    dogfood_report: Mapping[str, Any] | None = None,
    apw_probe: Mapping[str, Any] | None = None,
    source_chain_probe: Mapping[str, Any] | None = None,
    run_live_checks: bool = False,
    foreground_mcp_failure: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    surfaces = _clean_surfaces(extra_surfaces)
    root = repo_root or _repo_root()
    if run_live_checks and dogfood_report is None:
        dogfood_report = _dogfood_report(root)
    if run_live_checks and apw_probe is None:
        apw_probe = _fixture_apw_mcp_probe(root)
    if run_live_checks and source_chain_probe is None:
        source_chain_probe = _source_chain_identity_probe_suite(root)
    _apply_dogfood_report(surfaces, dogfood_report)
    _apply_apw_probe(surfaces, apw_probe)
    _apply_source_chain_probe(surfaces, source_chain_probe)
    _apply_foreground_mcp_failure(
        surfaces,
        foreground_mcp_failure or os.environ.get("AIPPOCAMPUS_FOREGROUND_MCP_FAILURE"),
    )
    failures: list[dict[str, Any]] = []
    for surface in surfaces:
        surface_id = str(surface.get("surface_id") or "surface")
        status = str(surface.get("status") or "")
        claim = str(surface.get("claim") or "")
        if status not in READY_STATUSES:
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "unknown_readiness_status",
                    "status": status,
                }
            )
            continue
        if status == "blocked":
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": str(surface.get("reason") or "readiness_surface_blocked"),
                    "owner_issue": surface.get("owner_issue"),
                    "live_failed_owners": surface.get("live_failed_owners"),
                }
            )
            continue
        acceptance_warnings = [
            warning
            for warning in surface.get("warnings") or []
            if isinstance(warning, Mapping) and warning.get("acceptance_bearing")
        ]
        if acceptance_warnings:
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "acceptance_bearing_warning",
                    "owner_issue": surface.get("owner_issue"),
                    "warning_count": len(acceptance_warnings),
                }
            )
        if status == "proxy_only" and "foreground" in claim.casefold():
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "proxy_only_surface_claims_foreground_callable",
                    "owner_issue": surface.get("owner_issue"),
                }
            )
        if (
            surface.get("foreground_callable")
            and surface.get("cli_wired")
            and not surface.get("mcp_wired")
        ):
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "agent_facing_cli_wired_but_mcp_unwired",
                    "owner_issue": surface.get("owner_issue"),
                }
            )
    status_counts = {
        status: sum(1 for surface in surfaces if surface.get("status") == status)
        for status in sorted(READY_STATUSES)
    }
    provenance = git_worktree_evidence(root)
    return {
        "kind": "aippocampus_recall_integration_readiness",
        "schema_version": 1,
        "ok": not failures,
        **provenance,
        "surface_count": len(surfaces),
        "status_counts": status_counts,
        "failure_count": len(failures),
        "failures": failures,
        "surfaces": surfaces,
        "claim_boundary": (
            "readiness reports foreground callability only; it is not a recall quality benchmark"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--skip-live-checks",
        action="store_true",
        help="Skip dogfood/live readiness checks and report static wiring only.",
    )
    parser.add_argument(
        "--foreground-mcp-failure",
        help=(
            "Sanitized current-foreground MCP failure, e.g. Transport closed. "
            "When supplied, readiness reports MCP parity as blocked instead of "
            "silently trusting repo-local stdio probes."
        ),
    )
    args = parser.parse_args(argv)
    report = build_recall_integration_readiness(
        run_live_checks=not args.skip_live_checks,
        foreground_mcp_failure=args.foreground_mcp_failure,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "recall integration readiness: "
            f"ok={str(report['ok']).lower()} surfaces={report['surface_count']} "
            f"failures={report['failure_count']}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
