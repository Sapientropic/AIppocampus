# Recall Degradation Audit

Role: public-safe deterministic fixture for #1184.

This audit checks that safe recall does not degrade into useless foreground
navigation. It starts from synthetic clean-source rows and the live
`recall_context_packet -> agent recall -> MemoryPacket` path. The fixture does
not prefill route labels; labels must be derived from public-safe route
metadata such as scope labels.

Run:

```powershell
python benchmarks\aippocampus\benchmark_recall_degradation_audit.py --json
```

The report kind is `aippocampus_recall_degradation_audit_fixture`.

## 2026-06-11 Fixture Result

Current deterministic result:

- `clean_source_reopenable_route_count = 3`
- `same_phase_title_route_count = 3`
- `input_prefilled_route_label_count = 0`
- `generic_reopen_hint_count = 0`
- `packet_triage_collision_count = 0`
- `blind_deepen_required_count = 0`
- `ask_light_question_with_reopenable_candidate_count = 0`
- `manual_search_fallback_count = 0`
- `cannot_verify_without_next_safe_action_count = 0`
- `foreground_packet_budget_violation_count = 0`
- `foreground_forbidden_key_count = 0`
- `safety_gate_ok = true`
- `usefulness_gate_ok = true`

The clean-source fixture has three relevant routes with the same visible
`phase/title` shape, but different safe scope buckets:

- `technical_work route`
- `open_question route`
- `relationship_continuity route`

The source-thin case deepens to `CannotVerify` and still exposes a safe
`use_hint` next action, without inventing manual search terms.

## Boundaries

Measured result: the current public-safe clean-source route projection can
derive distinct foreground route-selection previews without leaking source
handles, source refs, source ids, raw source text, local paths, or private
sentinels.

Important limits:

- synthetic clean-source fixture only;
- no live host behavior or private-history usefulness claim;
- labels and summaries remain navigation, not source evidence;
- this does not wire the full attention router into every live recall surface.

For the live-agent/proxy gap in #2329, use
`aippocampus smoke recall-funnel "<cue>" --json`. That diagnostic keeps this
fixture boundary intact while separately reporting ordinary
`agent recall -> agent deepen` route existence, specificity, source reopen, and
task usefulness.
