#!/usr/bin/env python3
"""Compatibility shim for packaged subconscious runtime primitives."""

from __future__ import annotations

from aippocampus_runtime.subconscious.runtime import (
    AGENT_SYSTEM_PROMPT as AGENT_SYSTEM_PROMPT,
)
from aippocampus_runtime.subconscious.runtime import DEFAULT_MAX_STEPS as DEFAULT_MAX_STEPS
from aippocampus_runtime.subconscious.runtime import (
    DEFAULT_MIN_TOOL_STEPS as DEFAULT_MIN_TOOL_STEPS,
)
from aippocampus_runtime.subconscious.runtime import DEFAULT_TEMPERATURE as DEFAULT_TEMPERATURE
from aippocampus_runtime.subconscious.runtime import HARD_MAX_STEPS as HARD_MAX_STEPS
from aippocampus_runtime.subconscious.runtime import AgentState as AgentState
from aippocampus_runtime.subconscious.runtime import ChatFn as ChatFn
from aippocampus_runtime.subconscious.runtime import add_usage as add_usage
from aippocampus_runtime.subconscious.runtime import call_chat_json as call_chat_json
from aippocampus_runtime.subconscious.runtime import compact_usage as compact_usage
from aippocampus_runtime.subconscious.runtime import (
    effective_step_budget as effective_step_budget,
)
from aippocampus_runtime.subconscious.runtime import normalize_tool_terms as normalize_tool_terms
from aippocampus_runtime.subconscious.runtime import parse_action as parse_action
from aippocampus_runtime.subconscious.runtime import project_matches as project_matches
from aippocampus_runtime.subconscious.runtime import registry_entries as registry_entries
from aippocampus_runtime.subconscious.runtime import run_tool as run_tool
from aippocampus_runtime.subconscious.runtime import (
    source_bank_from_turns as source_bank_from_turns,
)
from aippocampus_runtime.subconscious.runtime import tool_expand_concepts as tool_expand_concepts
from aippocampus_runtime.subconscious.runtime import tool_get_turn_context as tool_get_turn_context
from aippocampus_runtime.subconscious.runtime import tool_recent_edges as tool_recent_edges
from aippocampus_runtime.subconscious.runtime import (
    tool_search_clean_source as tool_search_clean_source,
)
