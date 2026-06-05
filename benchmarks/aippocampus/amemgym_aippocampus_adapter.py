#!/usr/bin/env python3
"""AIppocampus agent adapter for the official AMemGym runner.

The official AMemGym ``overall`` evaluator owns the state evolution, simulated
conversations, answer-choice prompts, parsing, and scoring. This module only
implements the AMemGym ``BaseAgent`` surface so AIppocampus can be measured as
an agent arm without rewriting AMemGym's metrics.

The adapter deliberately uses the public provider-neutral AIppocampus path:
visible AMemGym messages are exported as generic JSONL, then rebuilt into clean
source and a source index. That keeps the benchmark source-backed and avoids a
private, one-off RAG implementation that would be hard for other operators to
reproduce.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised through an upstream AMemGym subprocess.
    from amemgym.assistants.base import BaseAgent
    from amemgym.utils import call_llm, load_json, save_json
except Exception:  # pragma: no cover - lets repo-side tests import helpers.
    class BaseAgent:  # type: ignore[no-redef]
        pass

    def call_llm(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("AMemGym call_llm is available only inside the official runner")

    def load_json(path: str | os.PathLike[str]) -> Any:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def save_json(path: str | os.PathLike[str], data: Any) -> None:
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


GENERIC_PROVIDER_LABEL = "amemgym-official-aippocampus-adapter"
DEFAULT_TOP_K = 8
DEFAULT_LOCAL_LENGTH = 4
DEFAULT_SNIPPET_CHARS = 900
WORKING_MEMORY_FILENAME = "working_memory.jsonl"
SEMANTIC_TRIGGERS_FILENAME = "semantic_triggers.jsonl"
SEMANTIC_CUES_FILENAME = "semantic_cues.jsonl"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


class AIppocampusAMemGymAgent(BaseAgent):
    """AMemGym BaseAgent backed by AIppocampus clean source.

    ``act`` is intentionally ordinary assistant behavior plus a small local
    tail, while durable memory is rebuilt from visible messages at AMemGym
    period checkpoints. ``answer_question`` does not mutate the memory state,
    matching the official Native/RAG/AWI contract.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config)
        self.llm_config = dict(self.config.get("llm_config") or {})
        self.agent_config = dict(self.config.get("agent_config") or {})
        self.mode = str(self.agent_config.get("mode") or "clean-source")
        self.top_k = _safe_int(self.agent_config.get("top_k"), DEFAULT_TOP_K)
        self.local_length = _safe_int(
            self.agent_config.get("local_length"),
            DEFAULT_LOCAL_LENGTH,
        )
        self.snippet_chars = _safe_int(
            self.agent_config.get("snippet_chars"),
            DEFAULT_SNIPPET_CHARS,
        )
        self.rebuild_index = self.agent_config.get("build_source_index", True) is not False
        self.semantic_sidecar_required = self.mode == "semantic-sidecar"
        self.local_mem_dir = Path(
            self.config.get("local_mem_dir")
            or tempfile.mkdtemp(prefix="amemgym-aippocampus-")
        )
        self.reset()

    def reset(self) -> None:
        self.msg_history: list[dict[str, str]] = []
        self.local_msgs: list[dict[str, str]] = []
        self.last_artifact_status: dict[str, Any] = {}
        self._artifacts_dirty = True

    @property
    def transcript_path(self) -> Path:
        return self.local_mem_dir / "transcript.jsonl"

    @property
    def clean_source_dir(self) -> Path:
        return self.local_mem_dir / "clean-source"

    @property
    def index_dir(self) -> Path:
        return self.local_mem_dir / "source-index"

    @property
    def metadata_path(self) -> Path:
        return self.local_mem_dir / "adapter_metadata.json"

    @property
    def working_memory_path(self) -> Path:
        return self.local_mem_dir / WORKING_MEMORY_FILENAME

    def act(self, obs: str) -> str:
        new_msg = {"role": "user", "content": obs}
        memory_context = self._memory_context(obs)
        messages = self._prompt_messages(memory_context, [*self.local_msgs, new_msg])
        response = call_llm(messages, self.llm_config)
        self.add_msgs([new_msg, {"role": "assistant", "content": response}])
        return response

    def add_msgs(self, msgs: list[dict[str, str]]) -> None:
        if not msgs:
            return
        for msg in msgs:
            role = str(msg.get("role") or "")
            content = str(msg.get("content") or "")
            if role not in {"user", "assistant"} or not content:
                continue
            clean_msg = {"role": role, "content": content}
            self.msg_history.append(clean_msg)
            self.local_msgs.append(clean_msg)
        if self.local_length:
            self.local_msgs = self.local_msgs[-self.local_length :]
        else:
            self.local_msgs = []
        self._artifacts_dirty = True

    def load_state(self, local_dir: str) -> None:
        source = Path(local_dir)
        self.local_mem_dir.mkdir(parents=True, exist_ok=True)
        if self.local_mem_dir.exists():
            shutil.rmtree(self.local_mem_dir)
        shutil.copytree(source, self.local_mem_dir)
        self.msg_history = load_json(str(self.local_mem_dir / "msg_history.json"))
        self.local_msgs = self.msg_history[-self.local_length :] if self.local_length else []
        metadata = self._read_metadata()
        self.last_artifact_status = dict(metadata.get("artifact_status") or {})
        self._artifacts_dirty = False

    def save_state(self, local_dir: str) -> None:
        target = Path(local_dir)
        self._prepare_memory_artifacts()
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(self.local_mem_dir, target)

    def answer_question(self, question: str) -> tuple[str, dict[str, Any]]:
        self._prepare_memory_artifacts()
        memory_context = self._memory_context(question)
        messages = self._prompt_messages(memory_context, [*self.local_msgs, {"role": "user", "content": question}])
        return call_llm(messages, self.llm_config, return_token_usage=True)

    def _prompt_messages(
        self,
        memory_context: str,
        conversation_tail: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        system_prompt = (
            "You are a helpful AI assistant evaluated by AMemGym. Use the "
            "source-backed AIppocampus snippets below when they are relevant "
            "to the user's current preferences or state. If snippets conflict, "
            "prefer later source lines. Semantic sidecars are navigation hints; "
            "clean-source snippets are the evidence.\n\n"
            f"{memory_context or 'AIppocampus snippets: none found.'}"
        )
        return [{"role": "system", "content": system_prompt}, *conversation_tail]

    def _memory_context(self, query: str) -> str:
        if not self.msg_history:
            return ""
        self._prepare_memory_artifacts()
        contexts = [self._working_memory_context(query), self._clean_source_context(query)]
        return "\n\n".join(context for context in contexts if context)

    def _working_memory_context(self, query: str) -> str:
        if not self.working_memory_path.exists():
            return ""
        try:
            from aippocampus_runtime.subconscious.candidate_router import (
                load_working_memory,
                match_working_memory,
            )
        except Exception as exc:
            self.last_artifact_status["working_memory_error"] = type(exc).__name__
            return ""
        rows = load_working_memory(self.working_memory_path)
        matches = match_working_memory(query, rows, limit=min(self.top_k, 4))
        if not matches:
            return ""
        lines = [
            "AIppocampus prepared working-memory sidecar matches "
            "(navigation; reopen clean source before treating as fact):"
        ]
        for index, match in enumerate(matches, start=1):
            title = str(match.get("title") or "working memory")
            summary = str(match.get("summary") or "")
            route = str(match.get("route") or "")
            lines.append(f"{index}. title={title}; route={route}; summary={summary}")
        return "\n".join(lines)

    def _clean_source_context(self, query: str) -> str:
        if not (self.clean_source_dir / "messages.jsonl").exists():
            return ""
        try:
            from aippocampus_runtime.source.search import search_clean_source
        except Exception as exc:
            self.last_artifact_status["search_error"] = type(exc).__name__
            return ""
        result = search_clean_source(
            self.local_mem_dir,
            [query],
            clean_source_dir=self.clean_source_dir,
            limit=self.top_k,
            snippet_chars=self.snippet_chars,
        )
        matches = list(result.get("matches") or [])
        if not matches:
            return ""
        lines = ["AIppocampus source-backed snippets:"]
        for index, match in enumerate(matches, start=1):
            source_ref = match.get("source_ref") or match.get("message_id") or "clean-source"
            role = match.get("role") or "unknown"
            turn = match.get("turn_index") or match.get("turn_id") or "unknown"
            snippet = str(match.get("snippet") or "")
            lines.append(
                f"{index}. source={source_ref}; role={role}; turn={turn}; text={snippet}"
            )
        return "\n".join(lines)

    def _prepare_memory_artifacts(self) -> None:
        if not self._artifacts_dirty and (self.clean_source_dir / "messages.jsonl").exists():
            return
        self.local_mem_dir.mkdir(parents=True, exist_ok=True)
        save_json(str(self.local_mem_dir / "msg_history.json"), self.msg_history)
        self._write_generic_transcript()
        artifact_status = self._build_clean_source_and_index()
        self.last_artifact_status = artifact_status
        self._write_metadata(artifact_status)
        self._artifacts_dirty = False

    def _write_generic_transcript(self) -> None:
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        current_turn = 0
        for line_no, msg in enumerate(self.msg_history, start=1):
            role = msg["role"]
            if role == "user":
                current_turn += 1
            turn_id = f"turn-{current_turn or 1:04d}"
            rows.append(
                {
                    "session_id": "amemgym-official-agent",
                    "timestamp": None,
                    "cwd": str(self.local_mem_dir),
                    "role": role,
                    "turn_id": turn_id,
                    "phase": "final_answer" if role == "assistant" else "",
                    "text": msg["content"],
                    "provider_metadata": {
                        "provider": GENERIC_PROVIDER_LABEL,
                        "mode": self.mode,
                    },
                }
            )
        with self.transcript_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _build_clean_source_and_index(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "mode": self.mode,
            "message_count": len(self.msg_history),
            "clean_source": "not_built",
            "source_index": "not_built",
            "semantic_sidecar": "not_required" if not self.semantic_sidecar_required else "missing",
            "working_memory": "present" if self.working_memory_path.exists() else "missing",
            "semantic_triggers": "present"
            if (self.local_mem_dir / SEMANTIC_TRIGGERS_FILENAME).exists()
            else "missing",
            "semantic_cues": "present"
            if (self.local_mem_dir / SEMANTIC_CUES_FILENAME).exists()
            else "missing",
            "built_at": _now_utc(),
        }
        try:
            from aippocampus_runtime.source.clean_source import build_clean_source

            manifest = build_clean_source(
                self.local_mem_dir,
                rollout=self.transcript_path,
                output_dir=self.clean_source_dir,
                provider_name="generic-jsonl",
                redaction_profiles=["raw-private"],
            )
            status["clean_source"] = "built"
            status["clean_source_message_count"] = manifest.get("message_count")
        except Exception as exc:
            status["clean_source"] = "failed"
            status["clean_source_error"] = type(exc).__name__

        if self.rebuild_index:
            try:
                from aippocampus_runtime.recall import index_builder

                code = index_builder.main(
                    [
                        "--cwd",
                        str(self.local_mem_dir),
                        "--provider",
                        "generic-jsonl",
                        "--rollout",
                        str(self.transcript_path),
                        "--output-dir",
                        str(self.index_dir),
                        "--no-rag-cache",
                    ]
                )
                status["source_index"] = "built" if code == 0 else f"failed_exit_{code}"
            except Exception as exc:
                status["source_index"] = "failed"
                status["source_index_error"] = type(exc).__name__

        sidecar_path = self.clean_source_dir / "semantic-scope-labels.jsonl"
        if sidecar_path.exists():
            status["semantic_sidecar"] = "present"
        elif self.semantic_sidecar_required:
            status["semantic_sidecar"] = "missing"
        prepared_surfaces = [
            name
            for name in ("working_memory", "semantic_sidecar", "semantic_triggers", "semantic_cues")
            if status.get(name) == "present"
        ]
        status["prepared_worker_surfaces"] = prepared_surfaces
        if self.semantic_sidecar_required and not prepared_surfaces:
            status["semantic_worker_status"] = "missing_degraded_to_clean_source"
        elif self.semantic_sidecar_required:
            status["semantic_worker_status"] = "prepared"
        else:
            status["semantic_worker_status"] = "not_required"
        return status

    def _read_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        try:
            return load_json(str(self.metadata_path))
        except Exception:
            return {}

    def _write_metadata(self, artifact_status: dict[str, Any]) -> None:
        payload = {
            "kind": "aippocampus_amemgym_agent_state",
            "schema_version": 1,
            "adapter": GENERIC_PROVIDER_LABEL,
            "mode": self.mode,
            "artifact_status": artifact_status,
            "boundary": {
                "official_amemgym_base_agent": True,
                "source_format": "generic-jsonl -> clean-source -> source-index",
                "answer_question_mutates_state": False,
                "semantic_sidecar_is_navigation_not_truth": True,
            },
        }
        save_json(str(self.metadata_path), payload)
