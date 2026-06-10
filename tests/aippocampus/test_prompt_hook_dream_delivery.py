from __future__ import annotations

from pathlib import Path

from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    dream_shadow,
    json,
    subprocess,
    sys,
)


class PromptHookDreamDeliveryTests(AmbientRecallHookCase):
    def _salt_for_arm(self, arm: str) -> str:
        for index in range(1000):
            salt = f"unit-delivery-{index}"
            if (
                dream_shadow.assigned_arm_for(
                    "thread_topic_epoch",
                    "session-secret",
                    "epoch-dream",
                    salt=salt,
                )
                == arm
            ):
                return salt
        raise AssertionError(f"could not find salt for {arm}")

    def _write_dream_working_memory(self, *, include_second: bool = False) -> Path:
        working_memory = self.root / f"working_memory_dream_{include_second}.jsonl"
        rows = [
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "dream_hypothesis",
                "candidate_key": "wm_dream_continuity",
                "title": "Continuity route bridge",
                "summary": "Use only as a route hint.",
                "trigger_terms": ["continuity"],
                "source_finding_ids": ["dreamfinding_continuity"],
                "confidence": 0.7,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "sensitive_use_gate": {"state": "allowed"},
                "foreground_use": {"strong_claim_requires_source_reopen": True},
            }
        ]
        if include_second:
            rows.append(
                {
                    **rows[0],
                    "candidate_key": "wm_dream_continuity_second",
                    "title": "Second continuity bridge",
                    "source_finding_ids": ["dreamfinding_continuity_second"],
                }
            )
        working_memory.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        return working_memory

    def test_prompt_hook_can_write_opt_in_dream_shadow_event(self) -> None:
        working_memory = self.root / "working_memory.jsonl"
        working_memory.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_continuity",
                    "title": "Continuity route bridge",
                    "summary": "Use only as a route hint.",
                    "trigger_terms": ["continuity"],
                    "source_finding_ids": ["dreamfinding_continuity"],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "sensitive_use_gate": {"state": "allowed"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        shadow_log = self.root / "shadow.jsonl"

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-shadow-ab",
                "--dream-shadow-log",
                str(shadow_log),
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        self.assertIn('"decision"', proc.stdout)
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        encoded = json.dumps(event, ensure_ascii=False)
        self.assertTrue(event["eligible_exposure"])
        self.assertEqual(event["dream"]["match_count"], 1)
        self.assertNotIn("continuity 这条线", encoded)

    def test_prompt_hook_default_filters_dream_from_foreground(self) -> None:
        working_memory = self._write_dream_working_memory()

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["decision"], "skip")
        self.assertEqual(payload["working_memory"], [])
        self.assertNotIn("Dream hypothesis", encoded)

    def test_prompt_hook_dry_run_logs_would_deliver_without_foreground_dream(self) -> None:
        working_memory = self._write_dream_working_memory()
        shadow_log = self.root / "dry-run-shadow.jsonl"

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-delivery-mode",
                "dry_run",
                "--dream-shadow-log",
                str(shadow_log),
                "--session-id",
                "session-secret",
                "--topic-epoch",
                "epoch-dream",
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        self.assertEqual(payload["decision"], "skip")
        self.assertIn(event["would_deliver_arm"], {"control", "dream"})
        self.assertIsNone(event["delivered_arm"])
        self.assertEqual(event["delivery_mode"], "dry_run")
        self.assertEqual(event["assignment_unit"], "thread_topic_epoch")

    def test_prompt_hook_delivered_control_is_holdback_without_context(self) -> None:
        working_memory = self._write_dream_working_memory()
        shadow_log = self.root / "control-shadow.jsonl"
        salt = self._salt_for_arm("control")

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-delivery-mode",
                "delivered",
                "--dream-shadow-log",
                str(shadow_log),
                "--dream-shadow-salt",
                salt,
                "--session-id",
                "session-secret",
                "--topic-epoch",
                "epoch-dream",
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        self.assertEqual(payload["decision"], "skip")
        self.assertEqual(event["delivered_arm"], "control")
        self.assertEqual(event["delivery_decision"], "delivered_control_holdback")

    def test_prompt_hook_delivered_dream_inserts_one_private_context(self) -> None:
        working_memory = self._write_dream_working_memory(include_second=True)
        shadow_log = self.root / "dream-shadow.jsonl"
        salt = self._salt_for_arm("dream")

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-delivery-mode",
                "delivered",
                "--dream-shadow-log",
                str(shadow_log),
                "--dream-shadow-salt",
                salt,
                "--session-id",
                "session-secret",
                "--topic-epoch",
                "epoch-dream",
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        self.assertEqual(event["delivered_arm"], "dream")
        self.assertEqual(event["delivery_decision"], "delivered_dream_treatment")
        self.assertEqual(context.count("Dream hypothesis, not source fact"), 1)
        self.assertIn("reopen source", context)

