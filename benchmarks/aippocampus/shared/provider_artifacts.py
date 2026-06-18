"""Public-safe provider artifact metadata for benchmark evidence."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "benchmark-provider-artifact-v1"
PUBLIC_METADATA_KEYS = {
    "arm",
    "case_pack_split",
    "dataset_boundary",
    "kind",
    "raw_gold_answers_included",
    "run_surfaces",
    "runner",
    "stage3_incremental_dry_run",
    "status",
    "surface_count",
}
PRIVATE_VALUE_MARKERS = ("\\", "/", "secret", "token", "key", "password", "bearer", "sk-")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fingerprint(value: Any) -> str:
    return "ptr_" + hashlib.sha256(repr(value).encode("utf-8", errors="replace")).hexdigest()[:16]


def _public_metadata(value: Mapping[str, Any] | str, *, fallback_kind: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"kind": fallback_kind}
    public: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text not in PUBLIC_METADATA_KEYS or not _public_value(item):
            continue
        public[key_text] = item
    if "kind" not in public:
        public["kind"] = fallback_kind
    public["metadata_field_count"] = len(public)
    return public


def _public_value(value: Any) -> bool:
    if isinstance(value, bool | int | float) or value is None:
        return True
    if isinstance(value, str):
        text = value.casefold()
        return not any(marker in text for marker in PRIVATE_VALUE_MARKERS)
    if isinstance(value, list):
        return len(value) <= 12 and all(_public_value(item) for item in value)
    return False


def public_provider_artifact(
    *,
    benchmark_id: str,
    provider: str,
    model: str | None,
    prompt: Mapping[str, Any] | str,
    runner: Mapping[str, Any] | str,
    cost: Mapping[str, Any] | str | None = None,
    run_date: str | None = None,
    status: str = "blocked_not_run",
    blocker_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a public artifact from metadata, never raw provider payloads."""

    prompt_payload = _public_metadata(prompt, fallback_kind="provider_prompt_metadata")
    runner_payload = _public_metadata(runner, fallback_kind="provider_runner_metadata")
    cost_payload: Mapping[str, Any]
    if isinstance(cost, Mapping):
        cost_payload = dict(cost)
    elif cost is None:
        cost_payload = {"status": "not_reported", "estimated_cost_usd": None}
    else:
        cost_payload = {"status": str(cost), "estimated_cost_usd": None}
    blocker = dict(blocker_metadata or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_public_benchmark_provider_artifact",
        "benchmark_id": benchmark_id,
        "status": status,
        "provider": provider,
        "model": model,
        "prompt": {
            **prompt_payload,
            "raw_prompt_included": False,
            "prompt_fingerprint": _fingerprint(prompt_payload),
        },
        "runner": {
            **runner_payload,
            "raw_stdout_included": False,
            "raw_stderr_included": False,
        },
        "cost": cost_payload,
        "run_date": run_date or now_utc(),
        "blocker_metadata": blocker,
        "privacy_boundary": {
            "raw_provider_payload_included": False,
            "provider_credentials_included": False,
            "absolute_local_paths_included": False,
            "raw_model_outputs_included": False,
        },
        "raw_payload_policy": "operator_private_or_discarded_not_public_repo",
    }
