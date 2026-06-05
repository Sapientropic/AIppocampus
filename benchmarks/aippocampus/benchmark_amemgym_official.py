#!/usr/bin/env python3
"""Official AMemGym runner bridge and score summarizer.

This helper does not vendor the AMemGym code or replace the existing
metadata/source-backed overlay smoke. It owns the narrow boundary needed to
run an operator-provided official AMemGym checkout from a local ignored path,
then summarize official output files into public-safe Overall, UB, Random, and
normalized Memory scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
DEFAULT_UPSTREAM_ROOT = _paths.REPO_ROOT / ".tmp" / "amemgym-upstream"
DEFAULT_ENV_DATA_PATH = _paths.REPO_ROOT / "benchmark_corpus" / "amemgym" / "v1.base" / "data.json"
DEFAULT_OFFICIAL_OUTPUT_ROOT = _paths.REPO_ROOT / ".tmp" / "amemgym-official" / "v1.base"
DEFAULT_OVERALL_OUTPUT_DIR = DEFAULT_OFFICIAL_OUTPUT_ROOT / "overall"
DEFAULT_UPPERBOUND_OUTPUT_DIR = DEFAULT_OFFICIAL_OUTPUT_ROOT / "upperbound"
DEFAULT_RANDOM_OUTPUT_FILE = DEFAULT_OFFICIAL_OUTPUT_ROOT / "random_metrics.json"
DEFAULT_REPORT_OUTPUT = _paths.REPO_ROOT / "benchmark_corpus" / "reports" / "amemgym-official-summary.json"
DEFAULT_ADAPTER_OVERLAY_ROOT = DEFAULT_OFFICIAL_OUTPUT_ROOT / "adapter-overlays"
DEFAULT_METRIC = "accuracy"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "openai/gpt-4.1-mini"
OPENROUTER_KEY_ALIASES = ("Open_Router", "OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY", "OPENAI_API_KEY")

OFFICIAL_NATIVE_ARM = "official_native_full_history"
AIPPOCAMPUS_CLEAN_SOURCE_ARM = "aippocampus_clean_source_no_semantic_sidecar"
AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM = "aippocampus_semantic_sidecar"
OFFICIAL_ARM_ORDER = (
    OFFICIAL_NATIVE_ARM,
    AIPPOCAMPUS_CLEAN_SOURCE_ARM,
    AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM,
)
AIPPOCAMPUS_AGENT_TYPES = {
    AIPPOCAMPUS_CLEAN_SOURCE_ARM: "aippocampus-clean-source",
    AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM: "aippocampus-semantic-sidecar",
}

ENTRYPOINTS = {
    "overall": "amemgym.eval.overall",
    "upperbound": "amemgym.eval.upperbound",
    "random": "amemgym.eval.random",
}
REQUIRED_UPSTREAM_FILES = (
    "pyproject.toml",
    "src/amemgym/eval/overall.py",
    "src/amemgym/eval/upperbound.py",
    "src/amemgym/eval/random.py",
)


@dataclass(frozen=True)
class ProviderEnvironment:
    env_updates: dict[str, str]
    public_status: dict[str, Any]


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


def read_json(path: Path | str) -> dict[str, Any] | list[Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def safe_config_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    text = str(value)
    if not text:
        return ""
    if "/" in text or "\\" in text or ":" in text or len(text) > 120:
        return f"value_sha1:{sha1_short(text)}"
    return text


def external_env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if os.name != "nt":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except Exception:
        return None
    registry_locations = (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    )
    for root, key_path in registry_locations:
        try:
            with winreg.OpenKey(root, key_path) as key:
                candidate, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        if str(candidate).strip():
            return str(candidate)
    return None


def provider_environment(provider: str) -> ProviderEnvironment:
    if provider == "default":
        return ProviderEnvironment(
            env_updates={},
            public_status={
                "provider": "default",
                "credential_status": "left_to_process_env_or_dotenv",
                "base_url": "left_to_process_env_or_dotenv",
            },
        )
    if provider != "openrouter":
        raise ValueError(f"unknown provider: {provider}")
    credential_alias = None
    credential = None
    for alias in OPENROUTER_KEY_ALIASES:
        credential = external_env_value(alias)
        if credential:
            credential_alias = alias
            break
    env_updates = {"OPENAI_BASE_URL": OPENROUTER_BASE_URL}
    if credential:
        env_updates["OPENAI_API_KEY"] = credential
    return ProviderEnvironment(
        env_updates=env_updates,
        public_status={
            "provider": "openrouter",
            "credential_status": "set_redacted" if credential else "missing",
            "credential_alias": credential_alias,
            "base_url": "openrouter_default",
        },
    )


def model_name_slug(model: str | None) -> str:
    text = str(model or "model").strip() or "model"
    return re_safe_slug(text)


def re_safe_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def agent_name_for_arm(arm: str, model: str | None) -> str:
    if arm == OFFICIAL_NATIVE_ARM:
        return "native"
    suffix = {
        AIPPOCAMPUS_CLEAN_SOURCE_ARM: "aippocampus-clean-source",
        AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM: "aippocampus-semantic-sidecar",
    }.get(arm)
    if suffix is None:
        raise ValueError(f"unknown official AMemGym arm: {arm}")
    return f"{model_name_slug(model)}-{suffix}"


def aippocampus_agent_config(base_config: dict[str, Any], *, arm: str) -> dict[str, Any]:
    agent_type = AIPPOCAMPUS_AGENT_TYPES.get(arm)
    if agent_type is None:
        raise ValueError(f"not an AIppocampus AMemGym arm: {arm}")
    llm_config = dict(base_config.get("llm_config") if isinstance(base_config.get("llm_config"), dict) else {})
    mode = "semantic-sidecar" if arm == AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM else "clean-source"
    return {
        "type": agent_type,
        "name": agent_name_for_arm(arm, llm_config.get("llm_model")),
        "llm_config": llm_config,
        "agent_config": {
            "mode": mode,
            "top_k": 8,
            "local_length": 4,
            "build_clean_source": True,
            "build_source_index": True,
            "semantic_sidecar_required": arm == AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM,
            "source_format": "generic-jsonl",
        },
    }


def prepare_agent_config_for_provider(
    agent_config_path: Path | str,
    *,
    provider: str,
    openrouter_model: str = OPENROUTER_DEFAULT_MODEL,
    output_root: Path | str = DEFAULT_OFFICIAL_OUTPUT_ROOT,
    arm: str = OFFICIAL_NATIVE_ARM,
) -> Path:
    source = Path(agent_config_path)
    if provider != "openrouter" and arm == OFFICIAL_NATIVE_ARM:
        return source
    config = read_json(source)
    if not isinstance(config, dict):
        raise ValueError(f"{safe_path_label(source)} is not a JSON object")
    if arm != OFFICIAL_NATIVE_ARM:
        config = aippocampus_agent_config(config, arm=arm)
    llm_config = dict(config.get("llm_config") if isinstance(config.get("llm_config"), dict) else {})
    if provider == "openrouter":
        llm_config.update(
            {
                "llm_model": openrouter_model,
                "base_url": None,
                "api_key": None,
                "source": "agent:openrouter-official-bridge",
            }
        )
    elif arm != OFFICIAL_NATIVE_ARM:
        # The generated AIppocampus configs are local derivative artifacts.
        # Keep model/temperature/max_tokens for comparability, but do not copy
        # credentials or private base URLs into `.tmp`; the official factory
        # can still read OPENAI_API_KEY / OPENAI_BASE_URL from the environment.
        if llm_config.get("api_key") or llm_config.get("base_url"):
            llm_config["api_key"] = None
            llm_config["base_url"] = None
            llm_config.setdefault("source", "agent:aippocampus-official-bridge-env")
    config["llm_config"] = llm_config
    if arm == OFFICIAL_NATIVE_ARM:
        if provider == "openrouter":
            config["name"] = f"{config.get('name') or 'native'}-openrouter"
    else:
        config["name"] = agent_name_for_arm(arm, llm_config.get("llm_model"))
    suffix = "openrouter" if provider == "openrouter" else "default"
    output = Path(output_root) / "agent-configs" / f"{re_safe_slug(str(config.get('name') or source.stem))}-{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def public_agent_metadata(agent_config_path: Path | str) -> dict[str, Any]:
    path = Path(agent_config_path)
    if not path.exists():
        return {"status": "missing", "config_label": safe_path_label(path)}
    config = read_json(path)
    if not isinstance(config, dict):
        return {"status": "invalid", "config_label": safe_path_label(path)}
    llm_config = config.get("llm_config") if isinstance(config.get("llm_config"), dict) else {}
    return {
        "status": "loaded",
        "config_label": safe_path_label(path),
        "agent_name": safe_config_value(config.get("name")),
        "agent_type": safe_config_value(config.get("type")),
        "llm_model": safe_config_value(llm_config.get("llm_model")),
        "temperature": safe_config_value(llm_config.get("temperature")),
        "max_tokens": safe_config_value(llm_config.get("max_tokens")),
        "credential_status": "set_redacted" if llm_config.get("api_key") else "missing_or_env",
        "base_url_status": "set_redacted" if llm_config.get("base_url") else "missing_or_env",
    }


def public_env_metadata(env_config_path: Path | str) -> dict[str, Any]:
    path = Path(env_config_path)
    if not path.exists():
        return {"status": "missing", "config_label": safe_path_label(path)}
    config = read_json(path)
    if not isinstance(config, dict):
        return {"status": "invalid", "config_label": safe_path_label(path)}
    low_temp = config.get("llm_config_low_temp") if isinstance(config.get("llm_config_low_temp"), dict) else {}
    high_temp = config.get("llm_config_high_temp") if isinstance(config.get("llm_config_high_temp"), dict) else {}
    return {
        "status": "loaded",
        "config_label": safe_path_label(path),
        "seed": safe_config_value(config.get("seed")),
        "low_temp_model": safe_config_value(low_temp.get("llm_model")),
        "low_temp_temperature": safe_config_value(low_temp.get("temperature")),
        "high_temp_model": safe_config_value(high_temp.get("llm_model")),
        "high_temp_temperature": safe_config_value(high_temp.get("temperature")),
        "credentials": "redacted_or_env_only",
    }


def upstream_metadata(upstream_root: Path | str) -> dict[str, Any]:
    root = Path(upstream_root)
    missing = [rel for rel in REQUIRED_UPSTREAM_FILES if not (root / rel).exists()]
    commit = None
    git_dir = root / ".git"
    if git_dir.exists():
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            commit = completed.stdout.strip()
    return {
        "root_label": safe_path_label(root),
        "status": "ready" if not missing else "missing_required_files",
        "commit": commit,
        "required_files_present": not missing,
        "missing_required_files": missing,
        "python_requires": python_requires(root / "pyproject.toml"),
    }


def write_aippocampus_adapter_overlay(
    upstream_root: Path | str,
    *,
    output_root: Path | str = DEFAULT_ADAPTER_OVERLAY_ROOT,
) -> dict[str, Any]:
    """Create an ignored Python overlay that registers AIppocampus agents.

    AMemGym has no plugin registry; its factory is a regular ``match`` block in
    ``amemgym.assistants``. To keep the official checkout reproducible and
    avoid modifying upstream files, the runner writes a thin package overlay in
    `.tmp`. The overlay patches only the factory and extends ``__path__`` back
    to the operator-provided upstream checkout, so official eval modules,
    prompts, parsers, metrics, and built-in assistant classes still come from
    upstream.
    """

    root = Path(upstream_root)
    source_assistants = root / "src" / "amemgym" / "assistants"
    if not source_assistants.exists():
        return {
            "status": "missing_upstream_assistants",
            "pythonpath": None,
            "label": None,
        }
    overlay_src = Path(output_root) / "aippocampus" / "src"
    overlay_package = overlay_src / "amemgym"
    overlay_assistants = overlay_src / "amemgym" / "assistants"
    overlay_assistants.mkdir(parents=True, exist_ok=True)
    upstream_package_literal = json.dumps(str((root / "src" / "amemgym").resolve()))
    upstream_assistants_literal = json.dumps(str(source_assistants.resolve()))
    (overlay_package / "__init__.py").write_text(
        "from pathlib import Path\n\n"
        f"_UPSTREAM_PACKAGE = Path({upstream_package_literal})\n"
        "if _UPSTREAM_PACKAGE.exists():\n"
        "    __path__.insert(0, str(_UPSTREAM_PACKAGE))\n",
        encoding="utf-8",
    )
    (overlay_assistants / "aippocampus_agent.py").write_text(
        "from amemgym_aippocampus_adapter import AIppocampusAMemGymAgent\n\n"
        "AIppocampusOfficialAgent = AIppocampusAMemGymAgent\n",
        encoding="utf-8",
    )
    assistant_factory_overlay = """from pathlib import Path

_UPSTREAM_ASSISTANTS = Path(__UPSTREAM_ASSISTANTS_LITERAL__)
if _UPSTREAM_ASSISTANTS.exists():
    __path__.insert(0, str(_UPSTREAM_ASSISTANTS))

from .awi import InContextMemAgent
from .native import NaiveAgent
from .mem0 import Mem0Agent
from .evolvable import EvolvableInContextAgent, EvolvableMem0Agent
from .aippocampus_agent import AIppocampusOfficialAgent
import os

from dotenv import load_dotenv
load_dotenv()


def create_agent(agent_config, output_dir, item=None):
    # Keep provider injection identical to upstream AMemGym. The AIppocampus
    # arms must differ only in the memory substrate, not in model credentials,
    # temperature, max tokens, or answer prompt behavior.
    agent_config["llm_config"] |= {
        "base_url": agent_config["llm_config"].get("base_url") or os.environ.get("OPENAI_BASE_URL"),
        "api_key": agent_config["llm_config"].get("api_key") or os.environ.get("OPENAI_API_KEY")
    }

    match agent_config["type"]:
        case "native":
            return NaiveAgent(agent_config["llm_config"])
        case "awi":
            return InContextMemAgent(agent_config)
        case "awi-hack":
            assert item is not None, "the specific item is required for the hack setting"
            agent_config["info_types"] = list(item["state_schema"].keys())
            return InContextMemAgent(agent_config)
        case "awi-evolve":
            return EvolvableInContextAgent(agent_config)
        case "rag" | "awe":
            local_mem_dir = os.path.join(output_dir, "latest_memories")
            return Mem0Agent(agent_config | {"local_mem_dir": local_mem_dir})
        case "rag-evolve" | "mem0-evolution":
            local_mem_dir = os.path.join(output_dir, "latest_memories")
            return EvolvableMem0Agent(agent_config | {"local_mem_dir": local_mem_dir})
        case "aippocampus-clean-source" | "aippocampus-semantic-sidecar":
            local_mem_dir = os.path.join(output_dir, "latest_aippocampus")
            return AIppocampusOfficialAgent(agent_config | {"local_mem_dir": local_mem_dir})
        case _:
            raise ValueError(f"Unknown agent type: {agent_config['type']}")
""".replace("__UPSTREAM_ASSISTANTS_LITERAL__", upstream_assistants_literal)
    (overlay_assistants / "__init__.py").write_text(
        assistant_factory_overlay,
        encoding="utf-8",
    )
    return {
        "status": "ready",
        "pythonpath": str(overlay_src),
        "label": safe_path_label(overlay_src),
        "registration": {
            "agent_types": sorted(AIPPOCAMPUS_AGENT_TYPES.values()),
            "patched_surface": "amemgym.assistants.create_agent",
            "upstream_eval_modules_unmodified": True,
        },
    }


def adapter_runtime_for_arm(
    arm: str,
    *,
    upstream_root: Path | str,
    output_root: Path | str = DEFAULT_ADAPTER_OVERLAY_ROOT,
) -> dict[str, Any]:
    if arm == OFFICIAL_NATIVE_ARM:
        return {
            "status": "not_required",
            "pythonpath_entries": [],
            "metadata": {"official_factory_overlay": False},
        }
    overlay = write_aippocampus_adapter_overlay(upstream_root, output_root=output_root)
    entries = []
    if overlay.get("pythonpath"):
        entries.append(str(overlay["pythonpath"]))
    entries.extend([str(Path(__file__).resolve().parent), str(_paths.SKILL_SCRIPTS)])
    return {
        "status": overlay["status"],
        "pythonpath_entries": entries,
        "metadata": {
            "official_factory_overlay": overlay["status"] == "ready",
            "overlay_label": overlay.get("label"),
            "repo_adapter_module": "benchmarks/aippocampus/amemgym_aippocampus_adapter.py",
            "aippocampus_skill_scripts": "skills/aippocampus/scripts",
            "registration": overlay.get("registration"),
        },
    }


def python_requires(pyproject_path: Path) -> str | None:
    if not pyproject_path.exists():
        return None
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("requires-python"):
            return stripped.split("=", 1)[1].strip().strip('"')
    return None


def env_item_ids(env_data_path: Path | str) -> list[str]:
    payload = read_json(env_data_path)
    if not isinstance(payload, list):
        raise ValueError("AMemGym env data must be a JSON array")
    ids: list[str] = []
    for index, item in enumerate(payload, start=1):
        if isinstance(item, dict):
            ids.append(str(item.get("id") or f"row-{index}"))
        else:
            ids.append(f"row-{index}")
    return ids


def load_metric_matrix(path: Path | str, metric: str) -> Any:
    payload = read_json(path)
    if not isinstance(payload, dict) or metric not in payload:
        raise ValueError(f"{safe_path_label(path)} does not contain metric {metric!r}")
    return payload[metric]


def flatten_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        yield float(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from flatten_numbers(item)


def mean(value: Any) -> float | None:
    numbers = list(flatten_numbers(value))
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def matrix_shape(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    if not value:
        return [0]
    return [len(value), *matrix_shape(value[0])]


def resolve_child_metric_file(root: Path, file_name: str) -> Path | None:
    direct = root / file_name
    if direct.exists():
        return direct
    candidates = sorted(path for path in root.glob(f"*/{file_name}") if path.is_file())
    if not candidates:
        candidates = sorted(path for path in root.rglob(file_name) if path.is_file())
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_overall_agent_dir(
    root: Path,
    item_ids: list[str],
    *,
    agent_name: str | None = None,
) -> Path | None:
    if agent_name:
        named = root / agent_name
        if all((named / item_id / "overall_metrics.json").exists() for item_id in item_ids):
            return named
    if all((root / item_id / "overall_metrics.json").exists() for item_id in item_ids):
        return root
    candidates = []
    for child in sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []:
        if all((child / item_id / "overall_metrics.json").exists() for item_id in item_ids):
            candidates.append(child)
    if len(candidates) == 1:
        return candidates[0]
    return None


@dataclass
class ScoreFiles:
    overall_agent_dir: Path | None
    upperbound_metrics_path: Path | None
    random_metrics_path: Path | None


def discover_score_files(
    *,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    item_ids: list[str],
    overall_agent_name: str | None = None,
) -> ScoreFiles:
    return ScoreFiles(
        overall_agent_dir=resolve_overall_agent_dir(
            Path(overall_output_dir),
            item_ids,
            agent_name=overall_agent_name,
        ),
        upperbound_metrics_path=resolve_child_metric_file(Path(upperbound_output_dir), "utilization_metrics.json"),
        random_metrics_path=Path(random_output_file) if Path(random_output_file).exists() else None,
    )


def collect_overall_matrix(agent_dir: Path, item_ids: list[str], metric: str) -> list[Any]:
    matrices = []
    for item_id in item_ids:
        metrics_path = agent_dir / item_id / "overall_metrics.json"
        matrices.append(load_metric_matrix(metrics_path, metric))
    return matrices


def inspect_aippocampus_agent_states(agent_dir: Path | None) -> dict[str, Any]:
    if agent_dir is None:
        return {
            "status": "missing_overall_agent_dir",
            "period_state_count": 0,
            "adapter_metadata_count": 0,
            "surface_counts": {},
            "semantic_worker_state": "not_observed",
        }
    metadata_paths = sorted(agent_dir.glob("*/agent_states/period_*/adapter_metadata.json"))
    surface_counts: dict[str, dict[str, int]] = {}
    semantic_missing = 0
    semantic_prepared = 0
    clean_source_failures = 0
    source_index_failures = 0
    for path in metadata_paths:
        try:
            payload = read_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        status = payload.get("artifact_status") if isinstance(payload.get("artifact_status"), dict) else {}
        for key in (
            "clean_source",
            "source_index",
            "working_memory",
            "semantic_sidecar",
            "semantic_triggers",
            "semantic_cues",
            "semantic_worker_status",
        ):
            value = str(status.get(key) or "missing")
            surface_counts.setdefault(key, {})
            surface_counts[key][value] = surface_counts[key].get(value, 0) + 1
        if status.get("clean_source") != "built":
            clean_source_failures += 1
        if status.get("source_index") != "built":
            source_index_failures += 1
        worker_status = str(status.get("semantic_worker_status") or "")
        if worker_status == "prepared":
            semantic_prepared += 1
        elif worker_status == "missing_degraded_to_clean_source":
            semantic_missing += 1
    if not metadata_paths:
        semantic_state = "not_observed"
    elif semantic_prepared and not semantic_missing:
        semantic_state = "prepared"
    elif semantic_prepared:
        semantic_state = "partial"
    else:
        semantic_state = "missing_or_degraded"
    return {
        "status": "observed" if metadata_paths else "missing_adapter_metadata",
        "period_state_count": len(list(agent_dir.glob("*/agent_states/period_*"))) if agent_dir.exists() else 0,
        "adapter_metadata_count": len(metadata_paths),
        "surface_counts": surface_counts,
        "clean_source_failure_count": clean_source_failures,
        "source_index_failure_count": source_index_failures,
        "semantic_worker_state": semantic_state,
        "boundary": "Adapter state metadata is required before AIppocampus semantic-worker scores are claimable.",
    }


def normalized_memory_matrix(overall: Any, upperbound: Any, random: Any) -> tuple[Any, int, int, int]:
    zero_denominator_count = 0
    sample_count = 0
    below_random_count = 0

    def walk(o_value: Any, ub_value: Any, random_value: Any) -> Any:
        nonlocal zero_denominator_count, sample_count, below_random_count
        if isinstance(o_value, list) and isinstance(ub_value, list) and isinstance(random_value, list):
            return [walk(o_child, ub_child, random_child) for o_child, ub_child, random_child in zip(o_value, ub_value, random_value, strict=True)]
        if not all(isinstance(value, int | float) and not isinstance(value, bool) for value in (o_value, ub_value, random_value)):
            raise ValueError("score matrices must contain only numeric leaves")
        sample_count += 1
        if float(o_value) < float(random_value):
            below_random_count += 1
        denominator = float(ub_value) - float(random_value)
        if abs(denominator) < 1e-12:
            zero_denominator_count += 1
            return None
        return (float(o_value) - float(random_value)) / denominator

    return walk(overall, upperbound, random), zero_denominator_count, sample_count, below_random_count


def mean_by_period(matrix: list[Any]) -> list[float | None]:
    shape = matrix_shape(matrix)
    if len(shape) < 2:
        return []
    periods = shape[1]
    means: list[float | None] = []
    for period_index in range(periods):
        period_values = []
        for user_matrix in matrix:
            if isinstance(user_matrix, list) and period_index < len(user_matrix):
                period_values.append(user_matrix[period_index])
        means.append(mean(period_values))
    return means


def score_summary(
    *,
    env_data_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    metric: str = DEFAULT_METRIC,
    overall_agent_name: str | None = None,
) -> dict[str, Any]:
    ids = env_item_ids(env_data_path)
    files = discover_score_files(
        overall_output_dir=overall_output_dir,
        upperbound_output_dir=upperbound_output_dir,
        random_output_file=random_output_file,
        item_ids=ids,
        overall_agent_name=overall_agent_name,
    )
    outputs = {
        "overall": {
            "status": "found" if files.overall_agent_dir else "missing",
            "label": safe_path_label(files.overall_agent_dir) if files.overall_agent_dir else None,
        },
        "upperbound": {
            "status": "found" if files.upperbound_metrics_path else "missing",
            "label": safe_path_label(files.upperbound_metrics_path) if files.upperbound_metrics_path else None,
        },
        "random": {
            "status": "found" if files.random_metrics_path else "missing",
            "label": safe_path_label(files.random_metrics_path) if files.random_metrics_path else None,
        },
    }
    metrics: dict[str, Any] = {
        "official_expected_user_count": len(ids),
    }
    shapes: dict[str, Any] = {}
    interpretation: dict[str, Any] = {
        "normalized_memory_formula": "(overall - random) / (upperbound - random)",
        "notes": [],
    }

    overall_matrix = None
    if files.overall_agent_dir:
        overall_matrix = collect_overall_matrix(files.overall_agent_dir, ids, metric)
        metrics["official_overall"] = mean(overall_matrix)
        shapes["overall"] = matrix_shape(overall_matrix)
        metrics["official_overall_by_period"] = mean_by_period(overall_matrix)

    upperbound_matrix = None
    if files.upperbound_metrics_path:
        upperbound_matrix = load_metric_matrix(files.upperbound_metrics_path, metric)
        metrics["official_upperbound"] = mean(upperbound_matrix)
        shapes["upperbound"] = matrix_shape(upperbound_matrix)
        metrics["official_upperbound_by_period"] = mean_by_period(upperbound_matrix)

    random_matrix = None
    if files.random_metrics_path:
        random_matrix = load_metric_matrix(files.random_metrics_path, metric)
        metrics["official_random"] = mean(random_matrix)
        shapes["random"] = matrix_shape(random_matrix)
        metrics["official_random_by_period"] = mean_by_period(random_matrix)

    if overall_matrix is not None and upperbound_matrix is not None and random_matrix is not None:
        memory_matrix, zero_denominator_count, sample_count, below_random_count = normalized_memory_matrix(
            overall_matrix,
            upperbound_matrix,
            random_matrix,
        )
        metrics["official_normalized_memory_score"] = mean(memory_matrix)
        metrics["official_normalized_memory_score_by_period"] = mean_by_period(memory_matrix)
        metrics["memory_score_denominator_zero_count"] = zero_denominator_count
        metrics["score_sample_count"] = sample_count
        metrics["below_random_sample_count"] = below_random_count
        interpretation["normalized_memory_score_negative"] = below_random_count > 0
        if below_random_count:
            interpretation["notes"].append(
                "overall_below_random: normalized memory can be negative when official overall accuracy falls below the random baseline."
            )
        shapes["normalized_memory"] = matrix_shape(memory_matrix)

    missing = [name for name, payload in outputs.items() if payload["status"] != "found"]
    return {
        "item_count": len(ids),
        "metric": metric,
        "outputs": outputs,
        "missing_outputs": missing,
        "aippocampus_agent_state": inspect_aippocampus_agent_states(files.overall_agent_dir),
        "metrics": {key: value for key, value in metrics.items() if value is not None},
        "metric_shapes": shapes,
        "score_interpretation": interpretation,
    }


def command_argv(
    surface: str,
    *,
    env_data_path: Path | str,
    env_config_path: Path | str,
    agent_config_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    runner: str = "python",
    reset: bool = False,
) -> list[str]:
    command_prefix = [sys.executable, "-m"] if runner == "python" else ["uv", "run", "python", "-m"]
    if surface == "overall":
        command = [
            *command_prefix,
            ENTRYPOINTS[surface],
            "--agent_config",
            str(agent_config_path),
            "--env_data",
            str(env_data_path),
            "--env_config",
            str(env_config_path),
            "--output_dir",
            str(overall_output_dir),
        ]
        if reset:
            command.append("--reset")
        return command
    if surface == "upperbound":
        return [
            *command_prefix,
            ENTRYPOINTS[surface],
            "--agent_config",
            str(agent_config_path),
            "--env_data",
            str(env_data_path),
            "--output_dir",
            str(upperbound_output_dir),
        ]
    if surface == "random":
        return [
            *command_prefix,
            ENTRYPOINTS[surface],
            "--env_data",
            str(env_data_path),
            "--output_file",
            str(random_output_file),
        ]
    raise ValueError(f"unknown AMemGym surface: {surface}")


def safe_command_plan(
    *,
    upstream_root: Path | str,
    env_data_path: Path | str,
    env_config_path: Path | str,
    agent_config_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    runner: str = "python",
    arm: str = OFFICIAL_NATIVE_ARM,
) -> dict[str, Any]:
    pythonpath_add = [safe_path_label(Path(upstream_root) / "src")]
    if arm != OFFICIAL_NATIVE_ARM:
        pythonpath_add = [
            safe_path_label(DEFAULT_ADAPTER_OVERLAY_ROOT / "aippocampus" / "src"),
            "benchmarks/aippocampus",
            "skills/aippocampus/scripts",
            *pythonpath_add,
        ]
    return {
        "upstream_install": [
            "git clone https://github.com/AGI-Eval-Official/amemgym.git .tmp/amemgym-upstream",
            "cd .tmp/amemgym-upstream",
            "uv sync",
        ],
        "entrypoints": list(ENTRYPOINTS.values()),
        "working_directory": safe_path_label(upstream_root),
        "environment": {
            "pythonpath_add": pythonpath_add,
            "provider_credential": "OPENAI_API_KEY required for overall and upperbound; never written to reports",
            "provider_base_url": "OPENAI_BASE_URL optional; redacted from reports",
        },
        "arm": {
            "selected": arm,
            "official_factory_overlay_required": arm != OFFICIAL_NATIVE_ARM,
        },
        "commands": {
            surface: public_command_argv(
                surface,
                env_data_path=env_data_path,
                env_config_path=env_config_path,
                agent_config_path=agent_config_path,
                overall_output_dir=overall_output_dir,
                upperbound_output_dir=upperbound_output_dir,
                random_output_file=random_output_file,
                runner=runner,
            )
            for surface in ("overall", "upperbound", "random")
        },
    }


def public_command_argv(
    surface: str,
    *,
    env_data_path: Path | str,
    env_config_path: Path | str,
    agent_config_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    runner: str = "python",
) -> list[str]:
    argv = command_argv(
        surface,
        env_data_path=safe_path_label(env_data_path),
        env_config_path=safe_path_label(env_config_path),
        agent_config_path=safe_path_label(agent_config_path),
        overall_output_dir=safe_path_label(overall_output_dir),
        upperbound_output_dir=safe_path_label(upperbound_output_dir),
        random_output_file=safe_path_label(random_output_file),
        runner=runner,
    )
    # Reports should be copyable as a shape reference, but not expose the local
    # interpreter install path. The real runner still uses sys.executable.
    if runner == "python":
        argv[0] = "python"
    return argv


def run_official_surface(
    surface: str,
    *,
    upstream_root: Path | str,
    env_data_path: Path | str,
    env_config_path: Path | str,
    agent_config_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    runner: str = "python",
    provider: str = "default",
    reset: bool = False,
    pythonpath_entries: Iterable[Path | str] = (),
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(upstream_root)
    env = os.environ.copy()
    provider_env = provider_environment(provider)
    env.update(provider_env.env_updates)
    pythonpath = [str(Path(entry)) for entry in pythonpath_entries]
    pythonpath.append(str(root / "src"))
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    if surface == "random":
        Path(random_output_file).parent.mkdir(parents=True, exist_ok=True)
    if surface == "overall":
        Path(overall_output_dir).mkdir(parents=True, exist_ok=True)
    if surface == "upperbound":
        Path(upperbound_output_dir).mkdir(parents=True, exist_ok=True)
    command = command_argv(
        surface,
        env_data_path=Path(env_data_path).resolve(),
        env_config_path=Path(env_config_path).resolve(),
        agent_config_path=Path(agent_config_path).resolve(),
        overall_output_dir=Path(overall_output_dir).resolve(),
        upperbound_output_dir=Path(upperbound_output_dir).resolve(),
        random_output_file=Path(random_output_file).resolve(),
        runner=runner,
        reset=reset,
    )
    completed = subprocess.run(
        command,
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return {
        "surface": surface,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_sha1": sha1_short(stdout) if stdout else None,
        "stderr_sha1": sha1_short(stderr) if stderr else None,
        "stdout_line_count": len(stdout.splitlines()),
        "stderr_line_count": len(stderr.splitlines()),
        "provider": provider_env.public_status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def aippocampus_official_adapter_protocol() -> dict[str, Any]:
    return {
        "host": "official_amemgym_overall_runner",
        "why_base_agent_is_not_enough": (
            "A BaseAgent wrapper that only writes messages and searches files is "
            "a clean-source retrieval baseline, not the full AIppocampus memory system."
        ),
        "lifecycle_surrogates": [
            {
                "aippocampus_phase": "host_visible_message_capture",
                "official_runner_surface": "BaseAgent.act/add_msgs",
                "purpose": "record AMemGym user/assistant visible turns without reading gold state",
            },
            {
                "aippocampus_phase": "lifecycle_refresh",
                "official_runner_surface": "BaseAgent.save_state at each period checkpoint",
                "purpose": "build generic-jsonl, clean source, and source index before scoring",
            },
            {
                "aippocampus_phase": "background_worker_precache",
                "official_runner_surface": "adapter pre-score preparation inside the ignored agent state directory",
                "purpose": (
                    "materialize route cache, working-memory, semantic triggers, or semantic "
                    "sidecars before answer_question; cold worker cost is reported separately"
                ),
            },
            {
                "aippocampus_phase": "foreground_recall",
                "official_runner_surface": "BaseAgent.answer_question",
                "purpose": "consume prepared artifacts, reopen clean-source snippets, and ask the same llm_config model",
            },
        ],
        "arms": {
            OFFICIAL_NATIVE_ARM: {
                "official_comparable": True,
                "memory_surface": "full AMemGym msg_history in model context",
            },
            AIPPOCAMPUS_CLEAN_SOURCE_ARM: {
                "official_comparable": True,
                "memory_surface": "generic-jsonl -> clean-source exact/source-index retrieval",
                "claim_level": "file_retrieval_baseline",
                "not_full_aippocampus": True,
            },
            AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM: {
                "official_comparable": True,
                "memory_surface": "prepared clean source plus working-memory/semantic sidecar navigation with source reopen",
                "claim_level": "full_arm_only_when_precache_artifacts_are_present",
                "missing_worker_degrades_to": AIPPOCAMPUS_CLEAN_SOURCE_ARM,
            },
        },
        "must_preserve_for_score_comparability": [
            "same AMemGym overall prompt, parser, answer choices, random fallback, and metric code",
            "same llm_config model, temperature, max_tokens, provider base URL, and credential injection shape",
            "answer_question must not mutate memory state",
            "adapter must not read period state, answer_choice state, required_info gold labels, or real user memory",
            "each AMemGym item and period uses only its own ignored local agent state",
        ],
        "precache_claim_gate": {
            "clean_source_only_required": ["transcript.jsonl", "clean-source/messages.jsonl", "source-index/source_index.sqlite"],
            "semantic_sidecar_required": [
                "clean-source/messages.jsonl",
                "source-index/source_index.sqlite",
                "working_memory.jsonl or semantic-scope-labels.jsonl or semantic_triggers.jsonl",
            ],
            "cold_start_cost": "reported separately from warmed answer quality",
        },
    }


def build_official_bridge_report(
    *,
    upstream_root: Path | str = DEFAULT_UPSTREAM_ROOT,
    env_data_path: Path | str = DEFAULT_ENV_DATA_PATH,
    env_config_path: Path | str | None = None,
    agent_config_path: Path | str | None = None,
    overall_output_dir: Path | str = DEFAULT_OVERALL_OUTPUT_DIR,
    upperbound_output_dir: Path | str = DEFAULT_UPPERBOUND_OUTPUT_DIR,
    random_output_file: Path | str = DEFAULT_RANDOM_OUTPUT_FILE,
    metric: str = DEFAULT_METRIC,
    run_surfaces: tuple[str, ...] = (),
    runner: str = "python",
    provider: str = "default",
    openrouter_model: str = OPENROUTER_DEFAULT_MODEL,
    reset: bool = False,
    arm: str = OFFICIAL_NATIVE_ARM,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(upstream_root)
    env_config = Path(env_config_path) if env_config_path else root / "configs" / "env" / "v1.base.json"
    source_agent_config = Path(agent_config_path) if agent_config_path else root / "configs" / "agent" / "native.json"
    agent_config = prepare_agent_config_for_provider(
        source_agent_config,
        provider=provider,
        openrouter_model=openrouter_model,
        output_root=DEFAULT_OFFICIAL_OUTPUT_ROOT,
        arm=arm,
    )
    provider_env = provider_environment(provider)
    upstream = upstream_metadata(root)
    adapter_runtime = adapter_runtime_for_arm(
        arm,
        upstream_root=root,
        output_root=DEFAULT_ADAPTER_OVERLAY_ROOT,
    )
    agent_public = public_agent_metadata(agent_config)
    expected_overall_agent_name = str(agent_public.get("agent_name") or "").strip() or None
    run_results = []
    adapter_ready = adapter_runtime["status"] in {"not_required", "ready"}
    if upstream["status"] == "ready" and adapter_ready:
        for surface in run_surfaces:
            run_results.append(
                run_official_surface(
                    surface,
                    upstream_root=root,
                    env_data_path=env_data_path,
                    env_config_path=env_config,
                    agent_config_path=agent_config,
                    overall_output_dir=overall_output_dir,
                    upperbound_output_dir=upperbound_output_dir,
                    random_output_file=random_output_file,
                    runner=runner,
                    provider=provider,
                    reset=reset,
                    pythonpath_entries=adapter_runtime["pythonpath_entries"],
                )
            )

    score_payload: dict[str, Any]
    try:
        score_payload = score_summary(
            env_data_path=env_data_path,
            overall_output_dir=overall_output_dir,
            upperbound_output_dir=upperbound_output_dir,
            random_output_file=random_output_file,
            metric=metric,
            overall_agent_name=expected_overall_agent_name,
        )
        score_error = None
    except Exception as exc:
        score_payload = {
            "item_count": 0,
            "metric": metric,
            "outputs": {},
            "missing_outputs": ["score_summary_error"],
            "aippocampus_agent_state": inspect_aippocampus_agent_states(None),
            "metrics": {},
            "metric_shapes": {},
            "score_interpretation": {
                "normalized_memory_formula": "(overall - random) / (upperbound - random)",
                "notes": ["score_summary_error"],
            },
        }
        score_error = type(exc).__name__

    missing_outputs = list(score_payload["missing_outputs"])
    all_scores_present = not missing_outputs and "official_normalized_memory_score" in score_payload["metrics"]
    if upstream["status"] != "ready":
        status = "upstream_missing"
    elif not adapter_ready:
        status = "adapter_overlay_missing"
    elif all_scores_present:
        status = "official_score_summary"
    elif run_results:
        status = "partial_official_outputs"
    else:
        status = "runner_plan_ready_missing_outputs"

    cannot_claim = []
    if "overall" in missing_outputs:
        cannot_claim.append("official_overall_missing")
    if "upperbound" in missing_outputs:
        cannot_claim.append("official_upperbound_missing")
    if "random" in missing_outputs:
        cannot_claim.append("official_random_missing")
    if missing_outputs:
        cannot_claim.append("official_normalized_memory_score_missing")
    if not run_results and not all_scores_present:
        cannot_claim.append("local_official_runner_execution")
    if arm != OFFICIAL_NATIVE_ARM and not adapter_ready:
        cannot_claim.append("official_aippocampus_agent_adapter_execution")
    if arm == AIPPOCAMPUS_CLEAN_SOURCE_ARM:
        cannot_claim.append("aippocampus_full_semantic_worker_capability")
    if arm == AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM:
        state = score_payload.get("aippocampus_agent_state") or {}
        if state.get("semantic_worker_state") != "prepared":
            cannot_claim.append("semantic_worker_materialization_unless_agent_state_sidecars_are_present")
    cannot_claim.extend(
        [
            "source_backed_overlay_is_official_accuracy",
            "leaderboard_parity_or_sota",
            "Native_RAG_AWI_AWE_parity_unless_each_arm_is_run",
        ]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_amemgym_official_runner_bridge",
        "generated_at": now_utc(),
        "status": status,
        "ok": upstream["status"] == "ready",
        "upstream": upstream,
        "configuration": {
            "arm": arm,
            "available_arms": list(OFFICIAL_ARM_ORDER),
            "env_data_label": safe_path_label(env_data_path),
            "env_config_label": safe_path_label(env_config),
            "agent_config_label": safe_path_label(agent_config),
            "expected_overall_agent_name": expected_overall_agent_name,
            "overall_output_label": safe_path_label(overall_output_dir),
            "upperbound_output_label": safe_path_label(upperbound_output_dir),
            "random_output_label": safe_path_label(random_output_file),
            "metric": metric,
            "run_surfaces": list(run_surfaces),
            "runner": runner,
            "provider": provider,
            "reset": reset,
        },
        "runner_plan": safe_command_plan(
            upstream_root=root,
            env_data_path=env_data_path,
            env_config_path=env_config,
            agent_config_path=agent_config,
            overall_output_dir=overall_output_dir,
            upperbound_output_dir=upperbound_output_dir,
            random_output_file=random_output_file,
            runner=runner,
            arm=arm,
        ),
        "provider": provider_env.public_status,
        "agent": agent_public,
        "aippocampus_official_adapter_protocol": aippocampus_official_adapter_protocol(),
        "aippocampus_agent_adapter": {
            "requested": arm != OFFICIAL_NATIVE_ARM,
            "status": adapter_runtime["status"],
            **adapter_runtime["metadata"],
        },
        "environment_config": public_env_metadata(env_config),
        "official_outputs": score_payload["outputs"],
        "aippocampus_agent_state": score_payload.get("aippocampus_agent_state"),
        "metrics": score_payload["metrics"],
        "metric_shapes": score_payload["metric_shapes"],
        "score_interpretation": score_payload.get("score_interpretation", {}),
        "run_results": run_results,
        "score_summary_error_type": score_error,
        "claim_boundary": {
            "official_amemgym_score": "official_output_summary" if all_scores_present else "not_claimed",
            "official_runner_compatibility": "local_upstream_entrypoints_verified" if run_results else "planned_not_executed",
            "official_agent_adapter": "registered_overlay" if arm != OFFICIAL_NATIVE_ARM and adapter_ready else "not_required" if arm == OFFICIAL_NATIVE_ARM else "not_claimed",
            "aippocampus_memory_layer": (
                "clean_source_only_file_retrieval_baseline"
                if arm == AIPPOCAMPUS_CLEAN_SOURCE_ARM
                else "prepared_semantic_worker_required"
                if arm == AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM
                else "not_applicable"
            ),
            "source_backed_overlay": "separate_not_merged",
            "diagnosis": "not_run_by_this_summary",
            "cost_latency": "process_elapsed_only_unless_provider_run_metadata_is_recorded",
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
            "provider_credentials_emitted": False,
            "raw_official_outputs_committed": False,
            "default_report_shape": "scores_shapes_hashes_and_redacted_config_only",
        },
        "local_artifact_policy": {
            "upstream_checkout": ".tmp/amemgym-upstream",
            "generated_outputs": ".tmp/amemgym-official/ or benchmark_corpus/reports/",
            "git_policy": "do not commit raw AMemGym rows, model outputs, API keys, or absolute local paths",
        },
        "cannot_claim": cannot_claim,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus AMemGym official runner bridge")
    print(f"- status: {payload['status']}")
    print(f"- upstream: {payload['upstream']['status']}")
    metrics = payload.get("metrics", {})
    for key in (
        "official_overall",
        "official_upperbound",
        "official_random",
        "official_normalized_memory_score",
    ):
        if key in metrics:
            print(f"- {key}: {metrics[key]}")
    print("- cannot claim:")
    for item in payload["cannot_claim"]:
        print(f"  - {item}")


def parse_run_surfaces(values: list[str]) -> tuple[str, ...]:
    surfaces: list[str] = []
    for value in values:
        for item in value.split(","):
            surface = item.strip()
            if not surface:
                continue
            if surface not in ENTRYPOINTS:
                raise argparse.ArgumentTypeError(f"unknown AMemGym surface: {surface}")
            surfaces.append(surface)
    return tuple(dict.fromkeys(surfaces))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-root", type=Path, default=DEFAULT_UPSTREAM_ROOT)
    parser.add_argument("--env-data", type=Path, default=DEFAULT_ENV_DATA_PATH)
    parser.add_argument("--env-config", type=Path)
    parser.add_argument("--agent-config", type=Path)
    parser.add_argument("--overall-output-dir", type=Path, default=DEFAULT_OVERALL_OUTPUT_DIR)
    parser.add_argument("--upperbound-output-dir", type=Path, default=DEFAULT_UPPERBOUND_OUTPUT_DIR)
    parser.add_argument("--random-output-file", type=Path, default=DEFAULT_RANDOM_OUTPUT_FILE)
    parser.add_argument("--metric", default=DEFAULT_METRIC)
    parser.add_argument(
        "--runner",
        choices=("python", "uv"),
        default="python",
        help="Use the current Python interpreter or the upstream uv environment for official surfaces.",
    )
    parser.add_argument(
        "--provider",
        choices=("default", "openrouter"),
        default="default",
        help="Provider env adapter. openrouter maps Open_Router into OPENAI_API_KEY for the official runner.",
    )
    parser.add_argument(
        "--arm",
        choices=OFFICIAL_ARM_ORDER,
        default=OFFICIAL_NATIVE_ARM,
        help="Official AMemGym agent arm to run or summarize.",
    )
    parser.add_argument(
        "--openrouter-model",
        default=OPENROUTER_DEFAULT_MODEL,
        help="OpenRouter model id for the generated local agent config.",
    )
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        metavar="SURFACE[,SURFACE]",
        help="Run official surfaces before summarizing. Supported: overall, upperbound, random.",
    )
    parser.add_argument("--reset", action="store_true", help="Pass --reset to official overall runs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_surfaces = parse_run_surfaces(args.run)
    payload = build_official_bridge_report(
        upstream_root=args.upstream_root,
        env_data_path=args.env_data,
        env_config_path=args.env_config,
        agent_config_path=args.agent_config,
        overall_output_dir=args.overall_output_dir,
        upperbound_output_dir=args.upperbound_output_dir,
        random_output_file=args.random_output_file,
        metric=args.metric,
        run_surfaces=run_surfaces,
        runner=args.runner,
        provider=args.provider,
        openrouter_model=args.openrouter_model,
        reset=args.reset,
        arm=args.arm,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
