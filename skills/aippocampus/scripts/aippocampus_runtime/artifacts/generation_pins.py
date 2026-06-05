"""Reader pins for copy-on-write artifact generations.

Generation directories are rebuildable cache, but a foreground recall query may
already have resolved an older generation before a background publish swings the
pointer. Readers therefore create a short-lived visible pin beside the pointer;
storage GC only deletes an old generation when no active pin remains and the
conservative TTL window has elapsed. Keep this file-based and advisory so the
contract works without a daemon and across Windows/POSIX filesystems.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

PIN_DIR_NAME = ".reader-pins"
PIN_KIND = "aippocampus_generation_reader_pin"
DEFAULT_GENERATION_READER_PIN_TTL_SECONDS = 6 * 60 * 60


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reader_pin_dir(pointer_parent: Path) -> Path:
    return Path(pointer_parent) / PIN_DIR_NAME


def generation_id_for_artifact(artifact_path: Path) -> str | None:
    parts = Path(artifact_path).parts
    for index, part in enumerate(parts[:-1]):
        if part == "generations" and index + 1 < len(parts):
            generation = parts[index + 1]
            if generation.startswith("gen_"):
                return generation
    return None


def pointer_parent_for_generation_artifact(artifact_path: Path) -> Path | None:
    path = Path(artifact_path)
    generation = generation_id_for_artifact(path)
    if generation is None:
        return None
    for parent in path.parents:
        if parent.name == "generations":
            return parent.parent
    return None


def _relative_target(pointer_parent: Path, artifact_path: Path) -> str:
    try:
        return Path(artifact_path).resolve().relative_to(Path(pointer_parent).resolve()).as_posix()
    except (OSError, ValueError):
        return Path(artifact_path).as_posix()


def _safe_pin_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value) or "pin"


@contextlib.contextmanager
def pin_resolved_generation(
    artifact_path: Path,
    *,
    artifact_kind: str,
    ttl_seconds: int = DEFAULT_GENERATION_READER_PIN_TTL_SECONDS,
) -> Iterator[dict[str, Any] | None]:
    """Pin a resolved generation artifact for the duration of a foreground read.

    Stable compatibility paths are not inside `generations/gen_*`, so they do
    not need a pin. If the pin cannot be written (for example a read-only cache
    directory), the reader still proceeds; storage GC remains conservative
    because it also requires the TTL window to have elapsed.
    """

    artifact_path = Path(artifact_path)
    pointer_parent = pointer_parent_for_generation_artifact(artifact_path)
    generation = generation_id_for_artifact(artifact_path)
    if pointer_parent is None or generation is None:
        yield None
        return

    pins = reader_pin_dir(pointer_parent)
    pin_path: Path | None = None
    payload = {
        "schema_version": 1,
        "kind": PIN_KIND,
        "artifact_kind": artifact_kind,
        "pid": os.getpid(),
        "generation": generation,
        "created_at": utc_now(),
        "ttl_seconds": int(ttl_seconds),
        "target_relative_path": _relative_target(pointer_parent, artifact_path),
    }
    try:
        pins.mkdir(parents=True, exist_ok=True)
        pin_path = pins / (
            "reader-pin-"
            f"{_safe_pin_component(artifact_kind)}-"
            f"{_safe_pin_component(generation)}-"
            f"{os.getpid()}-{time.time_ns()}.json"
        )
        fd = os.open(str(pin_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError:
        pin_path = None

    try:
        yield {**payload, "pin_path": str(pin_path) if pin_path else None}
    finally:
        if pin_path is not None:
            try:
                pin_path.unlink()
            except FileNotFoundError:
                pass


def _pin_generation(pin: Path) -> str | None:
    try:
        payload = json.loads(pin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != PIN_KIND:
        return None
    generation = payload.get("generation")
    return generation if isinstance(generation, str) and generation else None


def reader_pin_summary(
    pointer_parent: Path,
    generation: str,
    *,
    ttl_seconds: int = DEFAULT_GENERATION_READER_PIN_TTL_SECONDS,
    now_seconds: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now_seconds is None else float(now_seconds)
    active = 0
    expired = 0
    malformed = 0
    pins = reader_pin_dir(pointer_parent)
    if pins.exists():
        for pin in pins.glob("*.json"):
            if _pin_generation(pin) != generation:
                continue
            try:
                age = max(0.0, now - pin.stat().st_mtime)
            except OSError:
                continue
            if age <= ttl_seconds:
                active += 1
            else:
                expired += 1
        for pin in pins.glob("*"):
            if pin.suffix != ".json":
                malformed += 1
    return {
        "generation": generation,
        "ttl_seconds": int(ttl_seconds),
        "active_reader_pin_count": active,
        "expired_reader_pin_count": expired,
        "malformed_pin_count": malformed,
    }


def generation_cleanup_contract(
    pointer_parent: Path,
    generation_dir: Path,
    *,
    ttl_seconds: int = DEFAULT_GENERATION_READER_PIN_TTL_SECONDS,
    now_seconds: float | None = None,
    freshness_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    now = time.time() if now_seconds is None else float(now_seconds)
    generation_dir = Path(generation_dir)
    generation = generation_dir.name
    latest_guard_mtime = 0.0
    try:
        latest_guard_mtime = max(latest_guard_mtime, generation_dir.stat().st_mtime)
    except OSError:
        pass
    for path in freshness_paths:
        try:
            latest_guard_mtime = max(latest_guard_mtime, Path(path).stat().st_mtime)
        except OSError:
            continue
    age_seconds = max(0, int(now - latest_guard_mtime)) if latest_guard_mtime else 0

    pins = reader_pin_summary(
        pointer_parent,
        generation,
        ttl_seconds=ttl_seconds,
        now_seconds=now,
    )
    active = int(pins["active_reader_pin_count"])
    if active > 0:
        cleanup_status = "blocked_active_reader_pin"
        status_name = "blocked"
        evidence = [
            f"active_reader_pin_count={active}",
            f"ttl_seconds={ttl_seconds}",
        ]
    elif age_seconds < ttl_seconds:
        cleanup_status = "blocked_ttl_window"
        status_name = "blocked"
        evidence = [
            "ttl_window_not_elapsed",
            f"generation_age_seconds={age_seconds}",
            f"ttl_seconds={ttl_seconds}",
        ]
    else:
        cleanup_status = "eligible"
        status_name = "passed"
        evidence = [
            "no_active_reader_pins",
            "ttl_window_elapsed",
            f"generation_age_seconds={age_seconds}",
            f"ttl_seconds={ttl_seconds}",
        ]

    return {
        "status": status_name,
        "cleanup_status": cleanup_status,
        "generation": generation,
        "generation_age_seconds": age_seconds,
        **pins,
        "evidence": evidence,
        "requirement": (
            "Old generation cleanup requires no active reader pin and a conservative TTL window."
        ),
    }
