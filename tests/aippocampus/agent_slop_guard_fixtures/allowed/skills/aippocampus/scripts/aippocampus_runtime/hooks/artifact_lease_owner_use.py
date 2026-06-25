from aippocampus_runtime.artifacts.publish import artifact_lease


def publish(path, payload):
    with artifact_lease(path.parent, f".{path.name}.lease"):
        path.write_text(payload, encoding="utf-8")
