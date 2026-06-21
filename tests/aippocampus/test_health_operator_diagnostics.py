from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime import health as health
from aippocampus_runtime import health_host_state as health_host_state


def _write_minimal_health_inputs(root: Path) -> dict[str, Path]:
    workspace = root / "workspace"
    workspace.mkdir()
    rollout = workspace / "rollout.jsonl"
    rollout.write_text(
        '{"type":"event_msg","payload":{"type":"user_message","message":"hi"}}\n',
        encoding="utf-8",
    )
    anchors = workspace / "thread-anchors.md"
    anchors.write_text("# Anchors\n", encoding="utf-8")
    index_dir = root / "index"
    index_dir.mkdir()
    manifest_path = index_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": "2026-06-03T00:00:00Z",
                "message_count": 1,
                "source_rollout_size": rollout.stat().st_size,
                "last_message_line": 1,
                "rag": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (index_dir / "source_index.sqlite").write_bytes(b"sqlite")
    clean = root / "clean-source"
    clean.mkdir()
    clean_manifest = {
        "schema_version": 2,
        "upgrade_contract": {"source_backed": True},
        "source_rollout_size": rollout.stat().st_size,
        "message_count": 1,
        "turn_count": 1,
    }
    (clean / "manifest.json").write_text(json.dumps(clean_manifest), encoding="utf-8")
    (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
    graphify = root / "graphify-corpus"
    graphify.mkdir()
    (graphify / "corpus_manifest.json").write_text(
        json.dumps({"source_index_manifest_sha256": health.file_sha256(manifest_path)}),
        encoding="utf-8",
    )
    return {
        "workspace": workspace,
        "rollout": rollout,
        "anchors": anchors,
        "index_dir": index_dir,
        "clean": clean,
        "graphify": graphify,
    }

def _health_options(root: Path, paths: dict[str, Path], **overrides: object) -> health.HealthOptions:
    return health.HealthOptions(
        cwd=paths["workspace"],
        index_dir=paths["index_dir"],
        clean_source_dir=paths["clean"],
        graphify_corpus=paths["graphify"],
        segments_dir=root / "segments",
        checkpoint_state=root / "checkpoint_state.json",
        anchors=paths["anchors"],
        registry_dir=root / "registry",
        **overrides,
    )

class HealthOperatorDiagnosticsTests(unittest.TestCase):
    def test_health_json_detail_full_records_section_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_minimal_health_inputs(root)
            with (
                mock.patch.object(health, "locate_rollout", return_value=paths["rollout"]),
                mock.patch.object(
                    health,
                    "registry_cache_pressure_report",
                    return_value={"available": True, "pressure": False},
                ),
                mock.patch.object(
                    health,
                    "background_cognition_health",
                    return_value={"available": True, "lane_count": 0},
                ),
                mock.patch.object(
                    health,
                    "codex_host_state_confounds",
                    return_value={"available": False, "partial": False},
                ),
            ):
                payload = health.build_health_report(
                    _health_options(
                        root,
                        paths,
                        include_operator_diagnostics=True,
                        slow_section_threshold_ms=0,
                    )
                )

        performance = payload["diagnostics"]["performance"]
        section_names = {section["name"] for section in performance["sections"]}

        self.assertIn("core_readiness", section_names)
        self.assertIn("storage_pressure", section_names)
        self.assertIn("background_cognition", section_names)
        self.assertIn("host_state_confounds", section_names)
        self.assertTrue(performance["slow_sections"])
        self.assertFalse(performance["privacy_boundary"]["paths_included"])
        self.assertTrue(
            all(isinstance(section["elapsed_ms"], int | float) for section in performance["sections"])
        )

    def test_health_full_detail_defers_storage_pressure_without_expensive_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_minimal_health_inputs(root)
            with (
                mock.patch.object(health, "locate_rollout", return_value=paths["rollout"]),
                mock.patch.object(
                    health,
                    "registry_cache_pressure_report",
                    side_effect=AssertionError("storage pressure should require explicit opt-in"),
                ),
                mock.patch.object(
                    health,
                    "background_cognition_health",
                    return_value={"available": True, "lane_count": 0},
                ),
                mock.patch.object(
                    health,
                    "codex_host_state_confounds",
                    return_value={"available": False, "partial": False},
                ),
            ):
                payload = health.build_health_report(
                    _health_options(root, paths, include_operator_diagnostics=True)
                )

        storage_pressure = payload["storage_pressure"]
        self.assertTrue(storage_pressure["partial"])
        self.assertEqual(storage_pressure["status"], "deferred")
        self.assertEqual(
            storage_pressure["reason"],
            "expensive_storage_pressure_diagnostic_requires_opt_in",
        )
        self.assertEqual(
            storage_pressure["next_operator_action"],
            "aippocampus health --detail full --json --include-expensive-diagnostics --operator-timeout-ms 30000",
        )
        self.assertFalse(storage_pressure["privacy_boundary"]["paths_included"])

    def test_codex_host_state_confounds_returns_partial_when_scan_budget_expires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            private_paths = [logs / f"private-session-{index}.log" for index in range(12)]

            def iter_files(path: Path):
                if path.name == "logs":
                    return iter(private_paths)
                return iter(())

            with (
                mock.patch.object(health_host_state, "_iter_files", side_effect=iter_files),
                mock.patch.object(health_host_state, "_safe_stat_size", return_value=128),
                mock.patch.object(
                    health_host_state,
                    "perf_counter",
                    side_effect=[0.0, 0.0, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002],
                ),
            ):
                payload = health_host_state.codex_host_state_confounds(
                    root,
                    max_elapsed_ms=1,
                )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["partial"])
        self.assertTrue(payload["logs_db_wal"]["scan_timed_out"])
        self.assertEqual(payload["logs_db_wal"]["partial_reason"], "scan_time_budget_exceeded")
        self.assertEqual(
            payload["next_operator_action"],
            "aippocampus health --detail full --json --operator-timeout-ms 30000",
        )
        self.assertFalse(payload["privacy_boundary"]["paths_included"])
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("private-session", encoded)

if __name__ == "__main__":
    unittest.main()
