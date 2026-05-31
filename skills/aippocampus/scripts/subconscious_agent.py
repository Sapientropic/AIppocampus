#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious agent runner."""

from __future__ import annotations

from aippocampus_runtime.subconscious.agent import (
    PROMPT_VERSION as PROMPT_VERSION,
)
from aippocampus_runtime.subconscious.agent import AgentRunConfig as AgentRunConfig
from aippocampus_runtime.subconscious.agent import (
    agent_initial_payload as agent_initial_payload,
)
from aippocampus_runtime.subconscious.agent import (
    agent_run_config_from_args as agent_run_config_from_args,
)
from aippocampus_runtime.subconscious.agent import main as main
from aippocampus_runtime.subconscious.agent import run_agent as run_agent
from aippocampus_runtime.subconscious.agent import (
    run_agent_with_config as run_agent_with_config,
)
from aippocampus_runtime.subconscious.agent import (
    validate_agent_edges as validate_agent_edges,
)

if __name__ == "__main__":
    raise SystemExit(main())
