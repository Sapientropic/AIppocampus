#!/usr/bin/env python3
"""Sanitized no-write smoke for optional live question-pair confirmation.

The smoke never writes to the formal subconscious jobs file. It creates a
temporary pending-request file, optionally calls the live confirmer, and feeds
the temporary artifacts back through question tracking to prove the round-trip
contract without emitting source refs or extracted question text.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.question import confirmation_live as live  # noqa: E402
from aippocampus_runtime.question import tracking  # noqa: E402
from aippocampus_runtime.question.confirmation import load_confirmation_decisions  # noqa: E402


def _route_summary(payload: dict[str, Any]) -> dict[str, Any]:
    route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
    return {
        key: route.get(key)
        for key in ("provider", "model", "route_name")
        if route.get(key)
    }


def run_question_confirmation_live_smoke(
    *,
    jobs_path: Path,
    registry_path: Path | None = None,
    call_model: bool = False,
    api_key_env: str | None = None,
    route_name: str | None = None,
    model: str | None = None,
    max_requests: int | None = 1,
    strong_threshold: float = tracking.DEFAULT_STRONG_THRESHOLD,
    borderline_threshold: float = tracking.DEFAULT_BORDERLINE_THRESHOLD,
    chat_fn: live.ChatFn = live.chat_json,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pending_path = root / "pending-question-confirmations.jsonl"
        artifact_path = root / "confirmed-question-pairs.jsonl"
        initial = tracking.run_question_tracking(
            jobs_path=jobs_path,
            registry_path=registry_path,
            no_write=True,
            strong_threshold=strong_threshold,
            borderline_threshold=borderline_threshold,
            pending_confirmations_output_path=pending_path,
        )
        live_payload = live.run_question_confirmation_live(
            requests_path=pending_path,
            output_path=artifact_path,
            route_name=route_name,
            model=model,
            api_key_env=api_key_env,
            call_model=call_model,
            max_requests=max_requests,
            chat_fn=chat_fn,
        )
        roundtrip: dict[str, Any] = {
            "ran": False,
            "link_count": 0,
            "accepted_confirmation_count": 0,
            "wrote_count": 0,
        }
        if artifact_path.exists():
            confirmed = tracking.run_question_tracking(
                jobs_path=jobs_path,
                registry_path=registry_path,
                no_write=True,
                strong_threshold=strong_threshold,
                borderline_threshold=borderline_threshold,
                confirmation_fn=load_confirmation_decisions(artifact_path),
            )
            roundtrip = {
                "ran": True,
                "link_count": int(confirmed.get("link_count") or 0),
                "accepted_confirmation_count": int(
                    confirmed.get("borderline_confirmation_accepted_pair_count") or 0
                ),
                "rejected_confirmation_count": int(
                    confirmed.get("borderline_confirmation_rejected_pair_count") or 0
                ),
                "invalid_confirmation_count": int(
                    confirmed.get("borderline_confirmation_malformed_pair_count") or 0
                )
                + int(confirmed.get("borderline_confirmation_stale_pair_count") or 0)
                + int(confirmed.get("borderline_confirmation_source_mismatch_pair_count") or 0),
                "wrote_count": int(confirmed.get("wrote_count") or 0),
            }

    live_status = str(live_payload.get("status") or "")
    status = (
        "live_roundtrip_completed"
        if roundtrip["ran"] and live_status == "live_model_confirmation_completed"
        else live_status
    )
    return {
        "ok": True,
        "kind": "aippocampus_question_confirmation_live_smoke",
        "status": status,
        "call_model": bool(call_model),
        "tracking": {
            "candidate_count": int(initial.get("candidate_count") or 0),
            "frontier_count": int(initial.get("frontier_count") or 0),
            "pending_confirmation_request_count": int(
                initial.get("pending_confirmation_request_count") or 0
            ),
            "pending_confirmation_wrote_count": int(
                initial.get("pending_confirmation_wrote_count") or 0
            ),
            "wrote_count": int(initial.get("wrote_count") or 0),
        },
        "live": {
            "status": live_status,
            "request_count": int(live_payload.get("request_count") or 0),
            "artifact_count": int(live_payload.get("artifact_count") or 0),
            "wrote_count": int(live_payload.get("wrote_count") or 0),
            "route": _route_summary(live_payload),
        },
        "roundtrip": roundtrip,
        "privacy": {
            "writes_formal_jobs": False,
            "raw_text_emitted": False,
            "source_refs_emitted": False,
            "temporary_artifacts_only": True,
        },
        "can_claim": [
            "live_confirmation_roundtrip_contract_exercised"
            if roundtrip["ran"]
            else "pending_confirmation_request_generation_exercised"
        ],
        "cannot_claim": [
            "real_user_calibration",
            "user_visible_recall_improvement",
            "private_history_threshold_quality",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs-input")
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--api-key-env")
    parser.add_argument("--route")
    parser.add_argument("--model")
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--strong-threshold", type=float, default=tracking.DEFAULT_STRONG_THRESHOLD)
    parser.add_argument("--borderline-threshold", type=float, default=tracking.DEFAULT_BORDERLINE_THRESHOLD)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    registry_path = tracking.default_registry_path(args.registry, args.registry_dir)
    jobs_path = (
        Path(args.jobs_input).resolve()
        if args.jobs_input
        else tracking.default_jobs_path(args.registry, args.registry_dir)
    )
    payload = run_question_confirmation_live_smoke(
        jobs_path=jobs_path,
        registry_path=registry_path,
        call_model=args.call_model,
        api_key_env=args.api_key_env,
        route_name=args.route,
        model=args.model,
        max_requests=args.max_requests,
        strong_threshold=args.strong_threshold,
        borderline_threshold=args.borderline_threshold,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "question confirmation live smoke: "
            f"{payload['status']} "
            f"({payload['tracking']['pending_confirmation_request_count']} pending, "
            f"{payload['roundtrip']['accepted_confirmation_count']} accepted)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
