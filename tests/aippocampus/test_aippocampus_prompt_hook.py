from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    hook,
    io,
    json,
    sys,
)


class PromptHookEntrypointContractTests(AmbientRecallHookCase):
    def test_prompt_hook_keeps_decision_and_rendering_in_split_modules(self) -> None:
        self.assertEqual(
            hook.assess_prompt.__module__,
            "aippocampus_runtime.recall.prompt_recall_decision",
        )
        self.assertEqual(
            hook.context_for_hook.__module__,
            "aippocampus_runtime.recall.prompt_context_render",
        )
        self.assertEqual(
            hook.hook_stdout_payload.__module__,
            "aippocampus_runtime.recall.prompt_context_render",
        )

    def test_hook_input_from_stdin_reads_codex_json_after_split(self) -> None:
        old_stdin = sys.stdin
        payload = {"prompt": "hook smoke 测试", "cwd": str(self.workspace)}
        try:
            sys.stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
            parsed = hook.hook_input_from_stdin()
        finally:
            sys.stdin = old_stdin

        self.assertEqual(parsed["prompt"], payload["prompt"])
        self.assertEqual(parsed["cwd"], payload["cwd"])
