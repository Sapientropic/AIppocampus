"""Codex hook entrypoints and installers for AIppocampus.

Top-level hook scripts remain direct-path compatibility shims because Codex
stores hook commands as script paths. Runtime code should import these package
owners so hook behavior does not keep growing in the flat script directory.
"""
