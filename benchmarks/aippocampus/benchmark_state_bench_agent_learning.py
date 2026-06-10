#!/usr/bin/env python3
"""STATE-Bench Agent Learning Track feasibility bridge for #1043.

This runner owns only the adapter/readiness slice. It can inspect a local
operator-provided STATE-Bench checkout, derive public-safe learning strings
from train trajectories, and generate a read-only `retrieve_learnings` adapter.
It does not run the official simulator/judge or claim task-performance lift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import _paths
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_state_bench_agent_learning_feasibility"
STATE_BENCH_REPO = "https://github.com/microsoft/STATE-Bench"
AGENT_LEARNING_DOC = f"{STATE_BENCH_REPO}/blob/main/docs/AGENT_LEARNING_TRACK.md"
SUBMIT_DOC = f"{STATE_BENCH_REPO}/blob/main/docs/SUBMIT.md"
ISSUE_VERIFIED_COMMIT = "83cb96de5429c43adfdb5cb9b6785439e937a3ca"
DOMAINS = ("travel", "customer_support", "shopping_assistant")
OFFICIAL_TRAIN_PER_DOMAIN = 100
OFFICIAL_TEST_PER_DOMAIN = 50
OFFICIAL_NUM_RUNS = 5
OFFICIAL_TOP_K = 3
DEFAULT_STATE_BENCH_ROOT = _paths.REPO_ROOT / ".tmp" / "state-bench-upstream"
DEFAULT_ADAPTER_ROOT = _paths.REPO_ROOT / ".tmp" / "state-bench-aippocampus"

CANNOT_CLAIM = [
    "official_state_bench_score",
    "agent_learning_track_lift",
    "leaderboard_submission_ready",
    "end_to_end_task_performance",
    "heldout_test_quality",
    "matched_no_memory_task_score",
    "state_bench_sota",
    "private_registry_quality",
]

RAW_TEXT_KEYS = {"content", "message", "messages", "prompt", "response", "text"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def safe_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_file:{sha1_short(str(resolved))}"


def tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.lower()) if len(token) > 2}


def public_task_terms(path: Path) -> list[str]:
    terms = [
        token
        for token in re.split(r"[^A-Za-z0-9_]+", path.stem)
        if token and not token.isdigit() and len(token) > 2
    ]
    return terms[:8]


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def train_domain_dir(state_bench_root: Path, domain: str) -> Path:
    return state_bench_root / "datasets" / "train_task_trajectories" / domain


def discover_train_files(state_bench_root: Path, domain: str) -> list[Path]:
    domain_dir = train_domain_dir(state_bench_root, domain)
    if not domain_dir.exists():
        return []
    return sorted(path for path in domain_dir.glob("*.json") if path.is_file())


def _tool_summary(row: Any) -> tuple[list[str], list[str], list[str]]:
    tool_names: list[str] = []
    policy_topics: list[str] = []
    policy_rule_keys: list[str] = []
    for item in _walk(row):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name and ("result" in item or "arguments" in item):
            if name not in tool_names:
                tool_names.append(name)
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        topic = arguments.get("topic") or result.get("topic")
        if isinstance(topic, str) and topic and topic not in policy_topics:
            policy_topics.append(topic)
        rules = result.get("rules") if isinstance(result.get("rules"), dict) else {}
        for key in rules:
            text = str(key)
            if text and text not in policy_rule_keys:
                policy_rule_keys.append(text)
    return tool_names[:12], policy_topics[:8], policy_rule_keys[:16]


def _raw_text_key_count(row: Any) -> int:
    count = 0
    for item in _walk(row):
        if isinstance(item, dict):
            count += sum(1 for key in item if str(key).lower() in RAW_TEXT_KEYS)
    return count


def learning_from_trajectory(path: Path, row: Any, *, domain: str) -> dict[str, Any]:
    tool_names, policy_topics, policy_rule_keys = _tool_summary(row)
    task_terms = public_task_terms(path)
    parts = [
        f"STATE-Bench {domain} learning",
        f"task_terms={','.join(task_terms) or 'unknown'}",
    ]
    if tool_names:
        parts.append(f"tool_sequence={','.join(tool_names)}")
    if policy_topics:
        parts.append(f"policy_topics={','.join(policy_topics)}")
    if policy_rule_keys:
        parts.append(f"policy_rule_keys={','.join(policy_rule_keys)}")
    parts.append("use as a retrieval hint only; verify with STATE-Bench domain tools before action")
    learning = "; ".join(parts)
    return {
        "learning_id": f"statebench:{domain}:{sha1_short(path.name)}",
        "domain": domain,
        "task_id": path.stem,
        "learning": learning,
        "query_terms": sorted(tokenize(" ".join([path.stem, learning]))),
        "tool_names": tool_names,
        "policy_topics": policy_topics,
        "policy_rule_keys": policy_rule_keys,
        "raw_text_field_count": _raw_text_key_count(row),
    }


def extract_learnings(
    state_bench_root: Path,
    *,
    domain: str,
    max_train_files: int | None = None,
) -> list[dict[str, Any]]:
    learnings: list[dict[str, Any]] = []
    files = discover_train_files(state_bench_root, domain)
    if max_train_files is not None:
        files = files[: max(max_train_files, 0)]
    for path in files:
        row = read_json(path)
        learnings.append(learning_from_trajectory(path, row, domain=domain))
    return learnings


def rank_learnings(query: str, learnings: Sequence[str | dict[str, Any]], *, top_k: int = OFFICIAL_TOP_K) -> list[str]:
    query_terms = tokenize(query)
    scored: list[tuple[int, int, str]] = []
    for index, item in enumerate(learnings):
        text = item if isinstance(item, str) else str(item.get("learning") or "")
        item_terms = tokenize(text)
        score = len(query_terms & item_terms)
        scored.append((score, -index, text))
    scored.sort(reverse=True)
    return [text for score, _index, text in scored[: max(top_k, 0)] if text and (score > 0 or not query_terms)]


def build_retrieval_comparison(learnings: Sequence[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    queries = [" ".join(learning.get("query_terms", [])[:5]) for learning in learnings[:3]]
    retrieved = [rank_learnings(query, learnings, top_k=top_k) for query in queries]
    retrieved_count = sum(len(items) for items in retrieved)
    if not learnings:
        return {"comparison_kind": "not_run", "reason": "no_train_learnings_extracted"}
    return {
        "comparison_kind": "adapter_retrieval_contract",
        "official_task_run_count": 0,
        "matched_harness": "same fixture queries and top_k; not a STATE-Bench task run",
        "case_count": len(queries),
        "no_memory": {"retrieved_learning_count": 0},
        "aippocampus": {
            "retrieved_learning_count": retrieved_count,
            "retrieved_nonempty_case_count": sum(1 for items in retrieved if items),
        },
        "cannot_read_as": "task_success_lift_or_official_baseline",
    }


def adapter_source() -> str:
    return '''from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from state_bench.agents.state_bench import StateBenchAgent


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.lower()) if len(token) > 2}


def _learning_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("learning") or "")
    return ""


def _learnings_path() -> Path:
    env_path = os.environ.get("AIPPOCAMPUS_STATE_BENCH_LEARNINGS")
    return Path(env_path) if env_path else Path(__file__).with_name("learnings.json")


class AIppocampusStateBenchAgent(StateBenchAgent):
    """Read-only STATE-Bench Agent Learning Track adapter."""

    def retrieve_learnings(self, query: str, top_k: int = 3) -> list[str]:
        path = _learnings_path()
        if not path.exists():
            return []
        rows = json.loads(path.read_text(encoding="utf-8"))
        query_terms = _tokens(query)
        scored: list[tuple[int, int, str]] = []
        for index, item in enumerate(rows):
            text = _learning_text(item)
            score = len(query_terms & _tokens(text))
            scored.append((score, -index, text))
        scored.sort(reverse=True)
        return [
            text
            for score, _index, text in scored[: max(int(top_k), 0)]
            if text and (score > 0 or not query_terms)
        ]
'''


def write_state_bench_adapter(*, output_dir: Path, learnings_path: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter_path = output_dir / "aippocampus_state_bench_agent.py"
    adapter_path.write_text(adapter_source(), encoding="utf-8")
    return adapter_path


def write_learnings(path: Path, learnings: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([row["learning"] for row in learnings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_state_bench_agent_learning_report(
    *,
    state_bench_root: Path = DEFAULT_STATE_BENCH_ROOT,
    domain: str = "customer_support",
    max_train_files: int | None = None,
    adapter_output_dir: Path | None = None,
    learnings_output: Path | None = None,
    write_adapter: bool = False,
    official_commit: str = ISSUE_VERIFIED_COMMIT,
) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise ValueError(f"domain must be one of {', '.join(DOMAINS)}")
    root = Path(state_bench_root)
    if not root.exists():
        return _base_report(
            status="skipped_missing_state_bench_checkout",
            decision="no_go_missing_state_bench_checkout",
            state_bench_root=root,
            domain=domain,
            official_commit=official_commit,
        )
    train_files = discover_train_files(root, domain)
    if not train_files:
        return _base_report(
            status="skipped_missing_domain_train_trajectories",
            decision="no_go_missing_train_trajectories",
            state_bench_root=root,
            domain=domain,
            official_commit=official_commit,
        )
    learnings = extract_learnings(root, domain=domain, max_train_files=max_train_files)
    adapter_path = None
    if learnings_output is not None:
        write_learnings(Path(learnings_output), learnings)
    if write_adapter:
        adapter_dir = Path(adapter_output_dir or DEFAULT_ADAPTER_ROOT / "agents")
        adapter_path = write_state_bench_adapter(
            output_dir=adapter_dir,
            learnings_path=Path(learnings_output or DEFAULT_ADAPTER_ROOT / "learnings.json"),
        )
    raw_text_count = sum(int(row.get("raw_text_field_count") or 0) for row in learnings)
    report = _base_report(
        status="adapter_dry_run_ready",
        decision="no_go_adapter_only_no_official_run",
        state_bench_root=root,
        domain=domain,
        official_commit=official_commit,
    )
    report.update(
        {
            "metrics": {
                "official_train_trajectory_count_expected": OFFICIAL_TRAIN_PER_DOMAIN,
                "official_test_task_count_expected": OFFICIAL_TEST_PER_DOMAIN,
                "observed_train_trajectory_count": len(train_files),
                "inspected_train_trajectory_count": len(learnings),
                "extracted_learning_count": len(learnings),
                "source_raw_text_field_count_observed_but_not_emitted": raw_text_count,
                "retrieve_learnings_top_k": OFFICIAL_TOP_K,
                "official_num_runs_required": OFFICIAL_NUM_RUNS,
                "official_task_run_count": 0,
            },
            "comparison": build_retrieval_comparison(learnings, top_k=OFFICIAL_TOP_K),
            "artifacts": {
                "adapter_file_written": adapter_path is not None,
                "adapter_file": safe_path_label(adapter_path) if adapter_path else None,
                "learnings_file_written": learnings_output is not None,
                "learnings_file": safe_path_label(learnings_output) if learnings_output else None,
            },
            "learning_catalog": {
                "learning_ids": [row["learning_id"] for row in learnings[:20]],
                "domains": sorted({str(row["domain"]) for row in learnings}),
                "tool_names": sorted({tool for row in learnings for tool in row["tool_names"]}),
                "policy_topics": sorted({topic for row in learnings for topic in row["policy_topics"]}),
                "raw_learning_text_emitted": False,
            },
        }
    )
    return report


def _base_report(
    *,
    status: str,
    decision: str,
    state_bench_root: Path,
    domain: str,
    official_commit: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "ok": True,
        "status": status,
        "official_submission_decision": decision,
        "domain": domain,
        "official_requirements": {
            "state_bench_repo": STATE_BENCH_REPO,
            "state_bench_commit": official_commit,
            "agent_learning_track_doc": AGENT_LEARNING_DOC,
            "submit_doc": SUBMIT_DOC,
            "domains": list(DOMAINS),
            "train_trajectories_per_domain": OFFICIAL_TRAIN_PER_DOMAIN,
            "heldout_test_tasks_per_domain": OFFICIAL_TEST_PER_DOMAIN,
            "official_num_runs": OFFICIAL_NUM_RUNS,
            "retrieve_learnings_top_k": OFFICIAL_TOP_K,
            "hook_shape": "retrieve_learnings(query, top_k=3) -> list[str]",
            "train_only_learning_extraction": True,
            "heldout_test_oracle_allowed": False,
        },
        "runner_plan": {
            "state_bench_root": safe_path_label(state_bench_root),
            "adapter_class": "AIppocampusStateBenchAgent",
            "run_batch_module": "state_bench.scripts.run_batch",
            "compute_metrics_module": "state_bench.scripts.compute_metrics",
            "official_submission_outputs": [
                "outputs/<domain>/run1..run5/<task_id>.json",
                "outputs/<domain>/metrics.json",
            ],
        },
        "metrics": {
            "official_train_trajectory_count_expected": OFFICIAL_TRAIN_PER_DOMAIN,
            "official_test_task_count_expected": OFFICIAL_TEST_PER_DOMAIN,
            "observed_train_trajectory_count": 0,
            "extracted_learning_count": 0,
            "retrieve_learnings_top_k": OFFICIAL_TOP_K,
            "official_num_runs_required": OFFICIAL_NUM_RUNS,
            "official_task_run_count": 0,
        },
        "comparison": {"comparison_kind": "not_run"},
        "artifacts": {
            "adapter_file_written": False,
            "adapter_file": None,
            "learnings_file_written": False,
            "learnings_file": None,
        },
        "privacy_boundary": {
            "raw_trajectory_text_emitted": False,
            "raw_learning_text_emitted_in_report": False,
            "absolute_paths_emitted": False,
            "private_registry_text_used": False,
        },
        "claim_boundary": {
            "official_state_bench_score": "not_claimed",
            "agent_learning_track_lift": "not_measured",
            "adapter_hook_shape": "implemented_when_adapter_written",
            "matched_no_memory_baseline": "retrieval_contract_only_until_official_run",
        },
        "cannot_claim": list(CANNOT_CLAIM),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-bench-root", type=Path, default=DEFAULT_STATE_BENCH_ROOT)
    parser.add_argument("--domain", choices=DOMAINS, default="customer_support")
    parser.add_argument("--max-train-files", type=int)
    parser.add_argument("--official-commit", default=ISSUE_VERIFIED_COMMIT)
    parser.add_argument("--write-adapter", action="store_true")
    parser.add_argument("--adapter-output-dir", type=Path)
    parser.add_argument("--learnings-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_state_bench_agent_learning_report(
        state_bench_root=args.state_bench_root,
        domain=args.domain,
        max_train_files=args.max_train_files,
        adapter_output_dir=args.adapter_output_dir,
        learnings_output=args.learnings_output,
        write_adapter=args.write_adapter,
        official_commit=args.official_commit,
    )
    output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
