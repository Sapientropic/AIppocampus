from aippocampus_runtime.registry.store import load_registry, save_registry


def repair_registry(json_path, md_path, entry):
    registry = load_registry(json_path)
    registry.setdefault("threads", []).append(entry)
    save_registry(registry, json_path, md_path)
