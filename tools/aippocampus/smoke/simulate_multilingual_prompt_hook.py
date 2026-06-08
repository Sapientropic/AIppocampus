#!/usr/bin/env python3
"""Run multilingual ambient-recall hook smoke cases.

This is a manual compatibility smoke for sharing AIppocampus with users who may
switch languages. It intentionally calls the real prompt hook so it exercises
the same pre-gate, semantic gate, cache, and source rerank path as Codex.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.recall import semantic_cue_cache as cue_cache  # noqa: E402
from claim_boundary_refs import claim_boundary_ref  # noqa: E402

CASES: list[dict[str, Any]] = [
    {
        "name": "ru_memory",
        "prompt": "Как там мой внешний гиппокамп памяти и система продолжения разговоров?",
        "allow": ["scent"],
    },
    {
        "name": "es_memory",
        "prompt": "¿Cómo va mi hipocampo externo de memoria y la continuidad de conversaciones?",
        "allow": ["scent"],
    },
    {
        "name": "fr_memory",
        "prompt": "Où en est mon hippocampe externe de mémoire et la continuité des conversations ?",
        "allow": ["scent"],
    },
    {
        "name": "de_memory",
        "prompt": "Wie läuft mein externer Gedächtnis-Hippocampus und die Gesprächskontinuität?",
        "allow": ["scent"],
    },
    {
        "name": "pt_memory",
        "prompt": "Como está meu hipocampo externo de memória e a continuidade das conversas?",
        "allow": ["scent"],
    },
    {
        "name": "ar_memory",
        "prompt": "كيف حال الحُصين الخارجي للذاكرة واستمرار المحادثات؟",
        "allow": ["scent"],
    },
    {
        "name": "ja_memory",
        "prompt": "外部海馬みたいな記憶システムの進捗はどう？",
        "allow": ["scent"],
    },
    {
        "name": "ko_memory",
        "prompt": "외부 해마 같은 기억 시스템은 지금 어떻게 되고 있어?",
        "allow": ["scent"],
    },
    {
        "name": "th_memory",
        "prompt": "ระบบความจำแบบฮิปโปแคมปัสภายนอกตอนนี้เป็นอย่างไรบ้าง",
        "allow": ["scent"],
    },
    {
        "name": "es_exact",
        "prompt": "¿Puedes recuperar la frase exacta que dijiste sobre el hipocampo externo?",
        "allow": ["scent", "evidence"],
    },
    {
        "name": "fr_exact",
        "prompt": "Tu peux retrouver la citation exacte sur l'hippocampe externe ?",
        "allow": ["scent", "evidence"],
    },
    {
        "name": "ru_code",
        "prompt": "Почини hover-стиль кнопки dashboard и запусти тесты",
        "allow": ["skip"],
    },
    {
        "name": "es_code",
        "prompt": "Arregla el estilo hover del botón del dashboard y ejecuta las pruebas",
        "allow": ["skip"],
    },
    {
        "name": "ja_code",
        "prompt": "dashboard のボタン hover スタイルを直してテストを実行して",
        "allow": ["skip"],
    },
    {
        "name": "ar_code",
        "prompt": "أصلح نمط hover لزر dashboard وشغّل الاختبارات",
        "allow": ["skip"],
    },
    {"name": "es_daily", "prompt": "¿Qué tiempo hará mañana?", "allow": ["skip"]},
    {"name": "fr_daily", "prompt": "Rappelle-moi d'acheter du lait demain.", "allow": ["skip"]},
]


def run_case(
    case: dict[str, Any],
    *,
    cwd: Path,
    semantic_gate: str,
    semantic_timeout: int,
    registry_path: Path | None = None,
    semantic_cues_path: Path | None = None,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "aippocampus_runtime.hooks.prompt",
        "--cwd",
        str(cwd),
        "--semantic-gate",
        semantic_gate,
        "--semantic-timeout",
        str(semantic_timeout),
        "--json",
        "--prompt",
        str(case["prompt"]),
    ]
    if registry_path:
        cmd.extend(["--registry", str(registry_path)])
    if semantic_cues_path:
        cmd.extend(["--semantic-cues", str(semantic_cues_path)])
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=_paths.SKILL_SCRIPTS,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    if proc.returncode != 0:
        return {
            "name": case["name"],
            "ok": False,
            "expected": case["allow"],
            "error": ((proc.stdout or "") + (proc.stderr or ""))[-700:],
            "elapsed_ms": elapsed_ms,
        }
    result = json.loads(proc.stdout)
    semantic = result.get("semantic_gate") or {}
    reuse = result.get("semantic_gate_reuse") or {}
    decision = result.get("decision")
    return {
        "name": case["name"],
        "ok": decision in set(case["allow"]),
        "expected": case["allow"],
        "decision": decision,
        "top": ((result.get("candidates") or [{}])[0]).get("title"),
        "semantic_decision": semantic.get("decision"),
        "semantic_available": semantic.get("available"),
        "semantic_cached": semantic.get("cached"),
        "semantic_availability_reason": semantic.get("availability_reason"),
        "semantic_diagnostic": semantic.get("diagnostic"),
        "semantic_error_buckets": semantic.get("error_buckets") or {},
        "semantic_budget": semantic.get("budget") or {},
        "semantic_reuse_source": reuse.get("source"),
        "exact_cache_hit": reuse.get("exact_cache_hit"),
        "semantic_cue_hit": reuse.get("semantic_cue_hit"),
        "cold_model_call": reuse.get("cold_model_call"),
        "aliases": (semantic.get("query_aliases") or result.get("query_terms") or [])[:5],
        "elapsed_ms": elapsed_ms,
    }


def write_seeded_semantic_fixture(root: Path, cwd: Path) -> tuple[Path, Path]:
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": "session:aippocampus",
                        "title": "AIppocampus continuity work",
                        "project_label": "AIppocampus",
                        "anchor_titles": ["External hippocampus recall"],
                        "keywords": ["external hippocampus", "conversation continuity"],
                        "summary": "Source-backed continuity work for external memory.",
                        "paths": {"workspace": str(cwd)},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cues_path = root / "registry" / "semantic_cues.jsonl"
    semantic_result = {
        "available": True,
        "decision": "scent",
        "confidence": 0.9,
        "query_aliases": [
            "внешний гиппокамп",
            "hipocampo externo",
            "hippocampe externe",
            "Gedächtnis-Hippocampus",
            "hipocampo externo de memória",
            "الحُصين الخارجي",
            "外部海馬",
            "외부 해마",
            "ฮิปโปแคมปัสภายนอก",
            "frase exacta hipocampo externo",
            "citation exacte hippocampe externe",
        ],
    }
    for _ in range(2):
        cue_cache.record_semantic_cue_hits(
            cues_path,
            prompt="synthetic multilingual continuity fixture",
            semantic_result=semantic_result,
            source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
            route="semantic_gate",
        )
    return registry_path, cues_path


def claim_boundary(
    *,
    seeded_semantic_cues: bool,
    semantic_gate: str,
) -> dict[str, Any]:
    if seeded_semantic_cues:
        return {
            "claim_level": "seeded_semantic_cue_reuse_smoke",
            "coverage_mode": "seeded_semantic_cue_reuse",
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/benchmarks/design/benchmark-priority-map.md"
            ),
            "cannot_claim": [
                "cold_natural_multilingual_recall_quality",
                "sleep_time_trigger_generation_quality",
            ],
        }
    if semantic_gate == "off":
        return {
            "claim_level": "unseeded_local_fallback_smoke",
            "coverage_mode": "unseeded_local_fallback",
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/benchmarks/design/benchmark-priority-map.md"
            ),
            "cannot_claim": [
                "seeded_cue_cache_reuse_quality",
                "live_semantic_gate_quality",
                "cold_model_multilingual_recall_quality",
            ],
        }
    return {
        "claim_level": "unseeded_foreground_semantic_smoke",
        "coverage_mode": "unseeded_foreground_semantic",
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": ["seeded_cue_cache_reuse_quality"],
    }


def summarize_rows(
    rows: list[dict[str, Any]],
    *,
    seeded_semantic_cues: bool,
    semantic_gate: str,
) -> dict[str, Any]:
    boundary = claim_boundary(
        seeded_semantic_cues=seeded_semantic_cues,
        semantic_gate=semantic_gate,
    )
    passed = sum(1 for row in rows if row.get("ok"))
    return {
        "passed": passed,
        "total": len(rows),
        "semantic_gate": semantic_gate,
        "seeded_semantic_cues": bool(seeded_semantic_cues),
        "coverage_mode": boundary["coverage_mode"],
        "claim_boundary": boundary,
        "claim_boundary_ref": boundary["claim_boundary_ref"],
        "cannot_claim": boundary["cannot_claim"],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--semantic-gate", choices=["auto", "on", "off"], default="on")
    parser.add_argument("--semantic-timeout", type=int, default=20)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument(
        "--seed-semantic-cues",
        action="store_true",
        help="Use a temporary public fixture registry with active multilingual semantic cues.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    cases = CASES[: args.max_cases] if args.max_cases and args.max_cases > 0 else CASES
    with tempfile.TemporaryDirectory() as tmp:
        registry_path: Path | None = None
        semantic_cues_path: Path | None = None
        if args.seed_semantic_cues:
            registry_path, semantic_cues_path = write_seeded_semantic_fixture(Path(tmp), cwd)
        rows = [
            run_case(
                case,
                cwd=cwd,
                semantic_gate=args.semantic_gate,
                semantic_timeout=args.semantic_timeout,
                registry_path=registry_path,
                semantic_cues_path=semantic_cues_path,
            )
            for case in cases
        ]
    result = summarize_rows(
        rows,
        seeded_semantic_cues=bool(args.seed_semantic_cues),
        semantic_gate=args.semantic_gate,
    )
    passed = int(result["passed"])
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"multilingual hook cases: {passed}/{len(rows)} passed")
        for row in rows:
            mark = "OK" if row.get("ok") else "FAIL"
            print(
                f"- {mark} {row.get('name')}: {row.get('decision')} "
                f"(semantic={row.get('semantic_decision')}, top={row.get('top')}, {row.get('elapsed_ms')}ms)"
            )
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
