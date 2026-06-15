"""Stable boundary for MCP tools this read-mostly server must not implement."""

from __future__ import annotations

UNSUPPORTED_MUTATION_TOOLS = {
    "delete_memory",
    "enable_hook",
    "forget_memory",
    "create_telepathy_handoff",
    "install_hook",
    "pull_sync",
    "push_sync",
    "repair_sync",
    "store_memory",
    "sync_pull",
    "sync_push",
    "sync_repair",
    "release_telepathy_handoff",
    "uninstall_hook",
    "update_memory",
    "write_memory",
}
