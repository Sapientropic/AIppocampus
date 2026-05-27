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
import time
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

PROMPT_HOOK = _paths.SKILL_SCRIPTS / "aippocampus_prompt_hook.py"

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
    case: dict[str, Any], *, cwd: Path, semantic_gate: str, semantic_timeout: int
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(PROMPT_HOOK),
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
    start = time.perf_counter()
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
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
        "aliases": (semantic.get("query_aliases") or result.get("query_terms") or [])[:5],
        "elapsed_ms": elapsed_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--semantic-gate", choices=["auto", "on", "off"], default="on")
    parser.add_argument("--semantic-timeout", type=int, default=20)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cases = CASES[: args.max_cases] if args.max_cases and args.max_cases > 0 else CASES
    rows = [
        run_case(
            case,
            cwd=Path(args.cwd).resolve(),
            semantic_gate=args.semantic_gate,
            semantic_timeout=args.semantic_timeout,
        )
        for case in cases
    ]
    passed = sum(1 for row in rows if row.get("ok"))
    result = {"passed": passed, "total": len(rows), "rows": rows}
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
