"""Instruction-surface inventory helpers for architecture debt checks."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterable
from pathlib import Path

INSTRUCTION_SURFACE_POLICY_DOC = (
    "docs/architecture/runtime/instruction-surface-policy.md"
)
INSTRUCTION_SURFACE_MARKER = "aippocampus-instruction-surface:"
INSTRUCTION_SURFACE_SCAN_PREFIXES = (
    "skills/aippocampus/scripts/aippocampus_runtime/source/",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/",
    "skills/aippocampus/scripts/aippocampus_runtime/update/",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/",
    "tests/aippocampus/",
)
INSTRUCTION_SURFACE_MIN_HITS = {
    "runtime": 3,
    "tests": 8,
}
INSTRUCTION_SURFACE_CLASSIFIED_FILES = {
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py": {
        "classification": "compact_projection_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns the compact recall card translation boundary; proof remains in "
            "detail/operator/tests, not default MCP payload expansion"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_deepen_projection.py": {
        "classification": "mcp_deepen_projection_owner",
        "owner": "#2679/#2686/#2651",
        "why": (
            "owns MCP agent_deepen compact-vs-detail source-open and recovery "
            "cards; operator/source diagnostics remain in detail/full output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_explain_projection.py": {
        "classification": "mcp_explain_projection_owner",
        "owner": "#2679/#2686/#2651",
        "why": (
            "owns MCP and CLI agent_explain compact-vs-detail recovery cards; "
            "policy/operator diagnostics remain behind detail/full output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_compact_choices.py": {
        "classification": "compact_route_choice_owner",
        "owner": "#2663/#2651",
        "why": (
            "owns compact recall route-choice and source-search affordance wording; "
            "route proof remains in deepen/open follow-through and tests"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/compact_profile.py": {
        "classification": "mcp_compact_profile_owner",
        "owner": "#2679/#2685/#2686/#2651",
        "why": (
            "owns MCP structuredContent/text compact filtering; debug and proof "
            "fields stay behind detail/operator profiles"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/foreground_recovery.py": {
        "classification": "mcp_foreground_recovery_owner",
        "owner": "#2685/#2651",
        "why": (
            "owns missing-input recovery card wording and safe next actions for "
            "MCP tools; detailed source/operator payload stays in full profile"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/public_projection.py": {
        "classification": "mcp_public_projection_owner",
        "owner": "#2666/#2651",
        "why": (
            "owns MCP default-vs-full public projection and redaction text; raw "
            "diagnostics stay in full/detail surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/continuity_routes.py": {
        "classification": "mcp_continuity_route_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns MCP continuity-domain route handles and route-count diagnostics; "
            "compact proof must stay in follow-through, not foreground field dumps"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/recall_navigation.py": {
        "classification": "mcp_recall_navigation_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns MCP progressive recall handles and blocked-source messages; "
            "handles guide deepen/open but must not become remembered facts"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py": {
        "classification": "mcp_tool_handler_owner",
        "owner": "#2666/#2651",
        "why": (
            "owns MCP handler tool-error and renderer-routing text; handlers must "
            "delegate compact/detail cleanup to the shared profile layer"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity.py": {
        "classification": "runtime_prompt_and_route_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns recall route/action selection text that later projections render"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/active_path_packet.py": {
        "classification": "active_path_packet_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns Active Path Packet foreground route hints; packet text is "
            "navigation guidance and source reopening remains the truth boundary"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli_support.py": {
        "classification": "recall_cli_render_boundary_owner",
        "owner": "#2636/#2651",
        "why": (
            "owns agent recall/deepen compact-vs-detail CLI rendering; source proof "
            "and diagnostics must stay in detail/operator surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cards.py": {
        "classification": "ambient_recall_card_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns compact ambient-card guidance and its source-boundary warnings; "
            "cards may orient attention but cannot assert source-open facts"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py": {
        "classification": "ambient_thread_cache_owner",
        "owner": "#2674/#2676/#2651",
        "why": (
            "owns local ambient-cache persistence and related-cache boundary text; "
            "cached cards remain navigation until clean source is reopened"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/cognitive_load_private_calibration.py": {
        "classification": "private_calibration_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns public-safe cognitive-load calibration wording from private "
            "history; private detail stays out of foreground output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_cli.py": {
        "classification": "continuity_domain_operator_cli_owner",
        "owner": "#2668/#2651",
        "why": (
            "owns explicit continuity-domain preview/operator wording; default "
            "foreground recall still has to reopen source before claims"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_cue_quality.py": {
        "classification": "continuity_domain_cue_quality_owner",
        "owner": "#2668/#2651",
        "why": (
            "owns continuity-domain foreground cue quality and suppression labels; "
            "broad route words may stay diagnostic but must not become recall commands"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domain_producer.py": {
        "classification": "continuity_domain_producer_owner",
        "owner": "#2668/#2631/#2651",
        "why": (
            "owns deterministic registry-to-domain candidate wording and "
            "low-information label filtering; append/publish remains operator-owned"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/evidence_drawer.py": {
        "classification": "evidence_drawer_projection_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns optional evidence-drawer explanation text; drawer/detail output "
            "can explain proof without expanding default compact recall"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/hook_agent_affordance.py": {
        "classification": "hook_agent_affordance_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns prompt-hook affordance text and quieting rules; broad agent words "
            "must not become unsolicited foreground recall nudges"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_cues.py": {
        "classification": "prompt_cue_policy_owner",
        "owner": "#2651",
        "why": (
            "owns prompt-intent and cue-detection strings used before recall "
            "routing; broad product doctrine belongs in canonical docs"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/route_notes.py": {
        "classification": "route_note_extraction_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns process-note extraction wording; notes are route context and must "
            "be source-reopened before becoming factual evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py": {
        "classification": "score_fusion_policy_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns retrieval score-fusion contract text; score richness is ranking "
            "metadata, not source eligibility"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/task_orientation.py": {
        "classification": "task_orientation_projection_owner",
        "owner": "#2670/#2651",
        "why": (
            "owns Task Orientation compact/detail projection text; compact route "
            "guidance must stay distinct from callable source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/task_orientation_fixtures.py": {
        "classification": "task_orientation_fixture_owner",
        "owner": "#2670/#2651",
        "why": (
            "owns deterministic Task Orientation fixture wording used to guard "
            "source-guidance boundaries without becoming live source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/segment_search_extras.py": {
        "classification": "source_sidecar_boundary_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns source sidecar/read-model boundary strings; sidecars may guide "
            "search, while source-open proof stays in detail/tests/issue closeout"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_actions.py": {
        "classification": "registry_search_action_owner",
        "owner": "#2660/#2662/#2651",
        "why": (
            "owns registry search foreground actions for exact identifiers and "
            "useful-target gating; diagnostic hits must not become source-open proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/agent_self_note_cli.py": {
        "classification": "agent_self_note_cli_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns low-authority foreground-agent self-note text and current-thread "
            "route hints; self-notes remain atmosphere, not evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py": {
        "classification": "source_io_trust_boundary_owner",
        "owner": "#2635/#2675/#2651",
        "why": (
            "owns JSONL/source-ref loss-accounting boundary text; diagnostics "
            "belong in detail/operator surfaces, not compact foreground proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/clean_source.py": {
        "classification": "clean_source_boundary_owner",
        "owner": "#2628/#2636/#2651",
        "why": (
            "owns clean-source normalization diagnostics and redaction labels; clean "
            "source is authority, while provider loss/profiles stay explicit"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/multimodal_manifest.py": {
        "classification": "multimodal_manifest_policy_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns media-origin validation text for source manifests; policy strings "
            "guard source eligibility rather than foreground recall proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_pipeline.py": {
        "classification": "registry_search_projection_owner",
        "owner": "#2660/#2662/#2651",
        "why": (
            "owns registry-wide search projection wording; exact/source usefulness "
            "state must drive actions instead of generic familiarity fallbacks"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/source/last_recall_recovery.py": {
        "classification": "last_recall_recovery_action_owner",
        "owner": "#2665/#2651",
        "why": (
            "owns invalid-selector recovery actions for last-recall source search; "
            "fallback commands must stay explicit and non-mutating"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/scheduler.py": {
        "classification": "lifecycle_scheduler_boundary_owner",
        "owner": "#2635/#2651",
        "why": (
            "owns hook-safe scheduler boundary text; lifecycle foreground must "
            "stay fail-open and must not become a proof or job-output surface"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/foreground_status.py": {
        "classification": "foreground_hook_status_owner",
        "owner": "#2611/#2651",
        "why": (
            "owns foreground hook/action-hint status wording and latency readiness; "
            "status output is operational guidance, not source proof"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_lifecycle.py": {
        "classification": "lifecycle_hook_install_owner",
        "owner": "#2674/#2651",
        "why": (
            "owns lifecycle hook install/status text and private command redaction; "
            "hook wiring is operational state, not foreground source evidence"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_prompt.py": {
        "classification": "prompt_hook_install_owner",
        "owner": "#2674/#2651",
        "why": (
            "owns prompt hook install/status text, latency-budget wording, and "
            "private command redaction for hook setup surfaces"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/skip_telemetry.py": {
        "classification": "prompt_skip_telemetry_owner",
        "owner": "#2674/#2651",
        "why": (
            "owns aggregate prompt-hook skip/latency telemetry wording; telemetry "
            "is local operational signal and must not log prompt/source text"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary.py": {
        "classification": "update_status_compact_projection_owner",
        "owner": "#2661/#2651",
        "why": (
            "owns compact update/readiness card text; acceptance-bearing warnings "
            "must stay actionable without being reported as ready"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary_core.py": {
        "classification": "update_status_projection_primitive_owner",
        "owner": "#2628/#2631/#2651",
        "why": (
            "owns shared update/readiness projection wording and action ordering "
            "primitives so staged modules do not recreate helper copies or cycles"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/capability_ladder.py": {
        "classification": "capability_ladder_status_owner",
        "owner": "#2628/#2651",
        "why": (
            "owns capability/readiness ladder wording; ambient states must stay to "
            "installed/callable/active/useful without mixed ready claims"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary_stages.py": {
        "classification": "update_status_staged_projection_owner",
        "owner": "#2631/#2651",
        "why": (
            "owns staged compact update/readiness projection after the mega-function "
            "split; proof and raw diagnostics remain in operator/detail output"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/status_actions.py": {
        "classification": "update_status_action_owner",
        "owner": "#2661/#2669/#2651",
        "why": (
            "owns update/readiness foreground action cards and mutation-risk labels "
            "for CLI and MCP follow-through"
        ),
    },
    "tests/aippocampus/frontstage_assertions.py": {
        "classification": "test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns reusable compact-vs-detail assertions instead of duplicating "
            "foreground doctrine in payload tests"
        ),
    },
    "tests/aippocampus/test_architecture_boundaries.py": {
        "classification": "architecture_guard_test_owner",
        "owner": "#2636/#2651",
        "why": "owns repository-level architecture boundary tests.",
    },
    "tests/aippocampus/test_aippocampus_cli.py": {
        "classification": "cli_frontdoor_test_contract_owner",
        "owner": "#2664/#2651",
        "why": "owns executable CLI frontdoor contracts for operator/detail actions.",
    },
    "tests/aippocampus/test_aippocampus_mcp_server_catalog.py": {
        "classification": "mcp_catalog_test_contract_owner",
        "owner": "#2685/#2686/#2651",
        "why": (
            "owns MCP tool catalog and missing-input compact/detail regression "
            "tests so payload assertions do not re-freeze JSON-wall text"
        ),
    },
    "tests/aippocampus/test_ambient_recall_cards.py": {
        "classification": "ambient_recall_card_test_contract_owner",
        "owner": "#2628/#2632/#2651",
        "why": (
            "owns ambient card trust/action-grammar behavior tests; identity checks "
            "must exercise public card output rather than private helper aliases"
        ),
    },
    "tests/aippocampus/test_cli_recovery_cards.py": {
        "classification": "cli_recovery_card_test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns broad CLI recovery-card wording assertions; shared helpers keep "
            "the subprocess runner centralized while compact/detail doctrine stays in tests"
        ),
    },
    "tests/aippocampus/test_closeout_audit.py": {
        "classification": "closeout_audit_test_contract_owner",
        "owner": "#2692/#2636/#2651",
        "why": (
            "owns PR-body and issue-closeout fixture text for the closeout audit; "
            "these strings are test inputs, not runtime foreground instructions"
        ),
    },
    "tests/aippocampus/test_question_tracking.py": {
        "classification": "question_source_ref_test_contract_owner",
        "owner": "#2667/#2651",
        "why": "owns question source-ref reopen contracts instead of title-search fallbacks.",
    },
    "tests/aippocampus/test_task_orientation_packet.py": {
        "classification": "task_orientation_test_contract_owner",
        "owner": "#2670/#2651",
        "why": "owns Task Orientation compact/detail boundary tests.",
    },
    "tests/aippocampus/test_update_agent_status.py": {
        "classification": "update_status_test_contract_owner",
        "owner": "#2661/#2651",
        "why": "owns compact update-status readiness semantics for foreground agents.",
    },
    "tests/aippocampus/test_update_sync.py": {
        "classification": "update_sync_test_contract_owner",
        "owner": "#2661/#2669/#2651",
        "why": "owns update/sync foreground action and mutation-risk regression contracts.",
    },
    "tests/aippocampus/test_warm_ambient_recall.py": {
        "classification": "warm_ambient_test_contract_owner",
        "owner": "#2632/#2651",
        "why": (
            "owns warm ambient recall compact/detail and private-boundary tests; "
            "fixtures should guard product semantics instead of freezing debug noise"
        ),
    },
}
COMPACT_DEBUG_FIELD_LITERALS = (
    "runtime_provenance",
    "source_anchor_gate",
    "operator_detail_command",
    "safe_next_actions",
    "weak_route_recovery_card",
    "apw_recovery_state",
    "last_recall_cache_available",
    "recall_selector_id",
    "route_count",
)
INSTRUCTION_SURFACE_TERMS = (
    "must",
    "should",
    "never",
    "always",
    "do not",
    "don't",
    "instruction",
    "prompt",
    "policy",
    "contract",
    "canonical",
    "claim_boundary",
    "cannot_claim",
    "foreground",
    "operator",
    "detail",
    "diagnostic",
    "source-backed",
    "source backed",
    "proof",
    "evidence",
)


def repo_relative(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def instruction_surface_scan_scope(rel_path: str) -> bool:
    return rel_path.startswith(INSTRUCTION_SURFACE_SCAN_PREFIXES)


def instruction_surface_threshold(rel_path: str) -> int:
    return (
        INSTRUCTION_SURFACE_MIN_HITS["tests"]
        if rel_path.startswith("tests/aippocampus/")
        else INSTRUCTION_SURFACE_MIN_HITS["runtime"]
    )


def instruction_surface_classification(
    rel_path: str,
    text: str,
) -> dict[str, object] | None:
    """Return the owner classification for instruction-like text in a file."""

    explicit = INSTRUCTION_SURFACE_CLASSIFIED_FILES.get(rel_path)
    if explicit:
        return {
            "path": rel_path,
            "source": "central_classification",
            "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
            **explicit,
        }
    if INSTRUCTION_SURFACE_MARKER in text:
        line = next(
            (
                index
                for index, value in enumerate(text.splitlines(), start=1)
                if INSTRUCTION_SURFACE_MARKER in value
            ),
            0,
        )
        return {
            "path": rel_path,
            "source": "inline_marker",
            "classification": "local_marked_boundary",
            "line": line,
            "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
        }
    return None


def instruction_like_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    if len(normalized) < 12:
        return False
    if " " not in normalized:
        return False
    if normalized.startswith(("def ", "from ", "import ")):
        return False
    if re.fullmatch(r"[\w./:\\#-]+", normalized):
        return False
    return any(term in normalized for term in INSTRUCTION_SURFACE_TERMS)


def instruction_comment_hits(text: str) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except tokenize.TokenError:
        return hits
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        comment = token.string.lstrip("#").strip()
        if instruction_like_text(comment):
            hits.append(
                {
                    "line": int(token.start[0]),
                    "kind": "comment",
                    "text": comment[:160],
                }
            )
    return hits


def instruction_string_hits(path: Path, text: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    hits: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value.strip()
        if instruction_like_text(value):
            hits.append(
                {
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "kind": "string",
                    "text": re.sub(r"\s+", " ", value)[:160],
                }
            )
    return hits


def instruction_surface_hits(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    hits = [*instruction_comment_hits(text), *instruction_string_hits(path, text)]
    return sorted(hits, key=lambda item: (int(item["line"]), str(item["kind"])))


def instruction_surface_inventory(
    paths: Iterable[Path],
    *,
    repo_root: Path,
) -> dict[str, object]:
    occurrences: list[dict[str, object]] = []
    classified_files: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda item: repo_relative(repo_root, item)):
        rel_path = repo_relative(repo_root, path)
        if not instruction_surface_scan_scope(rel_path):
            continue
        text = path.read_text(encoding="utf-8")
        hits = instruction_surface_hits(path)
        if not hits:
            continue
        classification = instruction_surface_classification(rel_path, text)
        item = {
            "path": rel_path,
            "hit_count": len(hits),
            "classification": classification,
            "sample_hits": hits[:5],
        }
        occurrences.append(item)
        if classification:
            classified_files.append(item)
    occurrences.sort(key=lambda item: (-int(item["hit_count"]), str(item["path"])))
    return {
        "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
        "summary": {
            "file_count": len(occurrences),
            "hit_count": sum(int(item["hit_count"]) for item in occurrences),
            "classified_file_count": len(classified_files),
            "unclassified_file_count": len(occurrences) - len(classified_files),
        },
        "top_files": occurrences[:20],
        "classified_files": classified_files,
        "note": (
            "Instruction-like text is inventory pressure, not automatic wrongdoing. "
            "Changed-surface warnings require an owner classification or inline "
            "local-boundary marker."
        ),
    }


def changed_file_instruction_surface(
    path: Path,
    *,
    repo_root: Path,
) -> dict[str, object] | None:
    rel_path = repo_relative(repo_root, path)
    if not instruction_surface_scan_scope(rel_path):
        return None
    text = path.read_text(encoding="utf-8")
    hits = instruction_surface_hits(path)
    threshold = instruction_surface_threshold(rel_path)
    if len(hits) < threshold:
        return None
    return {
        "path": rel_path,
        "hit_count": len(hits),
        "threshold": threshold,
        "classification": instruction_surface_classification(rel_path, text),
        "sample_hits": hits[:5],
    }


def changed_file_instruction_surface_warning(
    item: dict[str, object],
) -> dict[str, object] | None:
    if item.get("classification"):
        return None
    return {
        "code": "changed_surface_instruction_surface_unclassified",
        "path": item["path"],
        "hit_count": item["hit_count"],
        "threshold": item["threshold"],
        "sample_hits": item["sample_hits"],
        "acceptance_bearing": True,
        "message": (
            "Touched hot-path/test file contains instruction-like comments or strings; "
            "classify them as local invariant, canonical-doc pointer, runtime prompt "
            "owner, detail/operator diagnostics, test contract, or delete compensatory noise."
        ),
        "policy_doc": INSTRUCTION_SURFACE_POLICY_DOC,
    }
