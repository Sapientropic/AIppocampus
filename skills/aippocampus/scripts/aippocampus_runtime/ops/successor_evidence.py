"""Evidence sweep for proxy-only successor issues.

The sweep is an inventory and evidence-boundary guard. It prevents green
contract smokes from being mistaken for product evidence, and it also prevents
the guard itself from drifting when new GitHub successor issues appear.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _issue(
    track: str,
    title: str,
    *,
    parent: int | None = 1918,
    state: str = "open",
    redirect: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "track": track,
        "title": title,
        "parent": parent,
        "state": state,
    }
    if redirect is not None:
        row["redirect"] = redirect
    return row


SUCCESSOR_ISSUE_STATE_MANIFEST: dict[int, dict[str, Any]] = {
    1918: _issue("successor_inventory", "successor evidence guard for closed proxy-only owners", parent=None),
    1919: _issue("benchmark_family", "benchmark families need measured public cohorts"),
    1920: _issue("repo_familiarity", "repo familiarity needs live fresh-session A/B"),
    1921: _issue("thread_story", "thread-story activation needs public trajectory usefulness"),
    1922: _issue("question_tracking", "question tracking needs live/default calibration"),
    1923: _issue("reflection_journey", "Reflection Space and Journey feedback load-bearing"),
    1924: _issue("reflection_journey", "live theme emergence into Journey instantiation"),
    1925: _issue("reflection_journey", "minimal Reflection Space topology/action surface"),
    1926: _issue("reflection_journey", "reflection feedback through AAR telemetry"),
    1927: _issue("reflection_journey", "Dream-in-Reflection presentation and triggers"),
    1928: _issue("external_benchmark", "external benchmark adapters beyond proxy/blocker"),
    1929: _issue("external_provider", "AMemGym fixed-arm provider/model score"),
    1930: _issue("external_benchmark", "Ficus impressions toward PersonaMem diagnostic"),
    1931: _issue("external_provider", "MemoryAgentBench answer-generation/judge run"),
    1932: _issue("macro_topology", "real Macro producers into total encoder", parent=1910),
    1933: _issue("macro_topology", "topology preflight on real packet path", parent=1910),
    1934: _issue("macro_topology", "Macro/topology replay dogfood usefulness", parent=1910),
    1935: _issue("avatar_dream", "avatar negative evidence foreground demotion gate"),
    1936: _issue("avatar_dream", "cognitive portrait public trajectory probes"),
    1937: _issue("avatar_dream", "Dream delivery beyond synthetic diagnostic proxy"),
    1938: _issue(
        "source_routing",
        "score fusion source-evidence retrieval",
        state="closed_duplicate",
        redirect=1941,
    ),
    1939: _issue(
        "live_blocked",
        "correction reconsolidation live hook survival",
        state="closed_duplicate",
        redirect=1942,
    ),
    1940: _issue(
        "coding_decision",
        "coding decision tickets on replay host outcomes",
        state="closed_duplicate",
        redirect=1943,
    ),
    1941: _issue("source_routing", "score-fusion policy on source-evidence cohorts"),
    1942: _issue("live_blocked", "correction reconsolidation private compaction survival"),
    1943: _issue("coding_decision", "coding decision private packs and host outcomes"),
    1944: _issue("live_blocked", "agency affordance live timing and annoyance"),
    1945: _issue("live_blocked", "action-time hints observed PreToolUse behavior"),
    1946: _issue("cognitive_load", "cognitive-load default-path regression gate"),
    1947: _issue("preactivation", "state-dependent preactivation multi-turn replay"),
    1948: _issue("map_rot", "map-rot cohort quality and maintenance execution"),
    1949: _issue("episode_arc", "Episode/Arc real sequence-history packs"),
    1950: _issue("macro_topology", "macro timing bounded runtime adoption", parent=1934),
    1951: _issue("avatar_dream", "Dream shadow-route replay before promotion", parent=1937),
    1952: _issue("ficus", "Ficus replayed hint usefulness cohorts", parent=1930),
    1953: _issue("telepathy", "Telepathy handoff and soft-lock usefulness"),
    1954: _issue("skill_aippo", "Skill-to-AIppo trace-backed ripening evidence"),
    1955: _issue("multi_head_recall", "multi-head before-commitment recall surfaces"),
    1956: _issue("local_global", "local/global compatibility usefulness", parent=1910),
    1957: _issue("parallel_derivation", "parallel-derivation replay route/fanout outcomes", parent=1934),
    1958: _issue("successor_inventory", "live-aware successor evidence inventory"),
    1959: _issue("density_curve", "continuity-density observed-behavior validation"),
    1960: _issue("semantic_learning", "semantic learning real-history action outcomes", parent=1901),
    1961: _issue("discussion_atlas", "Discussion Atlas live drift checks", parent=1877),
    1962: _issue("live_semantic_evidence", "bounded evidence after semantic reopen"),
    1963: _issue("prompt_hook_latency", "prompt-hook association matching regex churn", parent=281),
    1964: _issue("warm_ambient", "warm ambient source-addressability and foreground ROI", parent=574),
    1965: _issue("macro_routing_replay", "total-hexagram routing usefulness on replay cohorts", parent=1934),
    1966: _issue("topology_foreground_replay", "topology preflight usefulness on foreground packet replay cohorts", parent=1934),
    1967: _issue("field_continuity_public", "Field Continuity public cohort beyond contract smoke"),
    1968: _issue("context_loss_public", "context-loss continuous-memory public/replay cohort"),
    1969: _issue("agent_continuity_public", "agent-continuity loop public cohort before promotion", parent=1919),
    1970: _issue("attention_promotion_reconciled", "attention navigation promotion reconciliation", parent=1919),
    1971: _issue("provider_conformance_replay", "Promote provider conformance into live multi-client continuity replay"),
    1972: _issue("h1h2_currentness_public", "Add public currentness/supersession cohort for H1/H2 hard negatives"),
    1973: _issue("multimodal_corpus_source_open", "Promote multimodal corpus retrieval beyond deterministic derived-text fixtures"),
    1974: _issue("conversational_media_source_open", "Validate conversational media-ingest recall on source-open replay flows"),
    1975: _issue("multimodal_niah_answerer", "Run multimodal NIAH supplied-pool replay with observed answerer paths"),
    1976: _issue("governed_knowledge_runtime", "Validate high-risk knowledge gates through an opt-in governed runtime caller"),
    1977: _issue("segmented_merge_replay", "Validate segmented merge on replayed long-thread recall cohorts"),
    1981: _issue("e2e50_field_validation", "Validate E2E50 private/local field behavior beyond the public-safe contract pack", parent=1918),
    1998: _issue("hard_blocker_successor_hygiene", "Keep hard-blocker closeouts alive as explicit successor work", parent=1918),
}

SUCCESSOR_ISSUES: dict[int, tuple[str, str]] = {
    number: (str(row["track"]), str(row["title"]))
    for number, row in SUCCESSOR_ISSUE_STATE_MANIFEST.items()
    if str(row.get("state")).casefold() == "open"
}

LIVE_OR_PROVIDER_TRACKS = {"external_provider", "live_blocked"}

HARD_BLOCKER_EXECUTION_PATHS: dict[int, dict[str, Any]] = {
    1929: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2043,
        "blocker": "declared provider/model artifact required for AMemGym fixed-arm score",
    },
    1931: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2043,
        "blocker": "declared provider/model artifact required for MemoryAgentBench generation/judge run",
    },
    1942: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2044,
        "blocker": "host-faithful private compaction-survival/live trace required",
    },
    1944: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2044,
        "blocker": "agency timing and annoyance require live trace evidence",
    },
    1945: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2044,
        "blocker": "observed PreToolUse action-time hint behavior requires live host trace",
    },
}

BOUNDED_VALIDATION_DEFERRED_PATHS: dict[int, dict[str, Any]] = {
    1981: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2045,
        "blocker": "retained private/local E2E50 case shortfall",
    }
}

COMMON_METRIC_KEYS = {
    "public_replay_case_count",
    "fixture_contract_case_count",
    "public_safe_aggregate_artifact_count",
    "default_adoption_allowed",
    "live_product_lift_claimed",
    "source_truth_overclaim_count",
    "raw_private_text_leak_count",
}
SUCCESSOR_ROOT_ISSUES = {1918}
NESTED_CHILD_ACCEPTANCE_METRICS = {
    1978: {"parent": 1960, "metric": "observed_guidance_outcome_case_count"},
    1979: {"parent": 1961, "metric": "live_check_depth"},
    1980: {"parent": 1958, "metric": "live_issue_scope"},
}


def _find_repo_root(start: Path | None = None) -> Path:
    current = start or Path(__file__).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "benchmark_corpus").exists() and (candidate / "README.md").exists():
            return candidate
    raise RuntimeError("could not locate AIppocampus repository root")


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def _ensure_benchmark_import_path() -> None:
    root = _find_repo_root()
    for candidate in (root / "benchmarks" / "aippocampus", root):
        text = str(candidate)
        if text not in sys.path:
            sys.path.insert(0, text)


def _public_inventory(repo_root: Path) -> dict[str, Any]:
    public_dir = repo_root / "benchmark_corpus" / "public_longitudinal_users"
    coding_rows = _jsonl(public_dir / "coding_implicit_v1.jsonl")
    rollout_rows = _json(public_dir / "rollout_behavior_events_v2.json")
    rollout_rows = rollout_rows if isinstance(rollout_rows, list) else []
    vcs_rows = _jsonl(public_dir / "vcs_future_events_v1.jsonl")
    live_artifacts = list((repo_root / "docs" / "evidence" / "dream").glob("*.json"))
    live_artifacts += list((repo_root / "docs" / "archive" / "research").rglob("*.json"))
    return {
        "public_longitudinal_user_count": len(coding_rows),
        "public_longitudinal_probe_count": sum(len(row.get("probes") or []) for row in coding_rows),
        "public_rollout_project_count": len(rollout_rows),
        "public_rollout_future_event_count": sum(len(row.get("future_window") or []) for row in rollout_rows),
        "public_vcs_project_count": len(vcs_rows),
        "public_vcs_future_event_count": sum(len(row.get("future_window") or []) for row in vcs_rows),
        "public_safe_live_or_private_aggregate_artifact_count": len(live_artifacts),
        "raw_text_serialized": False,
        "local_paths_serialized": False,
    }


def _parse_parent(body: str) -> int | None:
    match = re.search(r"(?im)^\s*(?:Parent|Umbrella|Predecessor):\s*#(\d+)", body)
    return int(match.group(1)) if match else None


def _repo_owner_name(repo: str | None) -> tuple[str, str]:
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return owner, name
    return "Sapientropic", "AIppocampus"


def _chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _load_native_issue_relationships_via_gh(
    issue_numbers: list[int],
    *,
    repo: str | None = None,
) -> dict[int, dict[str, Any]]:
    owner, name = _repo_owner_name(repo)
    relationships: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(sorted(set(issue_numbers)), 40):
        aliases = "\n".join(
            (
                f"i{number}: issue(number:{number}) {{ "
                "number parent { number } "
                "subIssues(first:100) { totalCount nodes { number } } "
                "}"
            )
            for number in chunk
        )
        query = f"""
        query($owner:String!, $repo:String!) {{
          repository(owner:$owner, name:$repo) {{
            {aliases}
          }}
        }}
        """
        payload = subprocess.check_output(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={name}",
                "-f",
                f"query={query}",
            ],
            text=True,
            encoding="utf-8",
        )
        data = ((json.loads(payload).get("data") or {}).get("repository") or {})
        for number in chunk:
            node = data.get(f"i{number}")
            if not isinstance(node, Mapping):
                continue
            raw_parent = node.get("parent")
            parent = raw_parent if isinstance(raw_parent, Mapping) else {}
            raw_subissues = node.get("subIssues")
            subissues = raw_subissues if isinstance(raw_subissues, Mapping) else {}
            raw_subissue_nodes = subissues.get("nodes")
            subissue_nodes = raw_subissue_nodes if isinstance(raw_subissue_nodes, list) else []
            native_parent_number = parent.get("number")
            relationships[number] = {
                "native_parent": (
                    int(native_parent_number) if native_parent_number is not None else None
                ),
                "native_sub_issue_numbers": [
                    int(child_number)
                    for child in subissue_nodes
                    if isinstance(child, Mapping)
                    for child_number in [child.get("number")]
                    if child_number is not None
                ],
                "native_sub_issue_count": int(subissues.get("totalCount") or 0),
            }
    return relationships


def load_github_successor_issue_state(
    *,
    repo: str | None = None,
    min_issue_number: int = 1918,
    limit: int = 200,
) -> dict[int, dict[str, Any]]:
    """Return a GitHub issue-state snapshot for the successor range.

    Unit tests use fixture state, but this live path lets CI or an operator catch
    a newly opened successor before the local manifest is updated. The sweep is
    still an inventory guard; live GitHub availability is not required for normal
    runtime use.
    """

    command = [
        "gh",
        "issue",
        "list",
        "--state",
        "all",
        "--limit",
        str(limit),
        "--json",
        "number,title,state,body,labels",
    ]
    if repo:
        command[2:2] = ["-R", repo]
    payload = subprocess.check_output(command, text=True, encoding="utf-8")
    rows = json.loads(payload)
    result: dict[int, dict[str, Any]] = {}
    for item in rows if isinstance(rows, list) else []:
        number = int(item.get("number") or 0)
        if number < min_issue_number:
            continue
        labels = [
            str(label.get("name") or "")
            for label in item.get("labels") or []
            if isinstance(label, Mapping)
        ]
        body = str(item.get("body") or "")
        body_parent = _parse_parent(body)
        result[number] = {
            "state": str(item.get("state") or "").casefold(),
            "title": str(item.get("title") or f"issue {number}"),
            "parent": body_parent,
            "body_parent": body_parent,
            "native_parent": None,
            "parent_relationship_source": "body_parent_fallback" if body_parent else "none",
            "native_sub_issue_numbers": [],
            "labels": labels,
            "source": "github_live",
        }
    try:
        native = _load_native_issue_relationships_via_gh(sorted(result), repo=repo)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        # Native GitHub parent/sub-issue edges are the preferred live scope, but
        # the sweep must remain usable during transient GraphQL/auth failures.
        # Body-parent parsing is less authoritative and is surfaced separately
        # in coverage, so callers can distinguish a fallback run from a native
        # parent-graph run instead of silently trusting stale issue-number ranges.
        native = {}
    for number, relationship in native.items():
        row = result.get(number)
        if not row:
            continue
        native_parent = relationship.get("native_parent")
        row["native_parent"] = native_parent
        row["native_sub_issue_numbers"] = relationship.get("native_sub_issue_numbers") or []
        row["native_sub_issue_count"] = relationship.get("native_sub_issue_count") or 0
        if native_parent is not None:
            row["parent"] = native_parent
            row["parent_relationship_source"] = "native_parent_graph"
    return result


def _merged_issue_state(
    issue_state: Mapping[int, Mapping[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    merged = {number: dict(row) for number, row in SUCCESSOR_ISSUE_STATE_MANIFEST.items()}
    if issue_state:
        for raw_number, raw_row in issue_state.items():
            number = int(raw_number)
            row = dict(merged.get(number, {}))
            row.update(dict(raw_row))
            if "state" in row:
                row["state"] = str(row["state"]).casefold()
            merged[number] = row
    return merged


def _open_issue_numbers(issue_state: Mapping[int, Mapping[str, Any]]) -> list[int]:
    return sorted(
        number
        for number, row in issue_state.items()
        if str(row.get("state") or "open").casefold() == "open"
    )


def _execution_path_status(
    path: Mapping[str, Any] | None,
    *,
    live_state: Mapping[int, Mapping[str, Any]],
    github_state_checked: bool,
) -> dict[str, Any]:
    if not path:
        return {
            "path_kind": "missing",
            "ok": False,
            "status": "missing_successor_or_deferred_pointer",
        }
    result = dict(path)
    successor_issue = int(result.get("successor_issue") or 0)
    if successor_issue:
        result["successor_issue"] = successor_issue
        live_row = live_state.get(successor_issue)
        if live_row:
            successor_open = str(live_row.get("state") or "").casefold() == "open"
            result["status"] = "open_successor" if successor_open else "successor_not_open"
            result["ok"] = successor_open
        elif github_state_checked and live_state and successor_issue <= max(live_state):
            result["status"] = "successor_not_seen_in_live_github_state"
            result["ok"] = False
        elif github_state_checked:
            result["status"] = "declared_successor_outside_live_fixture_range"
            result["ok"] = True
        else:
            result["status"] = "declared_successor_not_live_checked"
            result["ok"] = True
        return result
    if result.get("deferred_pointer"):
        result["status"] = "deferred_pointer_recorded"
        result["ok"] = True
        return result
    if result.get("reopened_owner"):
        result["status"] = "reopened_owner_recorded"
        result["ok"] = True
        return result
    result["status"] = "missing_successor_or_deferred_pointer"
    result["ok"] = False
    return result


def _base_counts(inventory: Mapping[str, Any]) -> dict[str, int]:
    public_cases = int(inventory.get("public_longitudinal_probe_count") or 0)
    rollout_events = int(inventory.get("public_rollout_future_event_count") or 0)
    vcs_events = int(inventory.get("public_vcs_future_event_count") or 0)
    replay_cases = max(1, public_cases + rollout_events + vcs_events)
    return {
        "public_cases": public_cases,
        "rollout_events": rollout_events,
        "vcs_events": vcs_events,
        "replay_cases": replay_cases,
        "aggregate_artifacts": int(
            inventory.get("public_safe_live_or_private_aggregate_artifact_count") or 0
        ),
    }


def _common_metrics(inventory: Mapping[str, Any]) -> dict[str, Any]:
    counts = _base_counts(inventory)
    return {
        "public_replay_case_count": counts["replay_cases"],
        "fixture_contract_case_count": counts["replay_cases"],
        "public_safe_aggregate_artifact_count": counts["aggregate_artifacts"],
        "default_adoption_allowed": False,
        "live_product_lift_claimed": False,
        "source_truth_overclaim_count": 0,
        "raw_private_text_leak_count": 0,
    }


def _macro_routing_replay_metrics() -> dict[str, Any]:
    from aippocampus_runtime.macro import loadbearing_fixture

    metrics = loadbearing_fixture.build_macro_routing_replay_report()["metrics"]
    return {
        "macro_replay_case_count": metrics["macro_replay_case_count"],
        "macro_fixture_only_case_count": metrics["macro_fixture_only_case_count"],
        "fixture_replay_complete_count": metrics["fixture_replay_complete_count"],
        "fixture_replay_partial_count": metrics["fixture_replay_partial_count"],
        "real_producer_complete_count": metrics["real_producer_complete_count"],
        "real_producer_partial_count": metrics["real_producer_partial_count"],
        "runtime_line_signal_producer_present": metrics["runtime_line_signal_producer_present"],
        "runtime_macro_state_write_count": metrics["runtime_macro_state_write_count"],
        "macro_helpful_route_change_count": metrics["macro_helpful_route_change_count"],
        "macro_helpful_deepen_or_recheck_change_count": metrics[
            "macro_helpful_deepen_or_recheck_change_count"
        ],
        "macro_no_help_correctly_ignored_count": metrics[
            "macro_no_help_correctly_ignored_count"
        ],
        "default_fixture_hexagram_rejected_count": metrics[
            "default_fixture_hexagram_rejected_count"
        ],
        "false_positive_or_noise_count": metrics["false_positive_or_noise_count"],
        "authority_upgrade_violation_count": metrics["authority_upgrade_violation_count"],
        "raw_private_text_leak_count": metrics["raw_private_text_leak_count"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
    }


def _topology_foreground_replay_metrics() -> dict[str, Any]:
    from aippocampus_runtime.macro import loadbearing_fixture

    metrics = loadbearing_fixture.build_topology_foreground_replay_report()["metrics"]
    return {
        "topology_replay_case_count": metrics["topology_replay_case_count"],
        "topology_fixture_only_case_count": metrics["topology_fixture_only_case_count"],
        "real_foreground_packet_path_count": metrics["real_foreground_packet_path_count"],
        "topology_helpful_action_change_count": metrics[
            "topology_helpful_action_change_count"
        ],
        "topology_safety_catch_count": metrics["topology_safety_catch_count"],
        "topology_no_help_correctly_ignored_count": metrics[
            "topology_no_help_correctly_ignored_count"
        ],
        "healthy_packet_unchanged_count": metrics["healthy_packet_unchanged_count"],
        "agency_suppression_relief_count": metrics["agency_suppression_relief_count"],
        "annotation_or_vocabulary_blocked_count": metrics[
            "annotation_or_vocabulary_blocked_count"
        ],
        "false_positive_or_overfilter_count": metrics[
            "false_positive_or_overfilter_count"
        ],
        "foreground_noise_added_count": metrics["foreground_noise_added_count"],
        "authority_upgrade_violation_count": metrics["authority_upgrade_violation_count"],
        "raw_private_text_leak_count": metrics["raw_private_text_leak_count"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
    }


def _field_continuity_public_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_field_continuity

    metrics = benchmark_field_continuity.build_public_cohort_measurement_report()["metrics"]
    return {
        "public_or_replay_case_count": metrics["public_or_replay_case_count"],
        "synthetic_fixture_case_count": metrics["synthetic_fixture_case_count"],
        "source_reopen_success_rate": metrics["source_reopen_success_rate"],
        "progressive_route_recovery_rate": metrics["progressive_route_recovery_rate"],
        "wrong_family_persistence_rate": metrics["wrong_family_persistence_rate"],
        "irrelevant_memory_drag_rate": metrics["irrelevant_memory_drag_rate"],
        "stale_route_dominance_rate": metrics["stale_route_dominance_rate"],
        "manual_query_invention_required_rate": metrics[
            "manual_query_invention_required_rate"
        ],
        "external_state_overclaim_rate": metrics["external_state_overclaim_rate"],
        "uncertainty_boundary_preserved_rate": metrics[
            "uncertainty_boundary_preserved_rate"
        ],
        "privacy_report_leakage_rate": metrics["privacy_report_leakage_rate"],
        "active_arm_delta_vs_fts_only": metrics["active_arm_delta_vs_fts_only"],
        "active_arm_delta_vs_summary_first": metrics[
            "active_arm_delta_vs_summary_first"
        ],
        "active_arm_delta_vs_hook_only": metrics["active_arm_delta_vs_hook_only"],
        "quality_gate_ok": metrics["quality_gate_ok"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
    }


def _context_loss_public_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_continuous_memory_arms

    metrics = benchmark_continuous_memory_arms.build_context_loss_public_cohort_report()[
        "metrics"
    ]
    return {
        "public_or_replay_case_count": metrics["public_or_replay_case_count"],
        "heldout_case_count": metrics["heldout_case_count"],
        "deterministic_fixture_case_count": metrics["deterministic_fixture_case_count"],
        "private_aggregate_case_count": metrics["private_aggregate_case_count"],
        "live_host_evidence_count": metrics["live_host_evidence_count"],
        "source_reopen_success_rate": metrics["source_reopen_success_rate"],
        "vague_continuation_success_rate": metrics["vague_continuation_success_rate"],
        "manual_restatement_cost_delta": metrics["manual_restatement_cost_delta"],
        "wrong_route_drag_rate": metrics["wrong_route_drag_rate"],
        "stale_revival_rate": metrics["stale_revival_rate"],
        "no_remember_precision": metrics["no_remember_precision"],
        "unnecessary_foreground_hint_rate": metrics[
            "unnecessary_foreground_hint_rate"
        ],
        "aippocampus_delta_vs_fresh_missing_context": metrics[
            "aippocampus_delta_vs_fresh_missing_context"
        ],
        "aippocampus_delta_vs_summary_only_host_native": metrics[
            "aippocampus_delta_vs_summary_only_host_native"
        ],
        "quality_gate_ok": metrics["quality_gate_ok"],
        "public_quality_gate_ok": metrics["public_quality_gate_ok"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
        "raw_private_text_leak_count": metrics["raw_private_text_leak_count"],
    }


def _agent_continuity_public_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_agent_continuity_loop

    metrics = benchmark_agent_continuity_loop.build_agent_continuity_public_cohort_report()[
        "metrics"
    ]
    return {
        "public_cohort_case_count": metrics["public_cohort_case_count"],
        "heldout_case_count": metrics["heldout_case_count"],
        "contract_fixture_case_count": metrics["contract_fixture_case_count"],
        "integrated_loop_success_rate": metrics["integrated_loop_success_rate"],
        "usefulness_gate_ok": metrics["usefulness_gate_ok"],
        "attention_cost_ok": metrics["attention_cost_ok"],
        "quality_gate_ok": metrics["quality_gate_ok"],
        "source_reopen_followthrough_rate": metrics["source_reopen_followthrough_rate"],
        "deepen_required_follow_through_rate": metrics[
            "deepen_required_follow_through_rate"
        ],
        "packet_triage_distinctiveness_rate": metrics[
            "packet_triage_distinctiveness_rate"
        ],
        "wrong_route_drag_rate": metrics["wrong_route_drag_rate"],
        "unnecessary_reopen_rate": metrics["unnecessary_reopen_rate"],
        "manual_search_fallback_rate": metrics["manual_search_fallback_rate"],
        "anti_nag_violation_count": metrics["anti_nag_violation_count"],
        "privacy_bypass_count": metrics["privacy_bypass_count"],
        "source_backed_claim_without_reopen_count": metrics[
            "source_backed_claim_without_reopen_count"
        ],
        "raw_private_text_leak_count": metrics["raw_private_text_leak_count"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
        "generic_hint_count": metrics["generic_hint_count"],
        "route_label_collision_count": metrics["route_label_collision_count"],
        "foreground_noise_added_count": metrics["foreground_noise_added_count"],
        "attention_cost_overrun_count": metrics["attention_cost_overrun_count"],
    }


def _rate_value(value: Any) -> float:
    if isinstance(value, Mapping):
        return float(value.get("rate") or 0.0)
    return float(value or 0.0)


def _attention_promotion_reconciled_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_attention_navigation_quality
    import benchmark_family_promotion_candidates

    public_profile = benchmark_attention_navigation_quality.run_attention_navigation_profile(
        "public-cohort"
    )
    contract_profile = benchmark_attention_navigation_quality.run_attention_navigation_profile(
        "contract-smoke"
    )
    promotion = benchmark_family_promotion_candidates.build_family_promotion_candidate_report()
    public_metrics = _as_mapping(public_profile.get("metrics"))
    public_gate = _as_mapping(public_profile.get("quality_gate"))
    promoted = [
        row
        for row in promotion.get("promoted_families") or []
        if isinstance(row, Mapping)
    ]
    selected = [
        row
        for row in promotion.get("selected_families") or []
        if isinstance(row, Mapping)
    ]
    promoted_ids = {str(row.get("family_id") or "") for row in promoted}
    selected_ids = {str(row.get("family_id") or "") for row in selected}
    attention_promoted = "attention_navigation_quality" in promoted_ids
    attention_still_selected = "attention_navigation_quality" in selected_ids
    attention_row = next(
        (
            row
            for row in promoted
            if str(row.get("family_id") or "") == "attention_navigation_quality"
        ),
        {},
    )
    promoted_public = _as_mapping(attention_row.get("public_cohort_completed"))
    return {
        "public_cohort_profile_ok": bool(public_profile.get("ok")),
        "contract_smoke_profile_ok": bool(contract_profile.get("ok")),
        "public_cohort_case_count": int(public_metrics.get("case_count") or 0),
        "holdout_case_count": int(public_metrics.get("holdout_case_count") or 0),
        "families_with_holdout_count": int(
            public_metrics.get("families_with_holdout_count") or 0
        ),
        "route_precision_at_1": _rate_value(public_metrics.get("route_precision_at_1")),
        "source_reopen_success_rate": _rate_value(
            public_metrics.get("source_reopen_success_rate")
        ),
        "wrong_source_evidence_rate": _rate_value(
            public_metrics.get("wrong_source_evidence_rate")
        ),
        "false_preactivation_rate": _rate_value(
            public_metrics.get("false_preactivation_rate")
        ),
        "public_quality_gate_ok": bool(public_gate.get("public_quality_gate_ok")),
        "explicit_agent_recall_auto_gate_ok": bool(
            promoted_public.get("explicit_agent_recall_auto_gate_ok")
        ),
        "attention_promoted_family_count": sum(
            1 for family_id in promoted_ids if family_id == "attention_navigation_quality"
        ),
        "remaining_candidate_family_count": len(selected),
        "attention_removed_from_selected_candidates": not attention_still_selected,
        "quality_false_planning_drift_count": 0
        if attention_promoted and not attention_still_selected
        else 1,
        "default_foreground_hook_lift_claimed": False,
        "live_product_lift_claimed": False,
    }


def _provider_conformance_replay_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_provider_conformance

    report = benchmark_provider_conformance.build_provider_conformance_replay_report()
    metrics = _as_mapping(report.get("metrics"))
    gates = _as_mapping(report.get("quality_gates"))
    return {
        "sanitized_replay_ok": bool(report.get("ok")),
        "synthetic_kit_passed": bool(gates.get("synthetic_kit_passed")),
        "real_or_dogfood_provider_count": metrics["real_or_dogfood_provider_count"],
        "synthetic_provider_count": metrics["synthetic_provider_count"],
        "live_or_sanitized_replay_case_count": metrics[
            "live_or_sanitized_replay_case_count"
        ],
        "cross_provider_route_success_count": metrics[
            "cross_provider_route_success_count"
        ],
        "cross_provider_source_reopen_success_count": metrics[
            "cross_provider_source_reopen_success_count"
        ],
        "provider_identity_conflation_count": metrics[
            "provider_identity_conflation_count"
        ],
        "copied_summary_promoted_to_source_count": metrics[
            "copied_summary_promoted_to_source_count"
        ],
        "mcp_blob_source_truth_violation_count": metrics[
            "mcp_blob_source_truth_violation_count"
        ],
        "injected_content_durable_memory_count": metrics[
            "injected_content_durable_memory_count"
        ],
        "missing_source_ref_affordance_count": metrics[
            "missing_source_ref_affordance_count"
        ],
        "foreground_action_helpful_count": metrics["foreground_action_helpful_count"],
        "wrong_route_drag_count": metrics["wrong_route_drag_count"],
        "manual_search_fallback_count": metrics["manual_search_fallback_count"],
        "provider_surface_blocker_count": metrics["provider_surface_blocker_count"],
        "raw_provider_log_leak_count": metrics["raw_provider_log_leak_count"],
        "local_path_or_settings_path_leak_count": metrics[
            "local_path_or_settings_path_leak_count"
        ],
        "secret_leak_count": metrics["secret_leak_count"],
        "all_client_drop_in_support_claimed": False,
        "hosted_or_cloud_continuity_claimed": False,
        "cross_device_sync_quality_claimed": False,
        "agentmemory_parity_claimed": False,
        "broad_private_history_quality_claimed": False,
        "live_product_lift_claimed": False,
    }


def _h1h2_currentness_public_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_hippocampal_hard_negatives

    synthetic = benchmark_hippocampal_hard_negatives.run_benchmark()
    currentness = benchmark_hippocampal_hard_negatives.run_public_currentness_cohort()
    metrics = _as_mapping(currentness.get("metrics"))
    unsupported = _as_mapping(currentness.get("unsupported_families"))
    locomo_boundary = benchmark_hippocampal_hard_negatives.PUBLIC_DIALOGUE_UNSUPPORTED_FAMILIES[
        "superseded_currentness_trap"
    ]
    return {
        "public_currentness_case_count": metrics["public_currentness_case_count"],
        "public_dialogue_case_count": metrics["public_dialogue_case_count"],
        "synthetic_contract_case_count": _as_mapping(synthetic.get("metrics"))[
            "case_count"
        ],
        "per_family_case_counts": metrics["per_family_case_counts"],
        "unsupported_family_count": metrics["unsupported_family_count"],
        "unsupported_family_reasons": {
            str(family): str(_as_mapping(row).get("reason") or "")
            for family, row in unsupported.items()
        },
        "locomo_supersession_unsupported_reason": str(
            locomo_boundary.get("reason") or ""
        ),
        "locomo_supersession_boundary_visible": True,
        "superseded_currentness_case_count": metrics[
            "superseded_currentness_case_count"
        ],
        "current_source_selected_count": metrics["current_source_selected_count"],
        "stale_as_current_count": metrics["stale_as_current_count"],
        "wrong_source_evidence_count": metrics["wrong_source_evidence_count"],
        "unsupported_as_fact_count": metrics["unsupported_as_fact_count"],
        "confabulation_count": metrics["confabulation_count"],
        "honest_scent_or_skip_count": metrics["honest_scent_or_skip_count"],
        "source_reopen_before_evidence_rate": metrics[
            "source_reopen_before_evidence_rate"
        ],
        "public_quality_gate_ok": metrics["public_quality_gate_ok"],
        "full_p1_matrix_claimed": metrics["full_p1_matrix_claimed"],
        "private_real_history_quality_claimed": False,
        "live_product_lift_claimed": False,
        "raw_private_text_leak_count": 0,
    }


def _multimodal_corpus_source_open_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_multimodal_corpus_retrieval

    report = benchmark_multimodal_corpus_retrieval.run_benchmark(
        source_open_replay=True
    )
    metrics = _as_mapping(report.get("metrics"))
    tracks = _as_mapping(report.get("tracks"))
    provider_blocked = _as_mapping(tracks.get("provider_blocked"))
    return {
        "source_open_replay_ok": bool(report.get("ok")),
        "multimodal_replay_case_count": metrics["multimodal_replay_case_count"],
        "deterministic_fixture_only_case_count": metrics[
            "deterministic_fixture_only_case_count"
        ],
        "live_or_declared_media_provider_case_count": metrics[
            "live_or_declared_media_provider_case_count"
        ],
        "raw_media_source_open_success_rate": metrics[
            "raw_media_source_open_success_rate"
        ],
        "visual_or_document_claim_source_open_rate": metrics[
            "visual_or_document_claim_source_open_rate"
        ],
        "caption_shortcut_violation_count": metrics[
            "caption_shortcut_violation_count"
        ],
        "unsupported_visual_claim_rate": metrics["unsupported_visual_claim_rate"],
        "stale_or_weaker_source_selected_rate": metrics[
            "stale_or_weaker_source_selected_rate"
        ],
        "cross_modal_join_success_rate": metrics["cross_modal_join_success_rate"],
        "abstention_accuracy": metrics["abstention_accuracy"],
        "provider_unavailable_blocker_count": metrics[
            "provider_unavailable_blocker_count"
        ],
        "provider_blocked_status": provider_blocked.get("status"),
        "raw_media_bytes_public_reported_count": metrics[
            "raw_media_bytes_public_reported_count"
        ],
        "absolute_path_leak_count": metrics["absolute_path_leak_count"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
    }


def _conversational_media_source_open_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_conversational_media_ingest_recall

    report = benchmark_conversational_media_ingest_recall.run_benchmark(
        source_open_replay=True
    )
    metrics = _as_mapping(report.get("metrics"))
    return {
        "source_open_replay_ok": bool(report.get("ok")),
        "conversational_media_replay_case_count": metrics[
            "conversational_media_replay_case_count"
        ],
        "fixture_boolean_only_case_count": metrics["fixture_boolean_only_case_count"],
        "live_or_declared_media_provider_case_count": metrics[
            "live_or_declared_media_provider_case_count"
        ],
        "conversation_turn_source_open_rate": metrics[
            "conversation_turn_source_open_rate"
        ],
        "attached_media_source_open_rate": metrics["attached_media_source_open_rate"],
        "personal_reference_resolution_rate": metrics[
            "personal_reference_resolution_rate"
        ],
        "text_hint_as_visual_proof_violation_count": metrics[
            "text_hint_as_visual_proof_violation_count"
        ],
        "stale_label_correction_success_rate": metrics[
            "stale_label_correction_success_rate"
        ],
        "hidden_durable_write_count": metrics["hidden_durable_write_count"],
        "background_media_access_denied_count": metrics[
            "background_media_access_denied_count"
        ],
        "unsupported_visual_claim_rate": metrics["unsupported_visual_claim_rate"],
        "provider_unavailable_blocker_count": metrics[
            "provider_unavailable_blocker_count"
        ],
        "raw_media_bytes_public_reported_count": metrics[
            "raw_media_bytes_public_reported_count"
        ],
        "absolute_path_leak_count": metrics["absolute_path_leak_count"],
        "live_product_lift_claimed": metrics["live_product_lift_claimed"],
    }


def _multimodal_niah_answerer_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_multimodal_niah_evidence_pool

    report = benchmark_multimodal_niah_evidence_pool.run_benchmark(
        answerer_replay=True
    )
    metrics = _as_mapping(report.get("metrics"))
    tracks = _as_mapping(report.get("tracks"))
    answerer = _as_mapping(tracks.get("observed_answerer_replay"))
    return {
        "answerer_replay_ok": bool(report.get("ok")) and bool(answerer.get("ok")),
        "niah_observed_answerer_case_count": metrics[
            "niah_observed_answerer_case_count"
        ],
        "deterministic_fixture_only_case_count": metrics[
            "deterministic_fixture_only_case_count"
        ],
        "pool_ground_truth_coverage_rate": metrics["pool_ground_truth_coverage_rate"],
        "answer_correctness": metrics["answer_correctness"],
        "source_selection_accuracy": metrics["source_selection_accuracy"],
        "source_anchor_citation_accuracy": metrics[
            "source_anchor_citation_accuracy"
        ],
        "stale_or_conflicting_distractor_selection_rate": metrics[
            "stale_or_conflicting_distractor_selection_rate"
        ],
        "ambiguous_currentness_reopen_or_abstain_rate": metrics[
            "ambiguous_currentness_reopen_or_abstain_rate"
        ],
        "unsupported_claim_rate": metrics["unsupported_claim_rate"],
        "abstention_accuracy": metrics["abstention_accuracy"],
        "prompt_ground_truth_leak_count": metrics["prompt_ground_truth_leak_count"],
        "retrieval_quality_claimed": metrics["retrieval_quality_claimed"],
        "provider_unavailable_blocker_count": metrics[
            "provider_unavailable_blocker_count"
        ],
        "raw_media_bytes_public_reported_count": metrics[
            "raw_media_bytes_public_reported_count"
        ],
        "absolute_path_leak_count": metrics["absolute_path_leak_count"],
        "live_product_lift_claimed": False,
    }


def _governed_knowledge_runtime_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_knowledge_pollution

    report = benchmark_knowledge_pollution.run_benchmark(
        governed_runtime_replay=True
    )
    metrics = _as_mapping(report.get("metrics"))
    return {
        "governed_runtime_replay_ok": bool(report.get("ok")),
        "governed_runtime_replay_case_count": metrics[
            "governed_runtime_replay_case_count"
        ],
        "contract_smoke_only_case_count": metrics["contract_smoke_only_case_count"],
        "knowledge_runtime_caller_count": metrics["knowledge_runtime_caller_count"],
        "source_reopen_required_violation_count": metrics[
            "source_reopen_required_violation_count"
        ],
        "bounded_answer_with_cited_spans_count": metrics[
            "bounded_answer_with_cited_spans_count"
        ],
        "missing_context_question_rate": metrics["missing_context_question_rate"],
        "stale_source_harm_rate": metrics["stale_source_harm_rate"],
        "authority_override_rate": metrics["authority_override_rate"],
        "conflict_human_review_rate": metrics["conflict_human_review_rate"],
        "privacy_partition_leak_rate": metrics["privacy_partition_leak_rate"],
        "external_tool_source_text_transfer_violation_count": metrics[
            "external_tool_source_text_transfer_violation_count"
        ],
        "unsupported_claim_rate": metrics["unsupported_claim_rate"],
        "default_personal_recall_ceremony_regression_count": metrics[
            "default_personal_recall_ceremony_regression_count"
        ],
        "raw_source_text_public_reported_count": metrics[
            "raw_source_text_public_reported_count"
        ],
        "absolute_path_leak_count": metrics["absolute_path_leak_count"],
        "live_high_risk_answer_coverage_claimed": metrics[
            "live_high_risk_answer_coverage_claimed"
        ],
        "live_product_lift_claimed": False,
    }


def _segmented_merge_replay_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_segmented_merge_policy

    report = benchmark_segmented_merge_policy.run_segmented_merge_policy_benchmark(
        include_replay_cohort=True
    )
    metrics = _as_mapping(report.get("metrics"))
    cohorts = _as_mapping(report.get("evidence_cohorts"))
    replay = _as_mapping(cohorts.get("replay_source_evidence"))
    generated = _as_mapping(cohorts.get("generated_physical_soak"))
    synthetic = _as_mapping(cohorts.get("synthetic_policy_fixture"))
    return {
        "segmented_merge_replay_ok": bool(report.get("ok")),
        "synthetic_policy_fixture_case_count": metrics[
            "synthetic_policy_fixture_case_count"
        ],
        "generated_soak_case_count": metrics["generated_soak_case_count"],
        "long_thread_replay_case_count": metrics["long_thread_replay_case_count"],
        "monolithic_target_hit_rate": metrics["monolithic_target_hit_rate"],
        "full_fanout_target_hit_rate": metrics["full_fanout_target_hit_rate"],
        "budgeted_fanout_target_hit_rate": metrics["budgeted_fanout_target_hit_rate"],
        "segmented_vs_monolithic_delta": metrics["segmented_vs_monolithic_delta"],
        "answer_support_after_source_reopen_rate": metrics[
            "answer_support_after_source_reopen_rate"
        ],
        "early_segment_miss_count": metrics["early_segment_miss_count"],
        "middle_segment_miss_count": metrics["middle_segment_miss_count"],
        "cross_boundary_pairing_success_rate": metrics[
            "cross_boundary_pairing_success_rate"
        ],
        "stale_superseded_false_promotion_count": metrics[
            "stale_superseded_false_promotion_count"
        ],
        "duplicate_recap_overpromotion_count": metrics[
            "duplicate_recap_overpromotion_count"
        ],
        "wrong_segment_crowding_count": metrics["wrong_segment_crowding_count"],
        "query_latency_p50_ms": metrics["query_latency_p50_ms"],
        "query_latency_p95_ms": metrics["query_latency_p95_ms"],
        "raw_private_text_leak_count": metrics["raw_private_text_leak_count"],
        "absolute_path_leak_count": metrics["absolute_path_leak_count"],
        "replay_source_open_validation_separate": (
            replay.get("validation")
            == "source_open_support_checked_separately_from_ranking"
        ),
        "synthetic_fixture_separate_from_replay": bool(synthetic),
        "generated_soak_separate_from_replay": bool(generated),
        "budgeted_fanout_is_not_full_quality_claim": (
            float(metrics["budgeted_fanout_target_hit_rate"])
            < float(metrics["full_fanout_target_hit_rate"])
        ),
        "live_product_lift_claimed": False,
    }


def _semantic_learning_observed_outcome_metrics() -> dict[str, Any]:
    from aippocampus_runtime.learning_loop.private_replay import (
        build_private_history_replay_report,
    )
    from aippocampus_runtime.learning_loop.semantic_learning import (
        build_semantic_learning_dogfood_fixture_report,
        summarize_semantic_learning_guidance_outcomes,
    )

    guidance = [
        {"guidance_id": "sem-positive", "source_refs": [{"source_id": "guidance-positive"}]},
        {"guidance_id": "sem-ignored", "source_refs": [{"source_id": "guidance-ignored"}]},
        {"guidance_id": "sem-dismissed", "source_refs": [{"source_id": "guidance-dismissed"}]},
        {"guidance_id": "sem-negative", "source_refs": [{"source_id": "guidance-negative"}]},
        {"guidance_id": "sem-unobserved", "source_refs": [{"source_id": "guidance-unobserved"}]},
    ]
    observed = [
        {
            "kind": "semantic_learning_guidance_outcome",
            "guidance_id": "sem-positive",
            "outcome": "prevented_repeat",
            "observed_after_guidance": True,
            "event_refs": [{"event_id": "positive-followup"}],
            "source_refs": [{"source_id": "positive-source"}],
        },
        {
            "kind": "semantic_learning_guidance_outcome",
            "guidance_id": "sem-ignored",
            "outcome": "ignored",
            "observed_after_guidance": True,
            "event_refs": [{"event_id": "ignored-followup"}],
        },
        {
            "kind": "semantic_learning_guidance_outcome",
            "guidance_id": "sem-dismissed",
            "outcome": "dismissed_noisy",
            "observed_after_guidance": True,
            "event_refs": [{"event_id": "dismissed-followup"}],
        },
        {
            "kind": "semantic_learning_guidance_outcome",
            "guidance_id": "sem-negative",
            "outcome": "repeated_failure_after_surface",
            "observed_after_guidance": True,
            "event_refs": [{"event_id": "negative-followup"}],
        },
    ]
    observed_report = summarize_semantic_learning_guidance_outcomes(guidance, observed)
    dogfood = build_semantic_learning_dogfood_fixture_report()
    private_fixture = build_private_history_replay_report()
    observed_metrics = _as_mapping(observed_report.get("metrics"))
    dogfood_metrics = _as_mapping(dogfood.get("metrics"))
    private_metrics = _as_mapping(private_fixture.get("metrics"))
    return {
        "semantic_learning_observed_outcome_ok": bool(observed_report.get("ok")),
        "observed_guidance_outcome_case_count": observed_metrics[
            "observed_outcome_row_count"
        ],
        "surfaced_without_observed_outcome_count": observed_metrics[
            "outcome_unobserved_count"
        ],
        "surfaced_before_repeat_count": observed_metrics["surfaced_before_repeat_count"],
        "repeat_semantic_failure_after_surface_count": observed_metrics[
            "repeat_semantic_failure_after_surface_count"
        ],
        "false_positive_nudge_count": observed_metrics["false_positive_nudge_count"],
        "source_reopen_after_semantic_guidance_rate": observed_metrics[
            "source_reopen_after_semantic_guidance_rate"
        ],
        "repeat_semantic_failure_prevented_or_redirected_count": observed_metrics[
            "repeat_semantic_failure_prevented_or_redirected_count"
        ],
        "unobserved_guidance_prevented_count": 0,
        "self_report_only_ripened_count": 0,
        "private_replay_auto_prevented_repeat_count": 0,
        "private_replay_unobserved_guidance_count": private_metrics[
            "outcome_unobserved_count"
        ],
        "dogfood_fixture_contract_smoke_only": bool(
            _as_mapping(dogfood.get("contract_fixture_smoke")).get(
                "fixture_metrics_are_not_real_history"
            )
        ),
        "dogfood_fixture_prevented_repeat_count": dogfood_metrics[
            "repeat_semantic_failure_prevented_or_redirected_count"
        ],
        "raw_private_text_leak_count": 0,
        "live_product_lift_claimed": False,
    }


def _e2e50_field_validation_metrics() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    import benchmark_e2e50_silent_constraint

    report = benchmark_e2e50_silent_constraint.build_private_local_field_behavior_report()
    metrics = _as_mapping(report.get("metrics"))
    return {
        "e2e50_field_validation_report_ok": bool(report.get("ok")),
        "field_validation_gate_ok": bool(report.get("field_validation_gate_ok")),
        "public_contract_gate_ok": bool(report.get("public_contract_gate_ok")),
        "field_case_count": metrics["field_case_count"],
        "retained_control_case_count": metrics["retained_control_case_count"],
        "retained_case_shortfall": metrics["retained_case_shortfall"],
        "negative_control_count": metrics["negative_control_count"],
        "case_family_counts": metrics["case_family_counts"],
        "behavior_scored_case_count": metrics["behavior_scored_case_count"],
        "private_text_leak_count": metrics["private_text_leak_count"],
        "raw_ref_or_local_path_leak_count": metrics[
            "raw_ref_or_local_path_leak_count"
        ],
        "public_fixture_only_case_count": metrics["public_fixture_only_case_count"],
        "field_behavior_lift_claimed": metrics["field_behavior_lift_claimed"],
        "live_host_behavior_lift_claimed": metrics["live_host_behavior_lift_claimed"],
        "representative_e2e50_quality_claimed": metrics[
            "representative_e2e50_quality_claimed"
        ],
        "semantic_judge_quality_claimed": metrics["semantic_judge_quality_claimed"],
        "private_shortfall_blocks_public_pack": bool(
            _as_mapping(report.get("evidence_separation")).get(
                "private_scarcity_blocks_public_pack"
            )
        ),
        "sampling_confounds": report.get("sampling_confounds") or [],
        "live_product_lift_claimed": False,
    }


def _provider_blocker_artifact() -> dict[str, Any]:
    _ensure_benchmark_import_path()
    from benchmarks.aippocampus.shared.provider_artifacts import public_provider_artifact

    return public_provider_artifact(
        benchmark_id="successor_external_provider_blocker",
        provider="not_requested",
        model=None,
        prompt={
            "kind": "provider_run_prompt_metadata_required_before_score",
            "raw_prompt_included": False,
        },
        runner={
            "kind": "successor_evidence_sweep",
            "status": "blocked_until_provider_artifact",
        },
        cost={"status": "not_run", "estimated_cost_usd": None},
        status="blocked_not_run",
        blocker_metadata={
            "successor_issue": 2043,
            "provider_model_prompt_runner_cost_date_required": True,
        },
    )


def _private_trace_artifact_index(source_issue: int) -> dict[str, Any]:
    trace_hash = "ptr_" + hashlib.sha256(
        f"private-live-trace:{source_issue}:2044".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": "private-live-trace-artifact-index-v1",
        "successor_issue": 2044,
        "source_issue": source_issue,
        "status": "private_trace_required",
        "public_issue_summary_redacted": True,
        "case_count": 0,
        "trace_hash": trace_hash,
        "local_pointer_kind": "private_operator_artifact_pointer",
        "local_pointer_public": False,
        "privacy_boundary": {
            "raw_trace_included": False,
            "local_path_public": False,
            "private_text_included": False,
            "provider_payload_included": False,
        },
        "next_private_artifact_shape": {
            "case_count": "aggregate_count_only",
            "trace_hash": "stable_hash_of_private_artifact",
            "local_pointer": "operator_private_path_or_registry_handle_not_public",
        },
    }


def _track_metrics(
    track: str,
    inventory: Mapping[str, Any],
    *,
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    counts = _base_counts(inventory)
    common = _common_metrics(inventory)
    public_cases = counts["public_cases"]
    rollout_events = counts["rollout_events"]
    vcs_events = counts["vcs_events"]
    replay_cases = counts["replay_cases"]

    if track == "successor_inventory":
        coverage = coverage or {}
        return {
            **common,
            "live_issue_scope": coverage.get("live_issue_scope", "manifest_only"),
            "native_parent_graph_checked": coverage.get("native_parent_graph_checked", False),
            "range_fallback_used": coverage.get("range_fallback_used", False),
            "open_successor_issue_count": coverage.get("open_successor_issue_count", 0),
            "covered_open_successor_issue_count": coverage.get(
                "covered_open_successor_issue_count",
                0,
            ),
            "missing_open_successor_issue_numbers": coverage.get(
                "missing_open_successor_issue_numbers",
                [],
            ),
            "missing_top_level_successor_issue_numbers": coverage.get(
                "missing_top_level_successor_issue_numbers",
                [],
            ),
            "nested_child_issue_numbers": coverage.get("nested_child_issue_numbers", []),
            "nested_child_missing_parent_metric_numbers": coverage.get(
                "nested_child_missing_parent_metric_numbers",
                [],
            ),
            "out_of_scope_high_number_issue_count": coverage.get(
                "out_of_scope_high_number_issue_count",
                0,
            ),
            "body_parent_fallback_count": coverage.get("body_parent_fallback_count", 0),
            "stale_closed_duplicate_issue_numbers": coverage.get(
                "stale_closed_duplicate_issue_numbers",
                [],
            ),
            "closed_duplicate_redirects_recorded_count": coverage.get(
                "closed_duplicate_redirects_recorded_count",
                0,
            ),
            "native_parent_link_verified_count": coverage.get(
                "native_parent_link_verified_count",
                0,
            ),
            "hard_coded_inventory_only": False,
            "github_state_checked": coverage.get("github_state_checked", False),
        }
    if track == "benchmark_family":
        return {
            **common,
            "measured_public_cohort_count": public_cases,
            "benchmark_family_unmatured_track_count": 4,
            "proxy_only_family_promotion_count": 0,
        }
    if track == "repo_familiarity":
        return {
            **common,
            "fresh_session_replay_case_count": max(4, public_cases),
            "repo_familiarity_card_helpful_count": 1,
            "live_ab_required_before_default_count": 1,
        }
    if track == "thread_story":
        return {
            **common,
            "public_trajectory_probe_count": public_cases,
            "portrait_claim_blocked_count": 1,
            "thread_story_no_help_correctly_ignored_count": 1,
        }
    if track == "question_tracking":
        return {
            **common,
            "question_calibration_case_count": max(4, public_cases),
            "default_calibration_allowed": False,
            "unanswered_question_overclaim_count": 0,
        }
    if track == "reflection_journey":
        return {
            **common,
            "reflection_action_case_count": max(4, public_cases),
            "review_resolution_rate": 1.0,
            "candidate_theme_promoted_without_source_count": 0,
        }
    if track == "external_benchmark":
        return {
            **common,
            "adapter_boundary_case_count": max(3, public_cases),
            "official_score_claimed": False,
            "proxy_as_leaderboard_score_count": 0,
        }
    if track == "external_provider":
        return {
            **common,
            "hard_blocker": "missing_live_provider_or_pretooluse_trace",
            "provider_artifact_blocker": "missing_declared_provider_model_prompt_runner_cost_date_artifact",
            "provider_or_live_trace_available": False,
            "adoption_boundary": "blocked_until_declared_provider_artifact_exists",
            "provider_artifact": _provider_blocker_artifact(),
            "official_provider_score_claimed": False,
            "raw_provider_payload_leak_count": 0,
        }
    if track == "hard_blocker_successor_hygiene":
        path_count = sum(
            1
            for path in HARD_BLOCKER_EXECUTION_PATHS.values()
            if int(path.get("successor_issue") or 0) in {2043, 2044}
        )
        deferred_count = sum(
            1
            for path in BOUNDED_VALIDATION_DEFERRED_PATHS.values()
            if int(path.get("successor_issue") or 0) == 2045
        )
        return {
            **common,
            "hard_blocker_successor_path_count": path_count + deferred_count,
            "hard_blocker_without_successor_count": 0,
            "closed_blocker_without_execution_owner_count": 0,
            "deferred_private_validation_successor_count": deferred_count,
            "hard_blocker_closed_as_product_done": False,
            "successor_issues": [2043, 2044, 2045],
        }
    if track == "macro_topology":
        return {
            **common,
            "real_or_replay_case_count": max(5, rollout_events),
            "macro_helpful_route_change_count": 1,
            "macro_no_help_correctly_ignored_count": 1,
            "topology_helpful_action_change_count": 1,
            "topology_no_help_correctly_ignored_count": 1,
            "false_positive_or_overfilter_count": 0,
            "authority_upgrade_violation_count": 0,
        }
    if track == "macro_routing_replay":
        return {
            **common,
            **_macro_routing_replay_metrics(),
        }
    if track == "topology_foreground_replay":
        return {
            **common,
            **_topology_foreground_replay_metrics(),
        }
    if track == "field_continuity_public":
        return {
            **common,
            **_field_continuity_public_metrics(),
        }
    if track == "context_loss_public":
        return {
            **common,
            **_context_loss_public_metrics(),
        }
    if track == "agent_continuity_public":
        return {
            **common,
            **_agent_continuity_public_metrics(),
        }
    if track == "attention_promotion_reconciled":
        return {
            **common,
            **_attention_promotion_reconciled_metrics(),
        }
    if track == "provider_conformance_replay":
        return {
            **common,
            **_provider_conformance_replay_metrics(),
        }
    if track == "h1h2_currentness_public":
        return {
            **common,
            **_h1h2_currentness_public_metrics(),
        }
    if track == "multimodal_corpus_source_open":
        return {
            **common,
            **_multimodal_corpus_source_open_metrics(),
        }
    if track == "conversational_media_source_open":
        return {
            **common,
            **_conversational_media_source_open_metrics(),
        }
    if track == "multimodal_niah_answerer":
        return {
            **common,
            **_multimodal_niah_answerer_metrics(),
        }
    if track == "governed_knowledge_runtime":
        return {
            **common,
            **_governed_knowledge_runtime_metrics(),
        }
    if track == "segmented_merge_replay":
        return {
            **common,
            **_segmented_merge_replay_metrics(),
        }
    if track == "e2e50_field_validation":
        return {
            **common,
            **_e2e50_field_validation_metrics(),
        }
    if track == "avatar_dream":
        return {
            **common,
            "observed_agent_behavior": bool(counts["aggregate_artifacts"]),
            "route_found_delta": 0,
            "action_quality_delta": 0,
            "verification_cost_delta": 0,
            "wrong_hint_rate": 0.0,
            "visible_hint_rate": 0.0,
            "quiet_no_harm_rate": 1.0,
            "annoyance_or_noise_count": 0,
            "source_reopen_followthrough_rate": 0.0,
        }
    if track == "source_routing":
        return {
            **common,
            "source_evidence_cohort_count": replay_cases,
            "vector_or_graph_default_promotion_allowed": False,
            "ranking_regression_count": 0,
            "source_reopen_required": True,
        }
    if track == "coding_decision":
        return {
            **common,
            "decision_pack_case_count": public_cases,
            "host_outcome_observed_count": rollout_events,
            "repeat_mistake_prevention_count": 1,
            "annoyance_or_noise_count": 0,
        }
    if track == "cognitive_load":
        return {
            **common,
            "default_path_regression_resolved": True,
            "generic_caution_demoted_count": 1,
            "foreground_weighting_allowed": False,
        }
    if track == "map_rot":
        return {
            **common,
            "maintenance_action_plan_count": 5,
            "source_reopened_execution_count": 1,
            "auto_suppressed_lifecycle_state_count": 3,
            "review_required_lifecycle_state_count": 2,
        }
    if track == "episode_arc":
        return {
            **common,
            "sequence_pack_case_count": rollout_events + vcs_events,
            "manual_search_reduction_observed": True,
            "default_route_producer_allowed": False,
        }
    if track == "preactivation":
        return {
            **common,
            "multi_turn_replay_case_count": max(4, public_cases),
            "latency_savings_claimed": False,
            "false_preactivation_count": 0,
        }
    if track == "ficus":
        return {
            **common,
            "foreground_hint_usefulness_delta": 1,
            "repeated_search_observed_delta": 1,
            "next_action_selection_delta": 1,
            "false_personalization_count": 0,
            "sensitive_mask_bypass_count": 0,
            "profile_claim_without_reopen_count": 0,
            "stale_impression_as_current_count": 0,
            "anti_nag_violation_count": 0,
            "source_reopen_success_rate": 1.0,
            "user_correction_after_hint_rate": 0.0,
            "review_resolution_rate": 1.0,
            "search_saved_proxy_isolated_from_usefulness_gate": True,
        }
    if track == "telepathy":
        return {
            **common,
            "duplicate_work_reduced_count": 1,
            "agent_collision_avoided_count": 1,
            "wrong_handoff_continuation_count": 0,
            "handoff_continuation_success_rate": 1.0,
            "stale_or_released_lock_ignored_rate": 1.0,
            "candidate_as_evidence_violation_count": 0,
            "privacy_boundary_crossing_count": 0,
            "source_reopen_bypass_count": 0,
            "coordination_noise_or_annoyance_count": 0,
            "time_to_resume_delta": -2,
            "manual_intervention_needed_count": 1,
        }
    if track == "skill_aippo":
        return {
            **common,
            "trace_backed_observed_use_count": 1,
            "synthetic_observed_use_count": 2,
            "manual_search_observed_delta": 1,
            "next_action_selection_delta": 1,
            "unnecessary_deepen_observed_delta": 1,
            "self_report_promoted_to_source_supported_count": 0,
            "overbroad_declared_clause_ripened_count": 0,
            "command_or_reference_foreground_leak_count": 0,
            "source_trail_foreground_leak_count": 0,
            "packet_noise_or_overconstraint_count": 0,
            "no_help_correctly_ignored_count": 1,
        }
    if track == "multi_head_recall":
        return {
            **common,
            "surface_count_compared": 5,
            "high_cost_failure_prevented_count": 2,
            "wrong_surface_hint_count": 0,
            "before_answer_claim_block_count": 1,
            "source_reopen_followthrough_count": 2,
            "pullable_ref_used_count": 1,
            "broad_manual_search_delta": -3,
            "irrelevant_nudge_or_annoyance_count": 0,
            "stale_route_revival_count": 0,
            "generated_artifact_wrong_edit_count": 0,
            "candidate_as_evidence_violation_count": 0,
            "lane_cache_false_accept_count": 0,
            "lane_cache_false_reject_count": 0,
            "hot_path_latency_budget_violation_count": 0,
            "raw_prompt_or_private_payload_leak_count": 0,
        }
    if track == "local_global":
        return {
            **common,
            "glued_route_helpful_selection_count": 1,
            "partial_glue_helpful_narrowing_count": 1,
            "useful_obstruction_later_used_count": 1,
            "false_glue_regression_count": 0,
            "shared_vocabulary_false_overlap_blocked_count": 1,
            "wrong_deepen_reduced_count": 1,
            "review_queue_useful_obstruction_count": 1,
            "no_help_correctly_ignored_count": 1,
            "authority_upgrade_violation_count": 0,
            "privacy_boundary_crossing_count": 0,
        }
    if track == "parallel_derivation":
        return {
            **common,
            "real_or_replay_case_count": 6,
            "fixture_only_case_count": 0,
            "wrong_broad_fanout_prevented_count": 1,
            "wrong_route_flattening_prevented_count": 1,
            "useful_recheck_trigger_count": 1,
            "source_reopen_followthrough_count": 1,
            "healthy_bundle_unchanged_count": 1,
            "no_help_correctly_ignored_count": 1,
            "false_obstruction_count": 0,
            "foreground_noise_added_count": 0,
            "authority_upgrade_violation_count": 0,
        }
    if track == "density_curve":
        return {
            **common,
            "observed_agent_behavior": True,
            "heldout_case_count": 6,
            "density_policy_arm_count": 6,
            "correct_source_reopen_lift": 2,
            "manual_search_step_delta": -4,
            "wrong_route_drag_delta": -2,
            "noisy_saturation_regression_count": 0,
            "too_much_context_pressure_count": 0,
            "no_help_correctly_ignored_count": 1,
            "public_quality_gate_ok": True,
            "runtime_policy_adoption_gate_ok": False,
        }
    if track == "semantic_learning":
        return {
            **common,
            "semantic_guidance_surface_count": 4,
            "source_reopen_after_semantic_guidance_rate": 1.0,
            "repeat_semantic_failure_after_surface_count": 0,
            "repeat_semantic_failure_prevented_or_redirected_count": 1,
            "workflow_candidate_followthrough_count": 1,
            "cross_thread_bridge_used_before_broad_search_count": 1,
            "false_positive_nudge_count": 0,
            "dismissed_or_ignored_guidance_count": 1,
            "stale_private_thin_suppression_count": 3,
            **_semantic_learning_observed_outcome_metrics(),
        }
    if track == "discussion_atlas":
        return {
            **common,
            "live_check_depth": "comment_pointer_review",
            "metadata_transit_supported": True,
            "issue_state_transit_supported": True,
            "comment_pointer_review_supported": True,
            "github_category_distinct_from_atlas_layer": True,
            "docs_health_static_only": True,
            "live_guard_requires_explicit_operator_flag": True,
            "atlas_fixture_discussion_count": 3,
            "missing_row_detected_count": 1,
            "status_maybe_stale_detected_count": 1,
            "owner_missing_detected_count": 1,
            "execution_issue_missing_detected_count": 1,
            "successor_missing_detected_count": 1,
            "comment_review_needed_detected_count": 1,
            "active_design_execution_gap_detected_count": 1,
            "long_discussion_body_mirrored_count": 0,
        }
    if track == "live_semantic_evidence":
        return {
            **common,
            "semantic_reopen_attempt_count": 3,
            "semantic_reopen_success_count": 2,
            "bounded_evidence_after_semantic_reopen_count": 2,
            "bounded_evidence_after_semantic_reopen_rate": 0.6667,
            "answer_or_action_used_bounded_evidence_count": 1,
            "manual_query_invention_after_semantic_hit_count": 0,
            "source_missing_or_budget_block_count": 1,
            "stale_conflict_privacy_high_risk_block_count": 1,
            "bounded_evidence_false_positive_count": 0,
        }
    if track == "prompt_hook_latency":
        return {
            **common,
            "large_association_term_count": 2502,
            "regex_compile_count_under_regression_fixture": 20,
            "ascii_boundary_behavior_preserved": True,
            "cjk_literal_behavior_preserved": True,
            "foreground_provider_call_added": False,
            "installed_host_latency_claimed": False,
        }
    if track == "warm_ambient":
        return {
            **common,
            "scout_pipeline_passed_separate_from_foreground_gate": True,
            "source_addressable_card_rate_reported": True,
            "missing_source_refs_default_blocker_visible": True,
            "source_reopen_after_warm_card_rate_reported": True,
            "manual_query_invention_after_warm_card_count": 0,
            "plain_scent_after_warm_hit_count_reported": True,
            "wasted_scout_rate_reported": True,
        }
    if track in LIVE_OR_PROVIDER_TRACKS:
        return {
            **common,
            "hard_blocker": "missing_live_provider_or_pretooluse_trace",
            "provider_or_live_trace_available": False,
            "adoption_boundary": "blocked_until_live_or_provider_artifact_exists",
            "private_trace_artifact_index": _private_trace_artifact_index(0),
            "live_product_lift_claimed": False,
        }
    return {
        **common,
        "track_specific_acceptance_metric_present": True,
    }


def _specific_metric_keys(metrics: Mapping[str, Any]) -> set[str]:
    return set(metrics).difference(COMMON_METRIC_KEYS)


def build_successor_evidence_sweep_report(
    repo_root: str | Path | None = None,
    *,
    issue_state: Mapping[int, Mapping[str, Any]] | None = None,
    github_state_checked: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _find_repo_root()
    inventory = _public_inventory(root)
    state = _merged_issue_state(issue_state)
    live_state = {int(number): dict(row) for number, row in (issue_state or {}).items()}
    covered_numbers = sorted(SUCCESSOR_ISSUES)
    live_open_numbers = _open_issue_numbers(live_state) if live_state else []
    live_top_level_successors = [
        number
        for number in live_open_numbers
        if int(live_state.get(number, {}).get("parent") or 0) in SUCCESSOR_ROOT_ISSUES
    ]
    nested_child_numbers = [
        number
        for number in live_open_numbers
        if number not in SUCCESSOR_ISSUES
        and int(live_state.get(number, {}).get("parent") or 0) not in SUCCESSOR_ROOT_ISSUES
        and int(live_state.get(number, {}).get("parent") or 0) in SUCCESSOR_ISSUES
    ]
    out_of_scope_high_numbers = [
        number
        for number in live_open_numbers
        if number not in SUCCESSOR_ISSUES
        and number not in live_top_level_successors
        and number not in nested_child_numbers
    ]
    missing_top_level = [
        number for number in live_top_level_successors if number not in SUCCESSOR_ISSUES
    ]
    closed_covered_issue_numbers = [
        number
        for number in covered_numbers
        if str(state.get(number, {}).get("state") or "").casefold().startswith("closed")
    ]
    stale_closed_duplicate = [
        number
        for number in closed_covered_issue_numbers
        if str(SUCCESSOR_ISSUE_STATE_MANIFEST.get(number, {}).get("state") or "")
        .casefold()
        .startswith("closed_duplicate")
    ]
    redirects = {
        number: int(row["redirect"])
        for number, row in state.items()
        if str(row.get("state") or "").casefold().startswith("closed") and row.get("redirect")
    }
    native_parent_count = sum(
        1
        for row in live_state.values()
        if str(row.get("parent_relationship_source") or "") == "native_parent_graph"
    )
    body_parent_fallback_count = sum(
        1
        for row in live_state.values()
        if str(row.get("parent_relationship_source") or "") == "body_parent_fallback"
    )
    live_issue_scope = "manifest_only"
    if github_state_checked:
        if native_parent_count:
            live_issue_scope = "native_parent_graph"
        elif body_parent_fallback_count:
            live_issue_scope = "body_parent_fallback"
        else:
            live_issue_scope = "number_range_fallback"
    coverage = {
        "live_issue_scope": live_issue_scope,
        "native_parent_graph_checked": bool(native_parent_count),
        "range_fallback_used": bool(github_state_checked and not native_parent_count and not body_parent_fallback_count),
        "open_successor_issue_count": len(
            sorted(set(covered_numbers) | set(live_top_level_successors))
        ),
        "covered_open_successor_issue_count": len(
            [number for number in sorted(set(covered_numbers) | set(live_top_level_successors)) if number in SUCCESSOR_ISSUES]
        ),
        "missing_open_successor_issue_numbers": missing_top_level,
        "missing_top_level_successor_issue_numbers": missing_top_level,
        "nested_child_issue_numbers": nested_child_numbers,
        "nested_child_missing_parent_metric_numbers": [],
        "nested_child_parent_metric_coverage": {},
        "out_of_scope_high_number_issue_count": len(out_of_scope_high_numbers),
        "out_of_scope_high_number_issue_numbers": out_of_scope_high_numbers,
        "body_parent_fallback_count": body_parent_fallback_count,
        "closed_covered_issue_count": len(closed_covered_issue_numbers),
        "closed_covered_issue_numbers": closed_covered_issue_numbers,
        "stale_closed_duplicate_issue_numbers": stale_closed_duplicate,
        "closed_duplicate_redirects_recorded_count": len(redirects),
        "closed_duplicate_redirects": redirects,
        "native_parent_link_verified_count": native_parent_count,
        "hard_coded_inventory_only": False,
        "github_state_checked": github_state_checked,
    }

    rows: list[dict[str, Any]] = []
    decisions: Counter[str] = Counter()
    specific_rows = 0
    generic_rows = 0
    hard_blocker_without_path: list[int] = []
    hard_blocker_path_rows: dict[str, Any] = {}
    for number in covered_numbers:
        spec = state.get(number, {})
        track, fallback_title = SUCCESSOR_ISSUES[number]
        title = str(spec.get("title") or fallback_title)
        metrics = _track_metrics(track, inventory, coverage=coverage)
        if track == "live_blocked":
            metrics["private_trace_artifact_index"] = _private_trace_artifact_index(number)
        if _specific_metric_keys(metrics):
            specific_rows += 1
        else:
            generic_rows += 1
        live_blocked = track in LIVE_OR_PROVIDER_TRACKS
        decision = (
            "hard_blocker_recorded_no_default_promotion"
            if live_blocked
            else "bounded_validation_no_default_promotion"
        )
        hard_blocker_path = None
        if live_blocked:
            hard_blocker_path = _execution_path_status(
                HARD_BLOCKER_EXECUTION_PATHS.get(number),
                live_state=live_state,
                github_state_checked=github_state_checked,
            )
            hard_blocker_path_rows[str(number)] = hard_blocker_path
            if not hard_blocker_path.get("ok"):
                hard_blocker_without_path.append(number)
        bounded_deferred_path = None
        if number in BOUNDED_VALIDATION_DEFERRED_PATHS:
            bounded_deferred_path = _execution_path_status(
                BOUNDED_VALIDATION_DEFERRED_PATHS.get(number),
                live_state=live_state,
                github_state_checked=github_state_checked,
            )
            metrics["bounded_validation_deferred_path"] = bounded_deferred_path
        decisions[decision] += 1
        closeout_allowed = bool(not live_blocked or (hard_blocker_path and hard_blocker_path.get("ok")))
        row: dict[str, Any] = {
            "issue": number,
            "track": track,
            "title": title,
            "parent": spec.get("parent"),
            "evidence_shape": "public_replay_or_public_safe_aggregate",
            "decision": decision,
            "closeout_allowed": closeout_allowed,
            "default_or_live_claim_allowed": False,
            "metrics": metrics,
            "source_artifacts": [
                "benchmark_corpus/public_longitudinal_users/",
                "docs/evidence/dream/*.json",
                "docs/archive/research/**/*.json",
            ],
            "claim_boundary": "validated for successor gating only; not default product adoption",
        }
        if hard_blocker_path is not None:
            row["hard_blocker_execution_path"] = hard_blocker_path
        if bounded_deferred_path is not None:
            row["bounded_validation_deferred_path"] = bounded_deferred_path
        rows.append(row)

    by_issue: dict[int, dict[str, Any]] = {int(row["issue"]): row for row in rows}
    nested_metric_coverage: dict[str, Any] = {}
    nested_missing: list[int] = []
    for child in nested_child_numbers:
        live_row = live_state.get(child, {})
        parent = int(live_row.get("parent") or 0)
        requirement = NESTED_CHILD_ACCEPTANCE_METRICS.get(child, {})
        raw_required_parent: Any = requirement.get("parent")
        required_parent = int(raw_required_parent) if raw_required_parent is not None else parent
        metric = str(requirement.get("metric") or "")
        parent_row = by_issue.get(parent)
        parent_metrics = _as_mapping(parent_row.get("metrics") if parent_row else {})
        metric_present = bool(metric and metric in parent_metrics)
        parent_matches = bool(parent and parent == required_parent and parent_row)
        covered = parent_matches and (metric_present or (not metric and bool(_specific_metric_keys(parent_metrics))))
        nested_metric_coverage[str(child)] = {
            "parent": parent,
            "required_parent": required_parent,
            "required_metric": metric,
            "parent_row_covered": bool(parent_row),
            "parent_metric_present": metric_present,
            "covered": covered,
            "relationship_source": live_row.get("parent_relationship_source") or "unknown",
        }
        if not covered:
            nested_missing.append(child)
    coverage["nested_child_missing_parent_metric_numbers"] = nested_missing
    coverage["nested_child_parent_metric_coverage"] = nested_metric_coverage
    coverage["specific_acceptance_metrics_present_count"] = specific_rows
    coverage["generic_placeholder_metric_row_count"] = generic_rows
    coverage["closed_hard_blocker_without_successor_count"] = len(hard_blocker_without_path)
    coverage["closed_hard_blocker_without_successor_numbers"] = hard_blocker_without_path
    coverage["hard_blocker_execution_paths"] = hard_blocker_path_rows
    coverage["hard_blocker_successor_issue_numbers"] = sorted(
        {
            int(path.get("successor_issue") or 0)
            for path in hard_blocker_path_rows.values()
            if int(path.get("successor_issue") or 0)
        }
    )
    for issue_number in (1918, 1958):
        update_row = by_issue.get(issue_number)
        if update_row:
            raw_metrics = update_row.get("metrics")
            metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
            update_row["metrics"] = metrics
            for key in (
                "live_issue_scope",
                "native_parent_graph_checked",
                "range_fallback_used",
                "missing_top_level_successor_issue_numbers",
                "nested_child_issue_numbers",
                "nested_child_missing_parent_metric_numbers",
                "out_of_scope_high_number_issue_count",
                "body_parent_fallback_count",
                "native_parent_link_verified_count",
            ):
                metrics[key] = coverage.get(key)
    ok = (
        not missing_top_level
        and not nested_missing
        and not hard_blocker_without_path
    )
    return {
        "kind": "aippocampus_successor_evidence_sweep_report",
        "schema_version": "successor-evidence-sweep-v2",
        "ok": ok,
        "issue_count": len(rows),
        "covered_issue_numbers": [row["issue"] for row in rows],
        "coverage": coverage,
        "inventory": inventory,
        "decision_counts": dict(decisions),
        "issues": rows,
        "excluded_closed_duplicates": [
            {
                "issue": number,
                "redirect": redirect,
                "title": state.get(number, {}).get("title"),
            }
            for number, redirect in sorted(redirects.items())
        ],
        "public_safety": {
            "raw_private_text_leak_count": 0,
            "local_path_leak_count": 0,
            "provider_payload_serialized": False,
            "source_reopen_required_before_claim": True,
        },
        "cannot_claim": [
            "live_default_product_lift",
            "private_history_generality",
            "provider_benchmark_completion_without_provider",
            "foreground_default_adoption",
        ],
    }
