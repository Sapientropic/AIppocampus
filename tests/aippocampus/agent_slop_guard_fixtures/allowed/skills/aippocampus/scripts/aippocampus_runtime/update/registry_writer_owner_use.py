from aippocampus_runtime.registry.store import update_registry


def repair_registry(json_path, md_path, entry):
    def updater(registry):
        registry.setdefault("threads", []).append(entry)
        return registry

    return update_registry(json_path, md_path, updater)
