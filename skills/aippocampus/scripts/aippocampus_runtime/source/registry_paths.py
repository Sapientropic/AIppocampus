"""Portable registry member path resolution for source-derived artifacts."""

from __future__ import annotations

from pathlib import Path


def resolve_registry_member_path(
    value: str | None, registry_path: Path | None = None
) -> Path | None:
    if not value:
        return None
    path = Path(str(value).replace("\\", "/"))
    if path.is_absolute() or registry_path is None:
        return path
    if path.drive or ".." in path.parts:
        return None

    # Public bundles keep registry/threads.json beside clean-source/ and index/
    # at the bundle root. Machine registries usually store absolute paths, but
    # portable examples and exports need relative paths to remain useful after
    # moving between machines. Source sidecar builders use this helper instead
    # of importing the timeline maintenance script just for path repair.
    registry_root = registry_path.resolve().parent
    bundle_root = registry_root.parent
    candidates = [(registry_root, registry_root / path)]
    if bundle_root != registry_root:
        candidates.append((bundle_root, bundle_root / path))
    for root, candidate in candidates:
        resolved = candidate.resolve()
        resolved_root = root.resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            continue
        if resolved.exists():
            return resolved
    return candidates[0][1]

