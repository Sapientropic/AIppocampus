from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.model import cache_contract_guard as cache_guard  # noqa: E402
from aippocampus_runtime.model import routing as routing  # noqa: E402


def json_dump_for_test(item: dict[str, str]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


class DeepSeekModelRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_values = {
            name: os.environ.get(name)
            for name in [
                "AIPPOCAMPUS_DEEPSEEK_API_KEY",
                "DEEPSEEK_API_KEY",
                "DEEPSEEK_MODEL",
                "DEEPSEEK_BASE_URL",
                "AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL",
                "AIPPOCAMPUS_DEEPSEEK_BASE_URL",
                "AIPPOCAMPUS_DEEPSEEK_PRO_MODEL",
                "DEEPSEEK_PRO_MODEL",
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
                "AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT",
                "AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING",
                "AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT",
                "AIPPOCAMPUS_OPENAI_COMPAT_REASONING_CONTENT_HANDLING",
                "AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND",
            ]
        }
        for name in self.old_values:
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        for name, value in self.old_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_flash_is_default_and_pro_routes_are_explicit(self) -> None:
        default = routing.resolve_model_route(None)
        self.assertEqual(default.model, "deepseek-v4-flash")
        self.assertEqual(default.provider, "deepseek")
        self.assertEqual(default.base_url, "https://api.deepseek.com")
        self.assertEqual(default.api_key_env, "AIPPOCAMPUS_DEEPSEEK_API_KEY")
        self.assertTrue(default.capabilities.supports_user_id)
        self.assertTrue(default.capabilities.supports_thinking)
        self.assertTrue(default.capabilities.supports_reasoning_effort)
        self.assertEqual(default.capabilities.default_thinking, "enabled")
        self.assertEqual(default.capabilities.default_reasoning_effort, "high")
        self.assertEqual(routing.resolve_route_thinking(default), "enabled")
        self.assertEqual(routing.resolve_route_reasoning_effort(default, thinking="enabled"), "high")
        self.assertEqual(default.capabilities.cache_metrics_kind, "deepseek_prefix")
        self.assertEqual(routing.route_cache_contract(default), "deepseek_prefix_v1")
        self.assertEqual(default.capabilities.safe_default_concurrency, 4)
        self.assertEqual(routing.resolve_model_route("default").model, "deepseek-v4-flash")
        self.assertEqual(routing.resolve_model_route("fast").model, "deepseek-v4-flash")

        for route in [
            "pro",
            "slow_adjudication",
            "suppressed_label_recovery",
            "agentic_source_review",
        ]:
            resolved = routing.resolve_model_route(route)
            self.assertEqual(resolved.model, "deepseek-v4-pro")
            self.assertEqual(resolved.tier, "pro")
            self.assertEqual(resolved.capabilities.safe_default_concurrency, 1)

    def test_environment_overrides_use_canonical_default_model_knobs(self) -> None:
        os.environ["DEEPSEEK_MODEL"] = "legacy-flash"
        os.environ["AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL"] = "primary-flash"
        os.environ["AIPPOCAMPUS_DEEPSEEK_PRO_MODEL"] = "pro-expensive"

        self.assertEqual(routing.resolve_model_route("default").model, "primary-flash")
        self.assertEqual(
            routing.resolve_model_route("agentic_source_review").model, "pro-expensive"
        )
        self.assertEqual(
            routing.resolve_model_route("default", explicit_model="manual").model, "manual"
        )

    def test_legacy_explicit_base_or_api_env_uses_conservative_compatible_capabilities(self) -> None:
        resolved = routing.resolve_model_route(
            None,
            explicit_model="local-model",
            explicit_base_url="http://127.0.0.1:11434/v1",
            explicit_api_key_env="LOCAL_KEY",
        )

        self.assertEqual(resolved.route, "explicit_openai_compatible")
        self.assertEqual(resolved.provider, "openai-compatible")
        self.assertEqual(resolved.model, "local-model")
        self.assertEqual(resolved.base_url, "http://127.0.0.1:11434/v1")
        self.assertEqual(resolved.api_key_env, "LOCAL_KEY")
        self.assertFalse(resolved.capabilities.supports_user_id)
        self.assertFalse(resolved.capabilities.supports_thinking)
        self.assertFalse(resolved.capabilities.supports_reasoning_effort)
        self.assertIsNone(routing.resolve_route_thinking(resolved))
        self.assertIsNone(routing.resolve_route_reasoning_effort(resolved, thinking=None))
        self.assertEqual(resolved.capabilities.cache_metrics_kind, "none")
        self.assertEqual(routing.route_cache_contract(resolved), "none")
        self.assertEqual(resolved.capabilities.safe_default_concurrency, 1)

    def test_aippocampus_deepseek_env_wins_over_legacy_env(self) -> None:
        os.environ["DEEPSEEK_MODEL"] = "legacy-flash"
        os.environ["AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL"] = "primary-flash"
        os.environ["DEEPSEEK_PRO_MODEL"] = "legacy-pro"
        os.environ["AIPPOCAMPUS_DEEPSEEK_PRO_MODEL"] = "primary-pro"
        os.environ["DEEPSEEK_BASE_URL"] = "https://legacy.example/v1"
        os.environ["AIPPOCAMPUS_DEEPSEEK_BASE_URL"] = "https://primary.example/v1"

        flash = routing.resolve_model_route("default")
        pro = routing.resolve_model_route("pro")

        self.assertEqual(flash.model, "primary-flash")
        self.assertEqual(pro.model, "primary-pro")
        self.assertEqual(flash.base_url, "https://primary.example/v1")
        self.assertEqual(pro.base_url, "https://primary.example/v1")

    def test_aippocampus_deepseek_api_key_env_is_the_only_default_env(self) -> None:
        self.assertEqual(
            routing.resolve_model_route("default").api_key_env,
            "AIPPOCAMPUS_DEEPSEEK_API_KEY",
        )

        os.environ["DEEPSEEK_API_KEY"] = "legacy-key"
        self.assertEqual(
            routing.resolve_model_route("default").api_key_env,
            "AIPPOCAMPUS_DEEPSEEK_API_KEY",
        )

        os.environ["AIPPOCAMPUS_DEEPSEEK_API_KEY"] = "canonical-key"
        self.assertEqual(
            routing.resolve_model_route("default").api_key_env,
            "AIPPOCAMPUS_DEEPSEEK_API_KEY",
        )

    def test_configured_openai_compatible_provider_exposes_neutral_capabilities(self) -> None:
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER"] = "local-test-provider"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_MODEL"] = "local-model"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL"] = "http://127.0.0.1:9999/v1"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV"] = "LOCAL_TEST_API_KEY"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_ROUTE"] = "local_semantic"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY"] = "2"

        resolved = routing.resolve_model_route("local_semantic")
        payload = resolved.as_dict()

        self.assertEqual(resolved.provider, "local-test-provider")
        self.assertEqual(resolved.model, "local-model")
        self.assertEqual(resolved.base_url, "http://127.0.0.1:9999/v1")
        self.assertEqual(resolved.api_key_env, "LOCAL_TEST_API_KEY")
        self.assertEqual(resolved.tier, "openai_compatible")
        self.assertEqual(resolved.capabilities.api_compatibility, "openai_chat_completions")
        self.assertTrue(resolved.capabilities.supports_json_response)
        self.assertFalse(resolved.capabilities.supports_user_id)
        self.assertFalse(resolved.capabilities.supports_thinking)
        self.assertFalse(resolved.capabilities.supports_reasoning_effort)
        self.assertEqual(resolved.capabilities.cache_metrics_kind, "none")
        self.assertEqual(routing.route_cache_contract(resolved), "none")
        self.assertEqual(resolved.capabilities.safe_default_concurrency, 2)
        self.assertEqual(payload["capabilities"]["supports_user_id"], False)
        self.assertNotIn("LOCAL_TEST_SECRET_VALUE", str(payload))

    def test_openai_compatible_provider_can_disable_json_and_enable_known_extensions(self) -> None:
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER"] = "compatible-provider"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_MODEL"] = "compatible-model"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL"] = "https://compatible.example/v1"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV"] = "COMPATIBLE_API_KEY"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON"] = "false"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID"] = "true"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING"] = "true"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT"] = "true"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING"] = "enabled"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT"] = "max"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND"] = "provider_specific"

        resolved = routing.resolve_model_route("openai_compatible")

        self.assertFalse(resolved.capabilities.supports_json_response)
        self.assertTrue(resolved.capabilities.supports_user_id)
        self.assertTrue(resolved.capabilities.supports_thinking)
        self.assertTrue(resolved.capabilities.supports_reasoning_effort)
        self.assertEqual(routing.resolve_route_thinking(resolved), "enabled")
        self.assertEqual(routing.resolve_route_reasoning_effort(resolved, thinking="enabled"), "max")
        self.assertEqual(resolved.capabilities.cache_metrics_kind, "provider_specific")
        self.assertEqual(routing.route_cache_contract(resolved), "none")

    def test_model_call_site_cache_contract_inventory_is_public_and_sanitized(self) -> None:
        inventory = routing.model_call_site_cache_contract_inventory()
        by_call_site = {item["call_site"]: item for item in inventory}

        for required in [
            "subconscious.agent",
            "subconscious.review",
            "semantic_scope_suppressed_recovery",
            "public_semantic_sidecar_labeler",
            "standard_public_line_reranker",
            "locomo_fixed_reader",
            "longmemeval_fixed_reader",
            "dream_sleep_cycle",
            "dream_real_history_eval",
            "dream_live_shadow_ab",
            "question_confirmation_live",
        ]:
            self.assertIn(required, by_call_site)

        required_fields = {
            "call_site",
            "path",
            "owner",
            "purpose",
            "route_source",
            "cache_contract",
            "usage_telemetry",
        }
        for item in inventory:
            self.assertTrue(required_fields <= set(item), item)
            rendered = json_dump_for_test(item)
            self.assertNotIn("E:\\", rendered)
            self.assertNotIn("C:\\", rendered)
            self.assertNotIn("api_key", item["usage_telemetry"].casefold())

    def test_static_cache_contract_guard_covers_live_model_call_surfaces(self) -> None:
        audit = cache_guard.model_cache_contract_call_site_audit(repo_root=REPO_ROOT)

        self.assertTrue(audit["ok"], json.dumps(audit, ensure_ascii=False, indent=2))
        self.assertEqual(audit["metrics"]["missing_cache_contract_count"], 0)
        self.assertGreaterEqual(audit["metrics"]["explicit_cache_contract_count"], 10)
        self.assertEqual(audit["metrics"]["inventory_entry_count"], 11)

        audited_paths = {item["path"] for item in audit["call_sites"]}
        for required_path in [
            "skills/aippocampus/scripts/aippocampus_runtime/subconscious/runtime.py",
            "skills/aippocampus/scripts/aippocampus_runtime/subconscious/worker.py",
            "skills/aippocampus/scripts/aippocampus_runtime/dream/sleep_cycle.py",
            "skills/aippocampus/scripts/aippocampus_runtime/dream/real_history_eval.py",
            "skills/aippocampus/scripts/aippocampus_runtime/dream/live_shadow_ab.py",
            "skills/aippocampus/scripts/aippocampus_runtime/question/confirmation_live.py",
            "benchmarks/aippocampus/source_evidence/public_semantic.py",
            "benchmarks/aippocampus/source_evidence/standard_public.py",
            "benchmarks/aippocampus/benchmark_locomo_qa.py",
            "benchmarks/aippocampus/benchmark_longmemeval_answer.py",
        ]:
            self.assertIn(required_path, audited_paths)

        rendered = json.dumps(audit, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("E:\\", rendered)
        self.assertNotIn("C:\\", rendered)
        self.assertNotIn("sk-", rendered)

    def test_static_cache_contract_guard_fails_new_uncontracted_live_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = (
                root
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "new_live_model_path.py"
            )
            target.parent.mkdir(parents=True)
            target.write_text(
                "\n".join(
                    [
                        "from aippocampus_runtime.model.client import ChatClientConfig",
                        "",
                        "CONFIG = ChatClientConfig(",
                        "    api_key='SECRET_NOT_RENDERED',",
                        "    model='deepseek-v4-flash',",
                        "    base_url='https://api.deepseek.com',",
                        ")",
                    ]
                ),
                encoding="utf-8",
            )

            audit = cache_guard.model_cache_contract_call_site_audit(
                repo_root=root,
                scan_paths=(
                    "skills/aippocampus/scripts/aippocampus_runtime/new_live_model_path.py",
                ),
            )

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["metrics"]["missing_cache_contract_count"], 1)
        self.assertEqual(
            audit["missing_cache_contract"][0]["path"],
            "skills/aippocampus/scripts/aippocampus_runtime/new_live_model_path.py",
        )
        self.assertEqual(audit["missing_cache_contract"][0]["call"], "ChatClientConfig")
        self.assertNotIn("SECRET_NOT_RENDERED", json.dumps(audit, sort_keys=True))

    def test_openai_compatible_provider_reports_missing_required_config(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER.*AIPPOCAMPUS_OPENAI_COMPAT_MODEL"
        ):
            routing.resolve_model_route("openai_compatible")

    def test_invalid_and_unknown_routes_are_provider_neutral(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown external model route"):
            routing.resolve_model_route("surprise")

        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER"] = "compatible-provider"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_MODEL"] = "compatible-model"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL"] = "https://compatible.example/v1"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV"] = "COMPATIBLE_API_KEY"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY"] = "many"
        with self.assertRaisesRegex(ValueError, "CONCURRENCY must be a positive integer"):
            routing.resolve_model_route("openai_compatible")


if __name__ == "__main__":
    unittest.main()
