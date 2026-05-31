from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import sys
import unittest
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def script_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in SCRIPTS.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SCRIPTS).with_suffix("")
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        if parts:
            modules[".".join(parts)] = path
    return modules


def pyproject_py_modules() -> set[str]:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^py-modules\s*=\s*\[(.*?)^\]", text)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def import_targets_for_node(
    node: ast.AST,
    *,
    current_module: str,
    modules: dict[str, Path],
) -> set[str]:
    targets: set[str] = set()

    def add_if_known(name: str) -> None:
        if name in modules:
            targets.add(name)
        top_level = name.split(".", maxsplit=1)[0]
        if top_level in modules:
            targets.add(top_level)

    if isinstance(node, ast.Import):
        for alias in node.names:
            add_if_known(alias.name)
    elif isinstance(node, ast.ImportFrom) and node.module:
        if node.level:
            parent = current_module.split(".")[:-node.level]
            base = ".".join([*parent, node.module]) if parent else node.module
        else:
            base = node.module
        add_if_known(base)
        for alias in node.names:
            add_if_known(f"{base}.{alias.name}")
    elif isinstance(node, ast.ImportFrom) and node.level:
        parent = current_module.split(".")[:-node.level]
        for alias in node.names:
            add_if_known(".".join([*parent, alias.name]))
    return targets


def same_dir_import_edges(*, top_level_only: bool = False) -> dict[str, set[str]]:
    modules = script_modules()
    edges = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = tree.body if top_level_only else ast.walk(tree)
        for node in nodes:
            edges[name].update(
                import_targets_for_node(node, current_module=name, modules=modules)
            )
    return edges


def strongly_connected_components(edges: dict[str, set[str]]) -> list[list[str]]:
    index_by_node: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        index_by_node[node] = len(index_by_node)
        lowlink[node] = index_by_node[node]
        stack.append(node)
        on_stack.add(node)
        for target in edges[node]:
            if target not in index_by_node:
                visit(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], index_by_node[target])
        if lowlink[node] != index_by_node[node]:
            return
        component: list[str] = []
        while True:
            current = stack.pop()
            on_stack.remove(current)
            component.append(current)
            if current == node:
                break
        components.append(sorted(component))

    for node in edges:
        if node not in index_by_node:
            visit(node)
    return components


class ImportCouplingTests(unittest.TestCase):
    def test_scripts_have_no_same_dir_import_cycles(self) -> None:
        edges = same_dir_import_edges()
        cycles = [
            component
            for component in strongly_connected_components(edges)
            if len(component) > 1 or any(node in edges[node] for node in component)
        ]
        self.assertEqual(cycles, [])

    def test_registry_does_not_import_retrieval_at_module_load(self) -> None:
        edges = same_dir_import_edges(top_level_only=True)
        self.assertNotIn("retrieval", edges["registry"])

    def test_cli_facade_has_package_owner_and_compat_shim(self) -> None:
        import aippocampus_cli
        from aippocampus_runtime.cli import facade

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "cli" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "cli" / "facade.py",
        ]
        shim_path = SCRIPTS / "aippocampus_cli.py"

        for path in package_paths:
            self.assertTrue(path.exists(), path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.cli.facade", edges["aippocampus_cli"])
        self.assertIs(aippocampus_cli.main, facade.main)
        self.assertIs(aippocampus_cli.run_script, facade.run_script)
        self.assertEqual(facade.SCRIPT_DIR, SCRIPTS)

    def test_registry_storage_is_separate_from_registry_runner(self) -> None:
        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "registry" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "registry" / "provider.py",
            SCRIPTS / "aippocampus_runtime" / "registry" / "search.py",
            SCRIPTS / "aippocampus_runtime" / "registry" / "store.py",
        ]
        shim_paths = [
            SCRIPTS / "registry_provider.py",
            SCRIPTS / "registry_search.py",
            SCRIPTS / "registry_store.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)

        self.assertIn("aippocampus_runtime.registry.provider", edges["registry"])
        self.assertIn("aippocampus_runtime.registry.search", edges["registry"])
        self.assertIn("aippocampus_runtime.registry.store", edges["registry"])
        self.assertNotIn("registry_store", edges["registry"])
        self.assertNotIn("registry", edges["aippocampus_runtime.registry.store"])

        registry_source = (SCRIPTS / "registry.py").read_text(encoding="utf-8")
        store_source = package_paths[-1].read_text(encoding="utf-8")
        self.assertNotIn("def load_registry", registry_source)
        self.assertIn("def load_registry", store_source)
        self.assertNotIn("def save_registry", registry_source)
        self.assertIn("def save_registry", store_source)

    def test_object_storage_helpers_have_package_owner_and_compat_shims(self) -> None:
        import object_storage_client
        import object_storage_providers
        from aippocampus_runtime.sync.object_storage import client, providers

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "sync" / "object_storage" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "object_storage" / "client.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "object_storage" / "providers.py",
        ]
        shim_paths = [
            SCRIPTS / "object_storage_client.py",
            SCRIPTS / "object_storage_providers.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.sync.object_storage.client", edges["sync_object_storage"])
        self.assertNotIn("object_storage_client", edges["sync_object_storage"])
        self.assertIn(
            "aippocampus_runtime.sync.object_storage.providers",
            edges["aippocampus_runtime.sync.object_storage.client"],
        )
        self.assertNotIn(
            "object_storage_providers",
            edges["aippocampus_runtime.sync.object_storage.client"],
        )

        self.assertIs(object_storage_client.HttpObjectStoreClient, client.HttpObjectStoreClient)
        self.assertIs(
            object_storage_client.object_storage_client_for,
            client.object_storage_client_for,
        )
        self.assertIs(object_storage_providers.SigV4Auth, providers.SigV4Auth)
        self.assertIs(object_storage_providers.provider_config, providers.provider_config)

    def test_encrypted_sync_helpers_have_package_owner_and_compat_shims(self) -> None:
        import encrypted_sync_bundle
        import encrypted_sync_crypto
        import encrypted_sync_keys
        import encrypted_sync_migration
        import encrypted_sync_object_storage
        from aippocampus_runtime.sync.encrypted import (
            bundle,
            crypto,
            keys,
            migration,
            object_storage,
        )

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "sync" / "encrypted" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "encrypted" / "bundle.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "encrypted" / "crypto.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "encrypted" / "keys.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "encrypted" / "migration.py",
            SCRIPTS / "aippocampus_runtime" / "sync" / "encrypted" / "object_storage.py",
        ]
        shim_paths = [
            SCRIPTS / "encrypted_sync_bundle.py",
            SCRIPTS / "encrypted_sync_crypto.py",
            SCRIPTS / "encrypted_sync_keys.py",
            SCRIPTS / "encrypted_sync_migration.py",
            SCRIPTS / "encrypted_sync_object_storage.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.sync.encrypted.keys", edges["encrypted_sync_admin"])
        self.assertIn("aippocampus_runtime.sync.encrypted.migration", edges["encrypted_sync_admin"])
        self.assertNotIn("encrypted_sync_keys", edges["encrypted_sync_admin"])
        self.assertNotIn("encrypted_sync_migration", edges["encrypted_sync_admin"])
        self.assertIn(
            "aippocampus_runtime.sync.encrypted.keys",
            edges["aippocampus_runtime.sync.encrypted.bundle"],
        )
        self.assertIn(
            "aippocampus_runtime.sync.encrypted.crypto",
            edges["aippocampus_runtime.sync.encrypted.bundle"],
        )
        self.assertFalse(
            {
                "encrypted_sync_bundle",
                "encrypted_sync_crypto",
                "encrypted_sync_keys",
                "encrypted_sync_migration",
                "encrypted_sync_object_storage",
            }
            & edges["aippocampus_runtime.sync.encrypted.migration"]
        )

        sync_bundle_source = (SCRIPTS / "sync_bundle.py").read_text(encoding="utf-8")
        sync_object_source = (SCRIPTS / "sync_object_storage.py").read_text(encoding="utf-8")
        self.assertIn("aippocampus_runtime.sync.encrypted.bundle", sync_bundle_source)
        self.assertNotIn('import_module("encrypted_sync_bundle")', sync_bundle_source)
        self.assertIn("aippocampus_runtime.sync.encrypted.object_storage", sync_object_source)
        self.assertNotIn('import_module("encrypted_sync_object_storage")', sync_object_source)

        self.assertEqual(
            encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME,
            bundle.ENCRYPTED_SYNC_DIR_NAME,
        )
        self.assertIs(encrypted_sync_crypto.EncryptedSyncError, crypto.EncryptedSyncError)
        self.assertIs(encrypted_sync_keys.init_device_key, keys.init_device_key)
        self.assertIs(
            encrypted_sync_migration.inventory_plaintext_sync_dir,
            migration.inventory_plaintext_sync_dir,
        )
        self.assertIs(
            encrypted_sync_object_storage.encrypted_manifest_relative_path,
            object_storage.encrypted_manifest_relative_path,
        )

    def test_external_model_helpers_have_package_owner_and_compat_shims(self) -> None:
        import deepseek_model_routing
        import model_client
        from aippocampus_runtime.model import client, routing

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "model" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "model" / "client.py",
            SCRIPTS / "aippocampus_runtime" / "model" / "routing.py",
        ]
        shim_paths = [
            SCRIPTS / "model_client.py",
            SCRIPTS / "deepseek_model_routing.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        for source in [
            "semantic_recall_gate",
            "subconscious_worker",
            "aippocampus_runtime.dream.worker",
            "warm_ambient_recall",
        ]:
            self.assertNotIn("model_client", edges[source])
        self.assertIn(
            "aippocampus_runtime.model.client",
            edges["aippocampus_runtime.dream.worker"],
        )
        self.assertIn("aippocampus_runtime.model.routing", edges["semantic_recall_gate"])

        self.assertIs(model_client.ChatClientConfig, client.ChatClientConfig)
        self.assertIs(model_client.chat_json, client.chat_json)
        self.assertIs(deepseek_model_routing.resolve_model_route, routing.resolve_model_route)
        self.assertIs(deepseek_model_routing.ModelRoute, routing.ModelRoute)

    def test_coding_host_contract_has_package_owner_and_compat_shim(self) -> None:
        import coding_ticket_host_contract
        from aippocampus_runtime.coding import host_contract

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "coding" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "coding" / "host_contract.py",
        ]
        shim_path = SCRIPTS / "coding_ticket_host_contract.py"

        for path in package_paths:
            self.assertTrue(path.exists(), path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        self.assertIs(
            coding_ticket_host_contract.host_decision_for_ticket,
            host_contract.host_decision_for_ticket,
        )
        self.assertIs(
            coding_ticket_host_contract.describe_host_contract,
            host_contract.describe_host_contract,
        )
        self.assertIs(
            coding_ticket_host_contract.tune_activation_from_feedback,
            host_contract.tune_activation_from_feedback,
        )
        self.assertIs(coding_ticket_host_contract.main, host_contract.main)

    def test_coding_rejected_route_probes_have_package_owner_and_compat_shim(self) -> None:
        import coding_rejected_route_probes
        from aippocampus_runtime.coding import rejected_route_probes

        package_path = SCRIPTS / "aippocampus_runtime" / "coding" / "rejected_route_probes.py"
        shim_path = SCRIPTS / "coding_rejected_route_probes.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        self.assertIs(
            coding_rejected_route_probes.build_rejected_route_probe,
            rejected_route_probes.build_rejected_route_probe,
        )
        self.assertIs(
            coding_rejected_route_probes.run_rejected_route_fixture,
            rejected_route_probes.run_rejected_route_fixture,
        )
        self.assertIs(
            coding_rejected_route_probes.public_fixture_summary,
            rejected_route_probes.public_fixture_summary,
        )

    def test_subconscious_worker_has_package_owner_and_compat_shim(self) -> None:
        import subconscious_worker
        from aippocampus_runtime.subconscious import worker

        package_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "worker.py"
        shim_path = SCRIPTS / "subconscious_worker.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        worker_consumers = [
            "aippocampus_runtime.subconscious.agent",
            "aippocampus_runtime.subconscious.job_validation",
            "aippocampus_runtime.subconscious.jobs_config",
            "aippocampus_runtime.subconscious.validation_audit",
            "onboard_frontier",
            "semantic_recall_gate",
            "semantic_scope_suppressed_recovery",
            "subconscious_jobs",
            "subconscious_review",
            "warm_ambient_recall",
        ]
        for source in worker_consumers:
            self.assertIn("aippocampus_runtime.subconscious.worker", edges[source])
            self.assertNotIn("subconscious_worker", edges[source])

        self.assertIs(subconscious_worker.run_worker, worker.run_worker)
        self.assertIs(subconscious_worker.select_timeline_turns, worker.select_timeline_turns)
        self.assertIs(subconscious_worker.clamp_confidence, worker.clamp_confidence)
        self.assertIs(subconscious_worker.main, worker.main)

    def test_subconscious_scheduler_has_package_owner_and_compat_shim(self) -> None:
        import subconscious_scheduler
        from aippocampus_runtime.subconscious import scheduler

        package_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "scheduler.py"
        shim_path = SCRIPTS / "subconscious_scheduler.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        self.assertIs(subconscious_scheduler.maybe_start, scheduler.maybe_start)
        self.assertIs(subconscious_scheduler.run_due, scheduler.run_due)
        self.assertIs(subconscious_scheduler.run_project, scheduler.run_project)
        self.assertIs(subconscious_scheduler.main, scheduler.main)
        self.assertEqual(scheduler.SCRIPT_DIR, SCRIPTS)

    def test_dream_delivery_policy_has_package_owner_and_compat_shim(self) -> None:
        import dream_delivery_policy
        from aippocampus_runtime.dream import delivery_policy

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "dream" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "dream" / "delivery_policy.py",
        ]
        shim_path = SCRIPTS / "dream_delivery_policy.py"

        for path in package_paths:
            self.assertTrue(path.exists(), path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        prompt_hook_source = (SCRIPTS / "aippocampus_prompt_hook.py").read_text(encoding="utf-8")
        self.assertIn("aippocampus_runtime.dream import delivery_policy", prompt_hook_source)
        self.assertNotIn("dream_delivery_policy", edges["aippocampus_prompt_hook"])

        self.assertIs(
            dream_delivery_policy.prepare_dream_delivery,
            delivery_policy.prepare_dream_delivery,
        )
        self.assertIs(
            dream_delivery_policy.add_dream_delivery_arguments,
            delivery_policy.add_dream_delivery_arguments,
        )

    def test_dream_worker_contract_has_package_owner_and_compat_shim(self) -> None:
        import dream_worker_contract
        from aippocampus_runtime.dream import worker_contract

        package_path = SCRIPTS / "aippocampus_runtime" / "dream" / "worker_contract.py"
        shim_path = SCRIPTS / "dream_worker_contract.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.dream.worker_contract",
            edges["aippocampus_runtime.dream.worker"],
        )
        self.assertNotIn(
            "dream_worker_contract",
            edges["aippocampus_runtime.dream.worker"],
        )

        self.assertEqual(dream_worker_contract.PROMPT_VERSION, worker_contract.PROMPT_VERSION)
        self.assertIs(
            dream_worker_contract.stable_worker_contract,
            worker_contract.stable_worker_contract,
        )
        self.assertIs(
            dream_worker_contract.variable_run_directive,
            worker_contract.variable_run_directive,
        )

    def test_dream_precision_policy_has_package_owner_and_compat_shim(self) -> None:
        import dream_precision_policy
        from aippocampus_runtime.dream import precision_policy

        package_path = SCRIPTS / "aippocampus_runtime" / "dream" / "precision_policy.py"
        shim_path = SCRIPTS / "dream_precision_policy.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        for source in [
            "aippocampus_runtime.dream.retrospective_lifecycle",
            "aippocampus_runtime.dream.sleep_cycle",
        ]:
            self.assertIn("aippocampus_runtime.dream.precision_policy", edges[source])
            self.assertNotIn("dream_precision_policy", edges[source])

        self.assertIs(
            dream_precision_policy.retention_policy_for_probe,
            precision_policy.retention_policy_for_probe,
        )
        self.assertIs(
            dream_precision_policy.activation_policy_for_row,
            precision_policy.activation_policy_for_row,
        )
        self.assertIs(
            dream_precision_policy.retrospective_policy_for_probe,
            precision_policy.retrospective_policy_for_probe,
        )

    def test_dream_sleep_cycle_has_package_owner_and_compat_shim(self) -> None:
        import dream_sleep_cycle
        from aippocampus_runtime.dream import sleep_cycle

        package_path = SCRIPTS / "aippocampus_runtime" / "dream" / "sleep_cycle.py"
        shim_path = SCRIPTS / "dream_sleep_cycle.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.dream.precision_policy",
            edges["aippocampus_runtime.dream.sleep_cycle"],
        )
        self.assertNotIn("dream_precision_policy", edges["aippocampus_runtime.dream.sleep_cycle"])

        self.assertIs(dream_sleep_cycle.run_sleep_cycle, sleep_cycle.run_sleep_cycle)
        self.assertIs(
            dream_sleep_cycle.public_sleep_cycle_summary,
            sleep_cycle.public_sleep_cycle_summary,
        )

    def test_dream_queue_has_package_owner_and_compat_shim(self) -> None:
        import dream_queue
        from aippocampus_runtime.dream import queue

        package_path = SCRIPTS / "aippocampus_runtime" / "dream" / "queue.py"
        shim_path = SCRIPTS / "dream_queue.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.dream.queue",
            edges["aippocampus_runtime.dream.sleep_cycle"],
        )
        self.assertNotIn("dream_queue", edges["aippocampus_runtime.dream.sleep_cycle"])

        self.assertIs(dream_queue.build_dream_queue, queue.build_dream_queue)
        self.assertIs(dream_queue.public_queue_summary, queue.public_queue_summary)
        self.assertIs(dream_queue.main, queue.main)

    def test_dream_core_helpers_have_package_owner_and_compat_shims(self) -> None:
        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "dream" / "input_pack.py",
            SCRIPTS / "aippocampus_runtime" / "dream" / "worker.py",
            SCRIPTS / "aippocampus_runtime" / "dream" / "working_memory.py",
        ]
        shim_paths = [
            SCRIPTS / "dream_input_pack.py",
            SCRIPTS / "dream_worker.py",
            SCRIPTS / "dream_working_memory.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        import dream_input_pack
        import dream_worker
        import dream_working_memory
        from aippocampus_runtime.dream import input_pack, worker, working_memory

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.dream.input_pack",
            edges["aippocampus_runtime.dream.sleep_cycle"],
        )
        self.assertIn(
            "aippocampus_runtime.dream.worker",
            edges["aippocampus_runtime.dream.sleep_cycle"],
        )
        self.assertNotIn("dream_input_pack", edges["aippocampus_runtime.dream.sleep_cycle"])
        self.assertNotIn("dream_worker", edges["aippocampus_runtime.dream.sleep_cycle"])
        self.assertIn(
            "aippocampus_runtime.dream.working_memory",
            edges["aippocampus_runtime.dream.worker"],
        )
        self.assertNotIn("dream_working_memory", edges["aippocampus_runtime.dream.worker"])
        self.assertIn("aippocampus_runtime.dream.worker", edges["dream_real_history_eval"])
        self.assertIn(
            "aippocampus_runtime.dream.working_memory",
            edges["dream_real_history_eval"],
        )
        self.assertNotIn("dream_worker", edges["dream_real_history_eval"])
        self.assertNotIn("dream_working_memory", edges["dream_real_history_eval"])
        self.assertIn(
            "aippocampus_runtime.dream.working_memory",
            edges["compensatory_dream"],
        )
        self.assertNotIn("dream_working_memory", edges["compensatory_dream"])

        self.assertIs(
            dream_input_pack.build_dream_input_pack,
            input_pack.build_dream_input_pack,
        )
        self.assertIs(
            dream_worker.run_model_backed_dream_worker,
            worker.run_model_backed_dream_worker,
        )
        self.assertIs(
            dream_working_memory.background_adjudicate_dream_findings,
            working_memory.background_adjudicate_dream_findings,
        )

    def test_dream_one_sidedness_has_package_owner_and_compat_shim(self) -> None:
        import dream_one_sidedness
        from aippocampus_runtime.dream import one_sidedness

        package_path = SCRIPTS / "aippocampus_runtime" / "dream" / "one_sidedness.py"
        shim_path = SCRIPTS / "dream_one_sidedness.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        self.assertIs(
            dream_one_sidedness.evaluate_one_sidedness_gate,
            one_sidedness.evaluate_one_sidedness_gate,
        )
        self.assertIs(
            dream_one_sidedness.build_opposite_hexagram_probe,
            one_sidedness.build_opposite_hexagram_probe,
        )
        self.assertIs(
            dream_one_sidedness.compute_opposite_arc,
            one_sidedness.compute_opposite_arc,
        )
        self.assertIs(dream_one_sidedness.main, one_sidedness.main)

    def test_dream_retrospective_lifecycle_has_package_owner_and_compat_shim(self) -> None:
        import dream_retrospective_lifecycle
        from aippocampus_runtime.dream import retrospective_lifecycle

        package_path = SCRIPTS / "aippocampus_runtime" / "dream" / "retrospective_lifecycle.py"
        shim_path = SCRIPTS / "dream_retrospective_lifecycle.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.dream.retrospective_lifecycle",
            edges["aippocampus_runtime.coding.rejected_route_probes"],
        )
        self.assertNotIn(
            "dream_retrospective_lifecycle",
            edges["aippocampus_runtime.coding.rejected_route_probes"],
        )

        self.assertIs(
            dream_retrospective_lifecycle.run_retrospective_lifecycle,
            retrospective_lifecycle.run_retrospective_lifecycle,
        )
        self.assertIs(
            dream_retrospective_lifecycle.public_lifecycle_summary,
            retrospective_lifecycle.public_lifecycle_summary,
        )
        self.assertIs(dream_retrospective_lifecycle.main, retrospective_lifecycle.main)

    def test_subconscious_job_storage_has_package_owner_and_compat_shim(self) -> None:
        import subconscious_job_storage
        from aippocampus_runtime.subconscious import job_storage

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "subconscious" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "subconscious" / "job_storage.py",
        ]
        shim_path = SCRIPTS / "subconscious_job_storage.py"

        for path in package_paths:
            self.assertTrue(path.exists(), path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.subconscious.job_storage", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_job_storage", edges["subconscious_jobs"])

        self.assertIs(
            subconscious_job_storage.append_job_findings,
            job_storage.append_job_findings,
        )
        self.assertIs(
            subconscious_job_storage.concept_findings_to_edges,
            job_storage.concept_findings_to_edges,
        )

    def test_subconscious_job_plan_has_package_owner_and_compat_shim(self) -> None:
        import subconscious_job_plan
        from aippocampus_runtime.subconscious import job_plan

        package_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "job_plan.py"
        shim_path = SCRIPTS / "subconscious_job_plan.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.subconscious.job_plan", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_job_plan", edges["subconscious_jobs"])

        self.assertIs(subconscious_job_plan.JobRunTask, job_plan.JobRunTask)
        self.assertIs(subconscious_job_plan.plan_job_run_tasks, job_plan.plan_job_run_tasks)
        self.assertIs(
            subconscious_job_plan.run_tasks_in_sample_waves,
            job_plan.run_tasks_in_sample_waves,
        )

    def test_subconscious_jobs_config_has_package_owner_and_compat_shim(self) -> None:
        import subconscious_jobs_config
        from aippocampus_runtime.subconscious import jobs_config

        package_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "jobs_config.py"
        shim_path = SCRIPTS / "subconscious_jobs_config.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        for source in ["subconscious_jobs", "question_tracking", "theme_emergence"]:
            self.assertIn("aippocampus_runtime.subconscious.jobs_config", edges[source])
            self.assertNotIn("subconscious_jobs_config", edges[source])

        self.assertIs(subconscious_jobs_config.JobsRunConfig, jobs_config.JobsRunConfig)
        self.assertIs(
            subconscious_jobs_config.jobs_run_config_from_args,
            jobs_config.jobs_run_config_from_args,
        )
        self.assertIs(
            subconscious_jobs_config.default_jobs_output_path,
            jobs_config.default_jobs_output_path,
        )

    def test_question_helpers_have_package_owner_and_compat_shims(self) -> None:
        import question_feedback_policy
        import question_source_refs
        import question_vector_index
        from aippocampus_runtime.question import feedback_policy, source_refs, vector_index

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "question" / "__init__.py",
            SCRIPTS / "aippocampus_runtime" / "question" / "feedback_policy.py",
            SCRIPTS / "aippocampus_runtime" / "question" / "source_refs.py",
            SCRIPTS / "aippocampus_runtime" / "question" / "vector_index.py",
        ]
        shim_paths = [
            SCRIPTS / "question_feedback_policy.py",
            SCRIPTS / "question_source_refs.py",
            SCRIPTS / "question_vector_index.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        for source in [
            "agency_affordance",
            "coding_decision_events",
            "correction_reconsolidation",
            "question_health",
            "question_index_sidecar",
            "question_resolution",
            "question_tracking",
            "theme_emergence",
        ]:
            self.assertIn("aippocampus_runtime.question.source_refs", edges[source])
            self.assertNotIn("question_source_refs", edges[source])
        self.assertIn("aippocampus_runtime.question.feedback_policy", edges["question_tracking"])
        self.assertNotIn("question_feedback_policy", edges["question_tracking"])

        modules = pyproject_py_modules()
        self.assertTrue(
            {"question_feedback_policy", "question_source_refs", "question_vector_index"}
            <= modules
        )

        self.assertIs(question_source_refs.source_ref_key, source_refs.source_ref_key)
        self.assertIs(
            question_feedback_policy.load_question_pair_feedback,
            feedback_policy.load_question_pair_feedback,
        )
        self.assertIs(
            question_vector_index.LocalQuestionVectorIndex,
            vector_index.LocalQuestionVectorIndex,
        )

    def test_subconscious_validation_audit_has_package_owner_and_compat_shim(self) -> None:
        import subconscious_validation_audit
        from aippocampus_runtime.subconscious import validation_audit

        package_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "validation_audit.py"
        shim_path = SCRIPTS / "subconscious_validation_audit.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.subconscious.validation_audit", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_validation_audit", edges["subconscious_jobs"])

        self.assertIs(
            subconscious_validation_audit.validation_audit,
            validation_audit.validation_audit,
        )
        self.assertIs(
            subconscious_validation_audit.validation_rejection_reason,
            validation_audit.validation_rejection_reason,
        )

    def test_subconscious_deterministic_jobs_have_package_owner_and_compat_shim(self) -> None:
        import subconscious_deterministic_jobs
        from aippocampus_runtime.subconscious import deterministic_jobs

        package_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "deterministic_jobs.py"
        shim_path = SCRIPTS / "subconscious_deterministic_jobs.py"

        self.assertTrue(package_path.exists(), package_path)
        self.assertTrue(shim_path.exists(), shim_path)
        self.assertIn("Compatibility shim", shim_path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn("aippocampus_runtime.subconscious.deterministic_jobs", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_deterministic_jobs", edges["subconscious_jobs"])

        self.assertIs(
            subconscious_deterministic_jobs.run_deterministic_job,
            deterministic_jobs.run_deterministic_job,
        )
        self.assertEqual(
            subconscious_deterministic_jobs.DETERMINISTIC_RUNNERS,
            deterministic_jobs.DETERMINISTIC_RUNNERS,
        )

    def test_subconscious_job_contracts_have_package_owner_and_compat_shims(self) -> None:
        import subconscious_job_circuits
        import subconscious_job_validation
        import subconscious_question_diagnostics
        from aippocampus_runtime.subconscious import (
            job_circuits,
            job_validation,
            question_diagnostics,
        )

        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "subconscious" / "question_diagnostics.py",
            SCRIPTS / "aippocampus_runtime" / "subconscious" / "job_circuits.py",
            SCRIPTS / "aippocampus_runtime" / "subconscious" / "job_validation.py",
        ]
        shim_paths = [
            SCRIPTS / "subconscious_question_diagnostics.py",
            SCRIPTS / "subconscious_job_circuits.py",
            SCRIPTS / "subconscious_job_validation.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.subconscious.question_diagnostics",
            edges["aippocampus_runtime.subconscious.job_circuits"],
        )
        self.assertNotIn(
            "subconscious_question_diagnostics",
            edges["aippocampus_runtime.subconscious.job_circuits"],
        )
        self.assertIn(
            "aippocampus_runtime.subconscious.job_circuits",
            edges["aippocampus_runtime.subconscious.job_validation"],
        )
        self.assertNotIn(
            "subconscious_job_circuits",
            edges["aippocampus_runtime.subconscious.job_validation"],
        )
        for source in [
            "aippocampus_runtime.subconscious.job_storage",
            "aippocampus_runtime.subconscious.jobs_config",
            "aippocampus_runtime.subconscious.validation_audit",
            "subconscious_jobs",
        ]:
            self.assertIn("aippocampus_runtime.subconscious.job_circuits", edges[source])
            self.assertNotIn("subconscious_job_circuits", edges[source])
        for source in [
            "aippocampus_runtime.subconscious.validation_audit",
            "subconscious_jobs",
            "subconscious_review",
        ]:
            self.assertIn("aippocampus_runtime.subconscious.job_validation", edges[source])
            self.assertNotIn("subconscious_job_validation", edges[source])
        self.assertIn(
            "aippocampus_runtime.subconscious.question_diagnostics",
            edges["subconscious_jobs"],
        )
        self.assertNotIn("subconscious_question_diagnostics", edges["subconscious_jobs"])

        self.assertIs(subconscious_job_circuits.JOB_SPECS, job_circuits.JOB_SPECS)
        self.assertIs(subconscious_job_circuits.job_names, job_circuits.job_names)
        self.assertIs(
            subconscious_job_validation.validate_findings,
            job_validation.validate_findings,
        )
        self.assertIs(
            subconscious_question_diagnostics.question_extraction_quality_diagnostics,
            question_diagnostics.question_extraction_quality_diagnostics,
        )

    def test_prompt_recall_core_stays_small_foreground_gate(self) -> None:
        edges = same_dir_import_edges()
        forbidden = {
            "build_associations",
            "build_cognitive_map",
            "build_concept_graph",
            "memory_candidate_router",
            "semantic_recall_gate",
        }
        self.assertLessEqual(len(edges["prompt_recall_core"]), 4)
        self.assertFalse(forbidden & edges["prompt_recall_core"])

    def test_prompt_recall_cues_are_separate_from_scoring_policy(self) -> None:
        cues_path = SCRIPTS / "prompt_cues.py"
        self.assertTrue(cues_path.exists())
        edges = same_dir_import_edges(top_level_only=True)

        self.assertIn("prompt_cues", edges["prompt_recall_core"])
        self.assertFalse(
            {
                "prompt_recall_core",
                "registry",
                "search_clean_source",
                "semantic_recall_gate",
            }
            & edges["prompt_cues"]
        )

        core_source = (SCRIPTS / "prompt_recall_core.py").read_text(encoding="utf-8")
        cues_source = cues_path.read_text(encoding="utf-8")
        self.assertIn("CUE_COMPAT_EXPORTS", core_source)
        self.assertNotIn("def matched_terms", core_source)
        self.assertIn("def matched_terms", cues_source)
        self.assertNotIn("CODE_SURFACE_CUES = {", core_source)
        self.assertIn("CODE_SURFACE_CUES =", cues_source)

        cue_compat_names = {
            "ASSOCIATIVE_CUES",
            "CONCEPT_EXPANSION_MAX_TERMS",
            "IMPORTANCE_CUES",
            "association_term_is_generic",
            "concept_expansion_terms",
            "expand_query_terms",
            "explicit_recall_terms",
            "is_decision_continuation",
            "matched_terms",
            "semantic_gate_can_request_evidence",
            "semantic_gate_is_memory_cue",
            "semantic_gate_terms",
            "should_run_semantic_gate",
            "working_memory_terms",
        }
        for rel_path in ("prompt_recall_context.py", "prompt_recall_decision.py"):
            tree = ast.parse((SCRIPTS / rel_path).read_text(encoding="utf-8"))
            imported_from_core = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "prompt_recall_core"
                for alias in node.names
            }
            self.assertFalse(cue_compat_names & imported_from_core)

    def test_prompt_life_cues_have_package_owner_and_compat_shim(self) -> None:
        import prompt_life_cues
        from aippocampus_runtime.recall import life_cues

        package_file = SCRIPTS / "aippocampus_runtime" / "recall" / "life_cues.py"
        shim_file = SCRIPTS / "prompt_life_cues.py"
        self.assertTrue(package_file.exists())
        self.assertTrue(shim_file.exists())
        self.assertIn("Compatibility shim", shim_file.read_text(encoding="utf-8"))

        edges = same_dir_import_edges(top_level_only=True)
        for source in [
            "aippocampus_runtime.recall.active_recall",
            "aippocampus_runtime.recall.retrieval",
            "prompt_cues",
        ]:
            self.assertIn("aippocampus_runtime.recall.life_cues", edges[source])
            self.assertNotIn("prompt_life_cues", edges[source])

        self.assertIs(prompt_life_cues.profile_recall_terms, life_cues.profile_recall_terms)
        self.assertIs(
            prompt_life_cues.LIFE_WIDE_SCOPE_LABEL_CUES,
            life_cues.LIFE_WIDE_SCOPE_LABEL_CUES,
        )

    def test_recall_runtime_core_has_package_owner_and_compat_shims(self) -> None:
        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "recall" / "active_recall.py",
            SCRIPTS / "aippocampus_runtime" / "recall" / "query_policy.py",
            SCRIPTS / "aippocampus_runtime" / "recall" / "retrieval.py",
            SCRIPTS / "aippocampus_runtime" / "recall" / "score_fusion.py",
        ]
        shim_paths = [
            SCRIPTS / "active_recall.py",
            SCRIPTS / "retrieval.py",
            SCRIPTS / "retrieval_query_policy.py",
            SCRIPTS / "retrieval_score_fusion.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        import active_recall
        import retrieval
        import retrieval_query_policy
        import retrieval_score_fusion
        from aippocampus_runtime.recall import (
            active_recall as packaged_active_recall,
        )
        from aippocampus_runtime.recall import (
            query_policy,
            score_fusion,
        )
        from aippocampus_runtime.recall import (
            retrieval as packaged_retrieval,
        )

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.recall.retrieval",
            edges["aippocampus_runtime.recall.active_recall"],
        )
        self.assertIn(
            "aippocampus_runtime.recall.query_policy",
            edges["aippocampus_runtime.recall.retrieval"],
        )
        self.assertIn(
            "aippocampus_runtime.recall.score_fusion",
            edges["aippocampus_runtime.recall.retrieval"],
        )

        flat_recall_modules = {
            "active_recall",
            "retrieval",
            "retrieval_query_policy",
            "retrieval_score_fusion",
            "prompt_life_cues",
        }
        offenders = {
            source: sorted(targets & flat_recall_modules)
            for source, targets in edges.items()
            if source not in flat_recall_modules and targets & flat_recall_modules
        }
        self.assertEqual(offenders, {})

        self.assertIs(
            active_recall.active_recall_query_terms,
            packaged_active_recall.active_recall_query_terms,
        )
        self.assertIs(retrieval.active_recall_decision, packaged_retrieval.active_recall_decision)
        self.assertIs(retrieval_query_policy.split_query_terms, query_policy.split_query_terms)
        self.assertIs(
            retrieval_score_fusion.retrieval_text_score,
            score_fusion.retrieval_text_score,
        )

    def test_ambient_recall_helpers_have_package_owner_and_compat_shims(self) -> None:
        package_paths = [
            SCRIPTS / "aippocampus_runtime" / "recall" / "ambient_cache.py",
            SCRIPTS / "aippocampus_runtime" / "recall" / "ambient_cards.py",
            SCRIPTS / "aippocampus_runtime" / "recall" / "ambient_policy.py",
        ]
        shim_paths = [
            SCRIPTS / "ambient_thread_cache.py",
            SCRIPTS / "ambient_recall_cards.py",
            SCRIPTS / "ambient_recall_policy.py",
        ]

        for path in package_paths + shim_paths:
            self.assertTrue(path.exists(), path)
        for path in shim_paths:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        import ambient_recall_cards
        import ambient_recall_policy
        import ambient_thread_cache
        from aippocampus_runtime.recall import ambient_cache, ambient_cards, ambient_policy

        edges = same_dir_import_edges(top_level_only=True)
        self.assertIn(
            "aippocampus_runtime.recall.ambient_policy",
            edges["aippocampus_runtime.recall.ambient_cards"],
        )
        flat_ambient_modules = {
            "ambient_thread_cache",
            "ambient_recall_cards",
            "ambient_recall_policy",
        }
        offenders = {
            source: sorted(targets & flat_ambient_modules)
            for source, targets in edges.items()
            if source not in flat_ambient_modules and targets & flat_ambient_modules
        }
        self.assertEqual(offenders, {})

        self.assertIs(
            ambient_thread_cache.default_ambient_cache_path,
            ambient_cache.default_ambient_cache_path,
        )
        self.assertIs(
            ambient_recall_cards.ambient_recall_from_decision,
            ambient_cards.ambient_recall_from_decision,
        )
        self.assertIs(
            ambient_recall_policy.policy_update_for_prompt,
            ambient_policy.policy_update_for_prompt,
        )

    def test_subconscious_jobs_do_not_depend_on_agent_runner(self) -> None:
        package_agent_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "agent.py"
        shim_agent_path = SCRIPTS / "subconscious_agent.py"
        package_runtime_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "runtime.py"
        shim_runtime_path = SCRIPTS / "subconscious_runtime.py"
        package_loop_path = SCRIPTS / "aippocampus_runtime" / "subconscious" / "tool_loop.py"
        shim_loop_path = SCRIPTS / "subconscious_tool_loop.py"
        self.assertTrue(package_agent_path.exists())
        self.assertTrue(shim_agent_path.exists())
        self.assertTrue(package_runtime_path.exists())
        self.assertTrue(shim_runtime_path.exists())
        self.assertTrue(package_loop_path.exists())
        self.assertTrue(shim_loop_path.exists())
        self.assertIn("Compatibility shim", shim_agent_path.read_text(encoding="utf-8"))
        self.assertIn("Compatibility shim", shim_runtime_path.read_text(encoding="utf-8"))
        self.assertIn("Compatibility shim", shim_loop_path.read_text(encoding="utf-8"))

        import subconscious_agent
        import subconscious_runtime
        import subconscious_tool_loop
        from aippocampus_runtime.subconscious import agent, runtime, tool_loop

        edges = same_dir_import_edges(top_level_only=True)

        self.assertIn("aippocampus_runtime.subconscious.agent", edges["subconscious_agent"])
        self.assertNotIn("aippocampus_runtime.subconscious.tool_loop", edges["subconscious_agent"])
        self.assertIn(
            "aippocampus_runtime.subconscious.tool_loop",
            edges["aippocampus_runtime.subconscious.agent"],
        )
        runtime_consumers = [
            "aippocampus_runtime.subconscious.agent",
            "aippocampus_runtime.subconscious.tool_loop",
            "semantic_recall_gate",
            "semantic_scope_suppressed_recovery",
            "subconscious_jobs",
            "subconscious_review",
            "warm_ambient_recall",
        ]
        for source in runtime_consumers:
            self.assertIn("aippocampus_runtime.subconscious.runtime", edges[source])
            self.assertNotIn("subconscious_runtime", edges[source])
        self.assertIn("aippocampus_runtime.subconscious.tool_loop", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_tool_loop", edges["subconscious_agent"])
        self.assertNotIn("subconscious_tool_loop", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_agent", edges["subconscious_jobs"])
        self.assertFalse(
            {"subconscious_jobs", "subconscious_review"}
            & edges["aippocampus_runtime.subconscious.agent"]
        )
        self.assertFalse(
            {"subconscious_agent", "subconscious_jobs"}
            & edges["aippocampus_runtime.subconscious.runtime"]
        )
        self.assertFalse(
            {"subconscious_agent", "subconscious_jobs"}
            & edges["aippocampus_runtime.subconscious.tool_loop"]
        )
        self.assertIs(subconscious_agent.AgentRunConfig, agent.AgentRunConfig)
        self.assertIs(subconscious_agent.run_agent, agent.run_agent)
        self.assertIs(subconscious_agent.main, agent.main)
        self.assertIs(subconscious_runtime.AgentState, runtime.AgentState)
        self.assertIs(subconscious_runtime.run_tool, runtime.run_tool)
        self.assertIs(subconscious_tool_loop.ToolLoopResult, tool_loop.ToolLoopResult)
        self.assertIs(subconscious_tool_loop.run_tool_using_loop, tool_loop.run_tool_using_loop)

    def test_runtime_scripts_do_not_import_smoke_modules(self) -> None:
        edges = same_dir_import_edges()
        offenders = {
            source: sorted(target for target in targets if target.startswith("smoke_"))
            for source, targets in edges.items()
            if not source.startswith(("benchmark_", "smoke_")) and source != "run_stage_0_5_smoke"
        }
        offenders = {source: targets for source, targets in offenders.items() if targets}

        self.assertEqual(offenders, {})

    def test_warm_ambient_helpers_have_package_owner_and_compat_shims(self) -> None:
        import warm_ambient_prompting
        import warm_ambient_scout_profiles
        import warm_ambient_source_validation
        from aippocampus_runtime.warm_ambient import prompting, scout_profiles, source_validation

        package_files = [
            SCRIPTS / "aippocampus_runtime" / "warm_ambient" / "prompting.py",
            SCRIPTS / "aippocampus_runtime" / "warm_ambient" / "scout_profiles.py",
            SCRIPTS / "aippocampus_runtime" / "warm_ambient" / "source_validation.py",
        ]
        shim_files = [
            SCRIPTS / "warm_ambient_prompting.py",
            SCRIPTS / "warm_ambient_scout_profiles.py",
            SCRIPTS / "warm_ambient_source_validation.py",
        ]

        for path in package_files + shim_files:
            self.assertTrue(path.exists(), path)
        for path in shim_files:
            self.assertIn("Compatibility shim", path.read_text(encoding="utf-8"))

        self.assertIs(warm_ambient_prompting.scout_prompt, prompting.scout_prompt)
        self.assertIs(
            warm_ambient_scout_profiles.expand_scout_lanes,
            scout_profiles.expand_scout_lanes,
        )
        self.assertIs(
            warm_ambient_source_validation.calibrate_cards,
            source_validation.calibrate_cards,
        )
        self.assertIs(
            warm_ambient_source_validation._stable_id,
            source_validation._stable_id,
        )

    def test_sync_contract_has_package_owner_and_compat_shim(self) -> None:
        import sync_contract
        from aippocampus_runtime.sync import contract

        package_file = SCRIPTS / "aippocampus_runtime" / "sync" / "contract.py"
        shim_file = SCRIPTS / "sync_contract.py"

        self.assertTrue(package_file.exists())
        self.assertTrue(shim_file.exists())
        self.assertIn("Compatibility shim", shim_file.read_text(encoding="utf-8"))
        self.assertIs(sync_contract.build_sync_manifest, contract.build_sync_manifest)
        self.assertIs(sync_contract.sync_privacy_boundary, contract.sync_privacy_boundary)
        self.assertEqual(sync_contract.SYNC_BUNDLE_KIND, contract.SYNC_BUNDLE_KIND)

    def test_repo_import_shims_delegate_to_single_helper(self) -> None:
        helper_path = REPO_ROOT / "tools" / "aippocampus" / "repo_paths.py"
        wrapper_paths = [
            REPO_ROOT / "tools" / "aippocampus" / "docs" / "_paths.py",
            REPO_ROOT / "tools" / "aippocampus" / "smoke" / "_paths.py",
            REPO_ROOT / "benchmarks" / "aippocampus" / "_paths.py",
        ]

        self.assertTrue(helper_path.exists())
        self.assertIn(
            "def ensure_repo_imports",
            helper_path.read_text(encoding="utf-8"),
        )
        for path in wrapper_paths:
            source = path.read_text(encoding="utf-8")
            self.assertIn("repo_paths.py", source)
            self.assertNotIn("sys.path.insert", source)

    def test_repo_import_helper_supports_compat_wrappers(self) -> None:
        helper = load_module_from_path(
            "aippocampus_repo_paths_test",
            REPO_ROOT / "tools" / "aippocampus" / "repo_paths.py",
        )
        paths = helper.ensure_repo_imports(
            REPO_ROOT / "benchmarks" / "aippocampus" / "_paths.py",
            include_smoke_tools=True,
        )

        self.assertEqual(paths.repo_root, REPO_ROOT)
        self.assertIn(str(paths.skill_scripts), sys.path)
        self.assertIn(str(paths.smoke_tools), sys.path)

        for name, path in {
            "docs_paths_test": REPO_ROOT / "tools" / "aippocampus" / "docs" / "_paths.py",
            "smoke_paths_test": REPO_ROOT / "tools" / "aippocampus" / "smoke" / "_paths.py",
            "benchmark_paths_test": REPO_ROOT / "benchmarks" / "aippocampus" / "_paths.py",
        }.items():
            wrapper = load_module_from_path(name, path)
            self.assertEqual(wrapper.REPO_ROOT, REPO_ROOT)
            self.assertEqual(wrapper.SKILL_SCRIPTS, SCRIPTS)
            wrapper.ensure_paths()

    def test_installed_skill_direct_script_help_does_not_need_repo_bootstrap(self) -> None:
        with TemporaryDirectory() as tmp:
            installed_scripts = Path(tmp) / "skills" / "aippocampus" / "scripts"
            shutil.copytree(SCRIPTS, installed_scripts)

            result = run(
                [
                    sys.executable,
                    str(installed_scripts / "aippocampus_health.py"),
                    "--help",
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: aippocampus_health.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
