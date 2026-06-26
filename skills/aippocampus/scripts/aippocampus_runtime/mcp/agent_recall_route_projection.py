"""Route receipt projection for compact agent recall."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import shell_quote


@dataclass(frozen=True)
class RouteReceiptProjection:
    route_receipts: list[dict[str, Any]]
    duplicate_label_omissions: dict[str, dict[str, Any]]
    suppressed_low_confidence_route_count: int


def public_route_label(packet: Mapping[str, Any]) -> str:
    if (
        str(packet.get("route_kind") or "") == "associative_path"
        or str(packet.get("matched_cue_family") or "") == "associative_path_fallback"
        or str(packet.get("label_granularity") or "") == "associative_path_terms"
    ):
        raw = str(
            packet.get("route_label")
            or packet.get("route_topic")
            or packet.get("display_hint")
            or "APW source route"
        )
        label = raw.removeprefix("thread_candidate:")
        label = label.replace("_", " ").replace("·", " ")
        label = " ".join(label.split())
        return core.compact_text(label[:1].upper() + label[1:] if label else "APW source route", 90)
    raw = str(
        packet.get("route_topic")
        or packet.get("route_label")
        or packet.get("display_hint")
        or "memory route"
    )
    label = raw.removeprefix("thread_candidate:")
    label = label.replace("_", " ").replace("·", " ")
    label = " ".join(label.split())
    return core.compact_text(label[:1].upper() + label[1:] if label else "Memory route", 90)


def route_deepen_action(
    request_index: int,
    *,
    recall_selector: str = "",
    low_confidence: bool = False,
) -> dict[str, Any]:
    clean_selector = str(recall_selector or "").strip()
    arguments: dict[str, Any] = {"request_index": request_index}
    if clean_selector:
        arguments["recall_selector"] = clean_selector
        command = (
            f"aippocampus agent deepen --request {request_index} "
            f"--recall-selector {shell_quote(clean_selector)} --json"
        )
    else:
        command = ""
    action: dict[str, Any] = {
        "id": "deepen_this_route",
        "tool_name": "agent_deepen",
        "arguments": arguments,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }
    if clean_selector:
        action["command"] = command
    else:
        action.update(
            {
                "command_template": (
                    "aippocampus agent deepen --request {request_index} "
                    "--recall-selector {recall_selector} --json"
                ),
                "requires": ["request_index", "recall_selector"],
                "template_only": True,
                "last_recall_fallback_command": (
                    f"aippocampus agent deepen --request {request_index} --last-recall --json"
                ),
                "last_recall_fallback_boundary": (
                    "--last-recall reads a mutable same-machine cache; use only when "
                    "the recall_selector emitted by the same recall is unavailable."
                ),
            }
        )
    if low_confidence:
        action["route_choice_posture"] = "labels_low_specificity"
        action["confidence"] = "low_confidence_navigation"
    return action


def project_route_receipts(
    memory_packets: list[dict[str, Any]],
    *,
    labels_low_specificity: bool,
    cache_available: bool,
    recall_selector: str,
) -> RouteReceiptProjection:
    """Render compact route choices without carrying raw handles or proof.

    This owner only shapes navigation receipts. Ranking, source proof, APW
    arbitration, and detail/operator diagnostics stay in their dedicated
    stages so compact MCP cannot become a catch-all debug console again.
    """

    displayed_packets, duplicate_label_omissions = _displayed_route_packets(
        memory_packets,
        labels_low_specificity=labels_low_specificity,
    )
    route_receipts: list[dict[str, Any]] = []
    for index, packet in displayed_packets:
        already_opened = bool(packet.get("already_opened"))
        route_is_callable = (
            cache_available
            and str(packet.get("output_mode") or "") == "reopenable_route"
        )
        route_receipts.append(
            core.strip_empty(
                {
                    "index": index,
                    "label": public_route_label(packet),
                    "why_this_route": _route_choice_explanation(
                        packet,
                        index=index,
                        route_count=len(memory_packets),
                        labels_low_specificity=labels_low_specificity,
                    ),
                    "request_index": index if route_is_callable else None,
                    "recall_selector": recall_selector if route_is_callable and recall_selector else None,
                    "already_opened": already_opened or None,
                    "source_boundary": "reopen_required_before_claim",
                    "action": route_deepen_action(
                        index,
                        recall_selector=recall_selector,
                        low_confidence=labels_low_specificity,
                    )
                    if route_is_callable
                    else None,
                }
            )
        )
    suppressed = 0
    if labels_low_specificity and route_receipts:
        # Keep a few read-only navigation receipts so a later agent is not
        # stranded, but mark them as low-confidence and let the foreground
        # action remain search/refine. The final compact stripper removes
        # detail-only posture fields from default product output.
        suppressed = max(0, len(memory_packets) - len(route_receipts))
        for receipt in route_receipts:
            receipt["route_choice_posture"] = "labels_low_specificity"
            receipt["confidence"] = "low_confidence_navigation"
            receipt["claim_boundary"] = "no_claim_before_reopen"
    return RouteReceiptProjection(
        route_receipts=route_receipts,
        duplicate_label_omissions=duplicate_label_omissions,
        suppressed_low_confidence_route_count=suppressed,
    )


def _displayed_route_packets(
    memory_packets: list[dict[str, Any]],
    *,
    labels_low_specificity: bool,
) -> tuple[list[tuple[int, dict[str, Any]]], dict[str, dict[str, Any]]]:
    duplicate_label_omissions: dict[str, dict[str, Any]] = {}
    if not labels_low_specificity:
        return list(enumerate(memory_packets[:3], start=1)), duplicate_label_omissions

    displayed_packets: list[tuple[int, dict[str, Any]]] = []
    seen_labels: dict[str, dict[str, Any]] = {}
    for index, packet in enumerate(memory_packets, start=1):
        label = public_route_label(packet)
        label_key = _route_label_key(label)
        if label_key and label_key in seen_labels:
            summary = duplicate_label_omissions.setdefault(
                label_key,
                {
                    "route_label": label,
                    "kept_route_index": seen_labels[label_key]["route_index"],
                    "omitted_count": 0,
                },
            )
            summary["omitted_count"] = int(summary["omitted_count"]) + 1
            continue
        if label_key:
            seen_labels[label_key] = {"route_index": index, "route_label": label}
        if len(displayed_packets) < 3:
            displayed_packets.append((index, packet))
    return displayed_packets, duplicate_label_omissions


def _route_label_key(label: str) -> str:
    return " ".join(str(label or "").casefold().split())


def _route_choice_explanation(
    packet: Mapping[str, Any],
    *,
    index: int,
    route_count: int,
    labels_low_specificity: bool,
) -> str:
    if labels_low_specificity:
        return "Potential route, but compact labels are not specific enough; refine or search source before choosing."
    if route_count <= 1:
        return "Best available route; reopen it before using source-backed details."
    output_mode = str(packet.get("output_mode") or packet.get("route_kind") or "")
    if output_mode == "reopenable_route":
        return f"Route {index} of {route_count}; it can be reopened for source-backed details."
    if output_mode == "direction_only":
        return f"Route {index} of {route_count}; use as navigation only until source is reopened."
    return f"Route {index} of {route_count}; inspect it before treating it as evidence."
