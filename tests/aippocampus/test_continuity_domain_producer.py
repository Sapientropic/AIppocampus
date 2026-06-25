from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import continuity_domain_scan
from aippocampus_runtime.recall.continuity_domain_producer import (
    _clean_candidate_term,
    propose_continuity_domain_events_from_registry,
)
from aippocampus_runtime.recall.continuity_domains import (
    match_continuity_domain_pointers,
    materialize_continuity_domains,
)


def _write_low_information_registry_fixture(root: Path) -> tuple[Path, Path]:
    registry_dir = root / "registry"
    clean = registry_dir / "threads" / "low-info-thread" / "clean-source"
    clean.mkdir(parents=True, exist_ok=True)
    messages = [
        {
            "message_id": "msg-low-a",
            "turn_id": "turn-low-a",
            "turn_index": 1,
            "source_line": 2,
            "role": "user",
            "phase": "",
            "text": "这个要怎么改一下？这个 AIppocampus 要怎么改？AIppocampus 小海马体仍然要回源。",
        },
        {
            "message_id": "msg-low-b",
            "turn_id": "turn-low-b",
            "turn_index": 2,
            "source_line": 4,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "那个怎么处理先别变成记忆标签；这个 AIppocampus 要怎么改也只是问法；小海马体应该保留 source-backed route。",
        },
        {
            "message_id": "msg-low-c",
            "turn_id": "turn-low-c",
            "turn_index": 3,
            "source_line": 6,
            "role": "user",
            "phase": "",
            "text": "这里要怎么做也只是指代词；小海马体和 AIppocampus 才是可用标签。",
        },
        {
            "message_id": "msg-low-d",
            "turn_id": "turn-low-d",
            "turn_index": 4,
            "source_line": 8,
            "role": "user",
            "phase": "",
            "text": "your answer",
        },
        {
            "message_id": "msg-low-e",
            "turn_id": "turn-low-e",
            "turn_index": 5,
            "source_line": 10,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "your answer",
        },
        {
            "message_id": "msg-low-f",
            "turn_id": "turn-low-f",
            "turn_index": 6,
            "source_line": 12,
            "role": "user",
            "phase": "",
            "text": (
                "but how should we change this? your answer gets visible; "
                "backstage life activation checklist persona visible gentle person."
            ),
        },
        {
            "message_id": "msg-low-g",
            "turn_id": "turn-low-g",
            "turn_index": 7,
            "source_line": 14,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": (
                "System Start first human sound voice easy feel know like stays gets visible."
            ),
        },
    ]
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in messages:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (clean / "turns.jsonl").write_text("", encoding="utf-8")
    (registry_dir / "threads.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": "low-info-thread",
                        "title": "AIppocampus 小海马体",
                        "keywords": ["AIppocampus", "小海马体"],
                        "paths": {"clean_source_dir": str(clean)},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return registry_dir, clean

def _write_lowercase_alias_registry_fixture(root: Path) -> tuple[Path, Path]:
    registry_dir = root / "registry"
    clean = registry_dir / "threads" / "alias-thread" / "clean-source"
    clean.mkdir(parents=True, exist_ok=True)
    messages = [
        {
            "message_id": "msg-alias-a",
            "turn_id": "turn-alias-a",
            "turn_index": 1,
            "source_line": 2,
            "role": "user",
            "phase": "",
            "text": "Style continuity should stay source-backed and reopenable.",
        },
        {
            "message_id": "msg-alias-b",
            "turn_id": "turn-alias-b",
            "turn_index": 2,
            "source_line": 4,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "The registered voice alias is a navigation handle, not source truth.",
        },
    ]
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in messages:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (clean / "turns.jsonl").write_text("", encoding="utf-8")
    (registry_dir / "threads.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": "alias-thread",
                        "title": "Style continuity",
                        "keywords": ["voice"],
                        "paths": {"clean_source_dir": str(clean)},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return registry_dir, clean


def _write_long_repeated_registry_fixture(
    root: Path,
    *,
    message_count: int = 1500,
) -> tuple[Path, Path]:
    registry_dir = root / "registry"
    clean = registry_dir / "threads" / "long-thread" / "clean-source"
    clean.mkdir(parents=True, exist_ok=True)
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for index in range(message_count):
            row = {
                "message_id": f"msg-long-{index}",
                "turn_id": f"turn-long-{index}",
                "turn_index": index + 1,
                "source_line": index + 2,
                "role": "user" if index % 2 == 0 else "assistant",
                "phase": "" if index % 2 == 0 else "final_answer",
                "text": "linear-domain repeats so source-backed continuity stays inspectable.",
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (clean / "turns.jsonl").write_text("", encoding="utf-8")
    (registry_dir / "threads.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": "long-thread",
                        "title": "linear-domain continuity",
                        "keywords": ["linear-domain"],
                        "paths": {"clean_source_dir": str(clean)},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return registry_dir, clean


class ContinuityDomainProducerTests(unittest.TestCase):
    def test_continuity_domain_producer_rejects_low_information_labels(self) -> None:
        for term in (
            "这个",
            "那个",
            "这里",
            "那边",
            "怎么",
            "这个 AIppocampus 要怎么改",
            "backstage",
            "life",
            "gets",
            "but",
            "activation",
            "checklist",
            "persona",
            "visible",
            "gentle",
            "person",
            "System",
            "you're",
            "first",
            "human",
            "sound",
            "Start",
            "stays",
            "voice",
            "easy",
            "feel",
            "know",
            "like",
            "one",
            "your",
            "answer",
            "your answer",
            "the answer",
            "your answer should change",
            "your answer gets visible",
            "github.com",
            "comment](https",
            "不是",
            "不过",
            "刚才",
            "本机",
            "压缩",
            "main",
        ):
            self.assertEqual(_clean_candidate_term(term), ("", False))
        self.assertEqual(_clean_candidate_term("AIppocampus"), ("AIppocampus", False))
        self.assertEqual(_clean_candidate_term("Graphify"), ("Graphify", False))
        self.assertEqual(_clean_candidate_term("Telethon"), ("Telethon", False))
        self.assertEqual(_clean_candidate_term("小海马体"), ("小海马体", False))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_low_information_registry_fixture(root)

            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=True,
                max_candidates=12,
            )

        titles = {event["title"] for event in report["candidate_events"]}
        self.assertGreater(report["metrics"]["low_information_label_suppressed_count"], 0)
        forbidden = {
            "这个",
            "那个",
            "这里",
            "那边",
            "怎么",
            "这个要怎么改一下",
            "这个 AIppocampus 要怎么改",
            "要怎么改",
            "backstage",
            "life",
            "gets",
            "but",
            "activation",
            "checklist",
            "persona",
            "visible",
            "gentle",
            "person",
            "system",
            "you're",
            "first",
            "human",
            "sound",
            "start",
            "stays",
            "voice",
            "easy",
            "feel",
            "know",
            "like",
            "one",
            "your",
            "answer",
            "your answer",
            "your answer gets visible",
            "github.com",
            "comment](https",
            "不是",
            "不过",
            "刚才",
            "本机",
            "压缩",
            "main",
        }
        self.assertFalse(titles & forbidden)
        cue_text = "\n".join(
            str(cue)
            for event in report["candidate_events"]
            for cue in event.get("activation_cues", [])
        ).casefold()
        for term in forbidden:
            self.assertNotIn(term.casefold(), cue_text)
        self.assertIn("小海马体", titles)

    def test_generic_cjk_prompt_does_not_project_low_information_domain_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, clean = _write_low_information_registry_fixture(root)
            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=True,
                max_candidates=12,
            )
            snapshot = materialize_continuity_domains(report["candidate_events"])
            generic_matches = match_continuity_domain_pointers(
                "这个要怎么改一下？",
                snapshot,
                clean_source_dir=clean,
            )
            specific_matches = match_continuity_domain_pointers(
                "小海马体要怎么改？",
                snapshot,
                clean_source_dir=clean,
            )

        self.assertEqual(generic_matches, [])
        self.assertTrue(specific_matches)

    def test_registered_lowercase_alias_remains_eligible_for_domain_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_lowercase_alias_registry_fixture(root)
            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=True,
                max_candidates=12,
            )

        titles = {event["title"] for event in report["candidate_events"]}
        self.assertIn("voice", titles)
        self.assertGreater(report["metrics"]["low_information_label_suppressed_count"], 0)

    def test_generic_english_prompt_does_not_project_low_information_domain_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, clean = _write_low_information_registry_fixture(root)
            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=True,
                max_candidates=12,
            )
            snapshot = materialize_continuity_domains(report["candidate_events"])
            generic_matches = match_continuity_domain_pointers(
                "but how should we change this?",
                snapshot,
                clean_source_dir=clean,
            )
            generic_multi_matches = match_continuity_domain_pointers(
                "your answer gets visible?",
                snapshot,
                clean_source_dir=clean,
            )
            specific_matches = match_continuity_domain_pointers(
                "AIppocampus hook source-backed memory",
                snapshot,
                clean_source_dir=clean,
            )

        titles = {event["title"].casefold() for event in report["candidate_events"]}
        self.assertNotIn("but", titles)
        self.assertNotIn("gets", titles)
        self.assertNotIn("visible", titles)
        self.assertEqual(generic_matches, [])
        self.assertEqual(generic_multi_matches, [])
        self.assertTrue(specific_matches)

    def test_long_thread_ref_dedupe_uses_identity_set_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_long_repeated_registry_fixture(
                root,
                message_count=1500,
            )

            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=True,
                max_candidates=4,
            )

        metrics = report["metrics"]
        self.assertEqual(metrics["scanned_message_count"], 1500)
        self.assertEqual(metrics["skipped_message_count"], 0)
        self.assertGreaterEqual(metrics["unique_term_ref_key_count"], 1)
        self.assertEqual(metrics["source_ref_dedup_list_scan_count"], 0)
        self.assertLessEqual(
            metrics["source_ref_identity_probe_count"],
            metrics["source_ref_candidate_count"],
        )
        event = next(
            event
            for event in report["candidate_events"]
            if event["title"] == "linear-domain"
        )
        self.assertEqual(len(event["source_refs"]), 6)

    def test_budgeted_clean_message_load_stops_at_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "messages.jsonl"
            path.write_text("{}\n", encoding="utf-8")
            yielded: list[int] = []
            original_iter = continuity_domain_scan.iter_jsonl_dict_rows

            def fake_iter_jsonl_dict_rows(_path: Path):
                for idx in range(10_000):
                    yielded.append(idx)
                    yield {"message_id": f"msg-{idx}", "text": f"linear-domain {idx}"}

            continuity_domain_scan.iter_jsonl_dict_rows = fake_iter_jsonl_dict_rows
            try:
                result = continuity_domain_scan.load_budgeted_clean_messages(
                    path,
                    max_messages=3,
                )
            finally:
                continuity_domain_scan.iter_jsonl_dict_rows = original_iter

        self.assertEqual(len(result.messages), 3)
        self.assertEqual(len(yielded), 4)
        self.assertEqual(result.skipped_message_count, 1)
        self.assertTrue(result.skipped_message_count_is_lower_bound)
        self.assertTrue(result.cutoff_reached)

if __name__ == "__main__":
    unittest.main()
