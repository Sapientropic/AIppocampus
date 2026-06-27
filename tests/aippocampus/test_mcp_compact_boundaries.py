from __future__ import annotations

import unittest
from types import SimpleNamespace

from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.mcp.agent_explain_projection import compact_agent_explain_payload
from aippocampus_runtime.mcp.agent_recall_result_assembly import (
    assemble_compact_recall_payload,
)
from aippocampus_runtime.mcp.compact_profile import compact_search_memory_payload
from aippocampus_runtime.mcp.contracts import (
    MCPCompactBoundaryError,
    build_mcp_compact_card,
)


def _bad_template_action() -> dict[str, object]:
    return {
        "id": "bad_template_primary",
        "tool_name": "agent_recall",
        "arguments_template": {"query": "{memory_cue}"},
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": "This template omits required inputs and must not be primary.",
    }


class McpCompactBoundaryTests(unittest.TestCase):
    def test_template_primary_must_mark_required_inputs_or_non_action(self) -> None:
        with self.assertRaises(MCPCompactBoundaryError):
            build_mcp_compact_card(
                {"detail": "compact", "foreground_action": _bad_template_action()},
                surface="mcp_agent_recall_compact",
            )

    def test_agent_recall_compact_projection_uses_boundary(self) -> None:
        context = SimpleNamespace(
            labels_low_specificity=False,
            memory_packets=[],
            status="needs_input",
        )
        route_projection = SimpleNamespace(route_receipts=[])

        with self.assertRaises(MCPCompactBoundaryError):
            assemble_compact_recall_payload(
                {},
                context,
                route_projection_result=route_projection,
                foreground_action=_bad_template_action(),
                safe_next_actions=[],
                miss_recovery_card=None,
                weak_route_recovery_card=None,
                apw_recovery=None,
                repo_familiarity_fallback=None,
                background_recovery=None,
                exact_wording_source_search_primary=False,
            )

    def test_agent_deepen_compact_projection_uses_boundary(self) -> None:
        with self.assertRaises(MCPCompactBoundaryError):
            compact_agent_deepen_payload(
                {
                    "surface": "recall",
                    "status": "needs_input",
                    "ok": False,
                    "foreground_action": _bad_template_action(),
                },
                surface="mcp_agent_deepen_compact",
            )

    def test_agent_explain_compact_projection_uses_boundary(self) -> None:
        with self.assertRaises(MCPCompactBoundaryError):
            compact_agent_explain_payload(
                {
                    "surface": "recall",
                    "status": "needs_input",
                    "ok": False,
                    "foreground_action": _bad_template_action(),
                },
                surface="mcp_agent_explain_compact",
            )

    def test_search_memory_compact_projection_uses_boundary(self) -> None:
        with self.assertRaises(MCPCompactBoundaryError):
            compact_search_memory_payload(
                {
                    "kind": "aippocampus_search_result",
                    "detail": "compact",
                    "status": "ok",
                    "ok": True,
                    "matches": [],
                    "foreground_action": _bad_template_action(),
                }
            )


if __name__ == "__main__":
    unittest.main()
