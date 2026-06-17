# Recall Architecture

Role: recall and foreground-memory contract index.
Status: current architecture layer.

Use this folder when changing how agents request, rank, display, or deepen
memory routes. Source authority still belongs to the source layer. For the
agent-facing UX review checklist across foreground cards, hooks, MCP/CLI, and
recovery flows, use the
[AIppocampus UX charter](../../../skills/aippocampus-ux/references/agent-facing-ux-charter.md).

| File | Use |
| --- | --- |
| [agent-native-recall-facade.md](agent-native-recall-facade.md) | Minimal recall/deepen/explain facade over route packets for agent hosts. |
| [cognitive-load-sidecar.md](cognitive-load-sidecar.md) | Deterministic cognitive-load sidecar and live-calibration boundary. |
| [continuity-domains.md](continuity-domains.md) | Source-trailed domains, pathlets, macro pointers, and situation glyph boundaries. |
| [foreground-memory-ux-budget.md](foreground-memory-ux-budget.md) | Foreground memory packet size, review-needed, anti-nag, and no-profile-dump budget. |
| [memory-evidence-drawer.md](memory-evidence-drawer.md) | Foreground recall explanation packet and source-reopen affordance boundary. |
| [question-tracking-subconscious.md](question-tracking-subconscious.md) | Question extraction, tracking, and theme-emergence design. |
| [source-backed-attention-router.md](source-backed-attention-router.md) | Hard-mask, route-packet, output-level, and claim-permission boundaries. |
| [source-backed-product-discipline.md](source-backed-product-discipline.md) | Recall-layer audit for source-backed foreground product discipline and Task Orientation Packets. |
| [source-backed-familiarity-map.md](source-backed-familiarity-map.md) | Familiarity-map direction and source-backed boundary. |
