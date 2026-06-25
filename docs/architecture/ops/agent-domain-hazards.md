# Agent Domain Hazards

Role: implementation map.
Status: current verification aid.

These cards exist because agents often know the general engineering rule but
miss the local domain hazard while optimizing for a green local shape. They are
attention aids, not source evidence, not product claims, and not a full SDD
layer.

Use these cards before editing or closing work on the listed surfaces. If a
card becomes too detailed, move the detail to the owning module docs, focused
test helper, or verification tool and leave only a pointer here.

## Card Format

```text
surface:
hazard:
why agents miss it:
forbidden shortcuts:
required checks:
allowed examples:
anti-examples:
focused command or fixture:
owner:
```

## Mined Navigation Terms

surface: `navigation/association*`, `navigation/concept_graph*`,
`cognitive_map`, theme extraction, phrase mining.

hazard: mined labels can look structured while flooding recall with fragments,
substring variants, one-window co-occurrence, or graph expansion that does not
help a foreground agent reopen useful source.

why agents miss it: n-gram windows, high edge counts, and populated graph JSON
look like progress even when the labels are not meaningful terms. Mixed
language and CJK text make the shortcut especially tempting because whitespace
is not a reliable boundary.

forbidden shortcuts:

- raw sliding-window CJK terms as user-facing concepts;
- promoting high-volume `co_occurs` edges without source/window diversity;
- treating graph growth, hub count, or constant confidence as recall quality;
- hiding bad terms by adding more downstream filters without fixing producer
  quality.

required checks:

- CJK fragment indicators and bad-edge-character ratios stay visible;
- source/window diversity is measured before promotion;
- substring domination and high-fanout hubs are bounded or parked;
- allowed meaningful CJK terms still survive the filter.

allowed examples: recurring, source-diverse phrases that would help an agent
choose a source reopen route.

anti-examples: two-character fragments, punctuation-bound terms, raw adjacent
character windows, and one-source co-occurrence edges presented as durable
concepts.

focused command or fixture:

```powershell
python -m pytest tests\aippocampus\test_build_associations.py tests\aippocampus\test_build_concept_graph.py -q
```

owner: navigation data-quality guard / issue track #2695.

## Foreground Recall Follow-Through

surface: `agent recall`, MCP recall/deepen, APW source routes, source-open
foreground actions, compact foreground projection, repo familiarity fallback.

hazard: payloads can be schema-valid, safe, and full of boundary fields while
still failing the user because the emitted route does not open the right source
or sends the agent into unrelated repo familiarity.

why agents miss it: "wired", `source_backed`, selector emission, route counts,
and compact JSON shape are easy to assert. The product invariant is harder:
the foreground agent must spend less effort and reopen useful source.

forbidden shortcuts:

- accepting field presence, route count, or "ready" as completion;
- moving operator diagnostics into compact output to justify safety;
- falling back to unrelated repo familiarity when exact/current source can
  answer the cue;
- claiming foreground action readiness without running CLI and MCP follow
  through.

required checks:

- real cue: `agent recall -> agent deepen/open -> opened source anchor hits`;
- MCP path for any MCP or "wired/ready" claim;
- compact output and detail/operator output inspected separately;
- wrong-route drag and manual-search fallback are counted as failures, not just
  warnings.

allowed examples: compact card with one useful next action plus a deepenable
route that opens the expected source.

anti-examples: a top-level `ok` result with nested blocker gates, debug policy
objects, or a route label that looks useful but opens nothing.

focused command or fixture:

```powershell
python -m pytest tests\aippocampus\test_agent_recall_compact_projection.py tests\aippocampus\test_agent_deepen_compact_projection.py tests\aippocampus\test_aippocampus_mcp_server_recall.py -q
```

owner: foreground recall / MCP verification steward.

## Source And State Durability

surface: JSONL intake, clean-source extraction, registry and sync publish,
locks, stale selectors, compatibility aliases, storage cleanup.

hazard: the happy path can pass while corrupt lines, stale locks, orphaned
generations, platform path behavior, or compatibility aliases silently change
what memory can be reopened.

why agents miss it: these surfaces often fail by omission. A command exits
successfully, a manifest exists, or a fallback field appears, but skipped input,
stale state, or a lost source anchor is not visible unless counted.

forbidden shortcuts:

- `except: continue` on source-bearing input without loss accounting;
- direct JSONL parsing outside the source IO owner;
- ad-hoc atomic writes or lock files outside the owning helper;
- new compatibility fields without owner, sunset condition, and default
  visibility boundary.

required checks:

- bad rows, dropped assistant turns, and skipped events are counted or reported;
- lock ownership and stale-break behavior are identity-safe;
- generation publish/sync either commits fully or leaves visible repair work;
- compatibility aliases are inventory-tracked and not exposed by default.

allowed examples: a corrupt-line fixture that reports loss and preserves good
rows; a stale lock test that does not delete another writer's lock.

anti-examples: "indexed N rows" after silently skipping malformed source lines;
fallback fields that make old payloads pass while foreground behavior remains
broken.

focused command or fixture:

```powershell
python -m pytest tests\aippocampus\test_source_io_kernel.py tests\aippocampus\test_generic_jsonl_integration_smoke.py tests\aippocampus\test_sync_bundle.py tests\aippocampus\test_update_sync.py -q
```

owner: source IO / sync / compatibility guard tracks.
