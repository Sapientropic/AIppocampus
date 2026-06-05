from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import activation_payload_compaction as runner  # noqa: E402
from aippocampus_runtime.ops.activation_authority_audit import (  # noqa: E402
    apply_dead_letter_candidate_manifest,
)


def source_ref(label: str) -> dict[str, Any]:
    return {"thread_key": f"session:{label}", "message_id": "msg-1", "line": 7}


def dead_letter_manifest() -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    for surface_id, surface_kind, label in [
        ("ambient-card-1", "ambient_card", "ambient"),
        ("working-memory-1", "working_memory", "working"),
        ("semantic-trigger-1", "semantic_trigger", "semantic"),
    ]:
        surfaces.append(
            {
                "surface_id": surface_id,
                "surface_kind": surface_kind,
                "conflict_key": f"dead-letter-{surface_kind}",
                "pruning_action": "retire",
                "wrong_route_drag_count": 4,
                "source_refs": [source_ref(label)],
                "provenance_pointer": f"{surface_kind}:test-fixture",
            }
        )
    return apply_dead_letter_candidate_manifest(
        surfaces,
        applied_at="2026-06-05T06:00:00Z",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_owner_fixtures(root: Path) -> tuple[Path, Path, Path, Path]:
    manifest_path = root / "dead-letter-manifest.json"
    manifest_path.write_text(json.dumps(dead_letter_manifest(), ensure_ascii=False), encoding="utf-8")

    ambient_cache = root / "ambient-cache.json"
    ambient_cache.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": {
                    "topic": {
                        "cards": [
                            {
                                "card_id": "ambient-card-1",
                                "kind": "aippocampus_ambient_card",
                                "title": "Raw ambient title",
                                "summary": "Raw ambient summary",
                                "source_refs": [source_ref("ambient")],
                                "related_fingerprints": ["card:ambient-card-1"],
                            }
                        ],
                        "source_ref_fingerprints": ["source:ambient"],
                        "related_fingerprints": ["card:ambient-card-1"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    working_memory = root / "working_memory.jsonl"
    write_jsonl(
        working_memory,
        [
            {
                "schema_version": 1,
                "kind": "aippocampus_working_memory",
                "candidate_key": "working-memory-1",
                "status": "candidate",
                "title": "Raw working title",
                "summary": "Raw working summary",
                "activation_cues": ["raw working cue"],
                "source_refs": [source_ref("working")],
            }
        ],
    )

    semantic_triggers = root / "semantic_triggers.jsonl"
    write_jsonl(
        semantic_triggers,
        [
            {
                "schema_version": 1,
                "kind": "aippocampus_semantic_trigger",
                "trigger_id": "semantic-trigger-1",
                "status": "active",
                "title": "Raw semantic title",
                "concept": "Raw semantic concept",
                "aliases": ["raw semantic alias"],
                "activation_cues": ["raw semantic cue"],
                "when_to_use": "Raw semantic guidance",
                "source_refs": [source_ref("semantic")],
            }
        ],
    )
    return manifest_path, ambient_cache, working_memory, semantic_triggers


class ActivationPayloadCompactionRunnerTests(unittest.TestCase):
    def test_dry_run_reports_all_owner_compactions_without_writing_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, ambient_cache, working_memory, semantic_triggers = write_owner_fixtures(root)

            report = runner.run_activation_payload_compaction(
                dead_letter_manifest_path=manifest_path,
                ambient_cache_path=ambient_cache,
                working_memory_path=working_memory,
                semantic_triggers_path=semantic_triggers,
                apply=False,
                compacted_at="2026-06-05T06:05:00Z",
            )

            self.assertEqual(report["kind"], "aippocampus_activation_payload_compaction_run")
            self.assertEqual(report["write_mode"], "no_write_dry_run")
            self.assertFalse(report["applied"])
            self.assertEqual(report["metrics"]["owner_count_run"], 3)
            self.assertEqual(report["metrics"]["payload_compacted_count"], 3)
            self.assertEqual(report["owners"]["ambient_cache"]["metrics"]["payload_compacted_count"], 1)
            self.assertEqual(report["owners"]["working_memory"]["metrics"]["payload_compacted_count"], 1)
            self.assertEqual(report["owners"]["semantic_triggers"]["metrics"]["payload_compacted_count"], 1)

            self.assertIn("Raw ambient title", ambient_cache.read_text(encoding="utf-8"))
            self.assertIn("Raw working title", working_memory.read_text(encoding="utf-8"))
            self.assertIn("Raw semantic title", semantic_triggers.read_text(encoding="utf-8"))

            serialized_report = json.dumps(report, ensure_ascii=False, sort_keys=True)
            self.assertNotIn(str(root), serialized_report)
            self.assertNotIn("Raw ambient", serialized_report)
            self.assertNotIn("Raw working", serialized_report)
            self.assertNotIn("Raw semantic", serialized_report)
            self.assertNotIn("session:ambient", serialized_report)
            self.assertFalse(report["contract"]["foreground_hook_mutation"])

    def test_apply_writes_owner_tombstones_only_when_apply_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, ambient_cache, working_memory, semantic_triggers = write_owner_fixtures(root)

            report = runner.run_activation_payload_compaction(
                dead_letter_manifest_path=manifest_path,
                ambient_cache_path=ambient_cache,
                working_memory_path=working_memory,
                semantic_triggers_path=semantic_triggers,
                apply=True,
                compacted_at="2026-06-05T06:05:00Z",
            )

            self.assertEqual(report["write_mode"], "apply_owner_payload_compaction")
            self.assertTrue(report["applied"])
            self.assertEqual(report["metrics"]["payload_compacted_count"], 3)

            ambient = json.loads(ambient_cache.read_text(encoding="utf-8"))
            card = ambient["entries"]["topic"]["cards"][0]
            self.assertTrue(card["payload_compacted"])
            self.assertNotIn("title", card)
            self.assertNotIn("summary", card)
            self.assertNotIn("source_refs", card)

            working = read_jsonl(working_memory)[0]
            self.assertTrue(working["payload_compacted"])
            self.assertEqual(working["status"], "payload_compacted")
            self.assertNotIn("candidate_key", working)
            self.assertNotIn("title", working)
            self.assertNotIn("source_refs", working)

            semantic = read_jsonl(semantic_triggers)[0]
            self.assertTrue(semantic["payload_compacted"])
            self.assertEqual(semantic["status"], "payload_compacted")
            self.assertNotIn("trigger_id", semantic)
            self.assertNotIn("title", semantic)
            self.assertNotIn("aliases", semantic)
            self.assertNotIn("source_refs", semantic)

    def test_missing_owner_path_is_reported_without_exposing_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _ambient_cache, working_memory, semantic_triggers = write_owner_fixtures(root)
            missing = root / "missing-cache.json"

            report = runner.run_activation_payload_compaction(
                dead_letter_manifest_path=manifest_path,
                ambient_cache_path=missing,
                working_memory_path=working_memory,
                semantic_triggers_path=semantic_triggers,
                apply=False,
                compacted_at="2026-06-05T06:05:00Z",
            )

            self.assertEqual(report["owners"]["ambient_cache"]["status"], "skipped")
            self.assertEqual(report["owners"]["ambient_cache"]["skip_reason"], "owner_path_missing")
            self.assertEqual(report["metrics"]["owner_count_run"], 2)
            self.assertNotIn(str(root), json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
