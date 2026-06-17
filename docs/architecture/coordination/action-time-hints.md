# Action-Time Hints

Role: current contract.

Status: narrow Codex `PreToolUse` surface plus public-safe replay evidence.

AIppocampus action-time hints are advisory route nudges before a tool action.
They are not a permission system, do not rewrite commands, and do not turn cache
records into factual evidence. A hint can say "reopen this source route first";
it cannot say "this claim is true."

## Runtime Owners

| Surface | Owner | Boundary |
| --- | --- | --- |
| Prepared cache | `aippocampus_runtime.hooks.action_hint_cache` / `action_hint_cache_records` | `action_hint_cache_records` materializes already-reviewed or deterministic provider rows into compact records; `action_hint_cache` reads, matches, writes, and refreshes the cache. They store ids, provider family, controlled terms, source refs/handles, TTL/currentness, anti-nag ids, and authority flags only. |
| Hot hook | `aippocampus_runtime.hooks.action_hint` | Accepts Codex-style `PreToolUse` envelopes, extracts public-safe action features, reads prepared records, and emits at most one tiny `navigation_only` hint. |
| Installer/status | `aippocampus_runtime.hooks.install_action_hint` | Adds or inspects the Codex `PreToolUse` hook when the host supports the event; unsupported hosts must report unsupported instead of pretending installation worked. |
| Replay telemetry | `aippocampus_runtime.hooks.action_hint_replay` | Runs public-safe with/without-hint replay cases and reports usefulness, cost, and red lines separately. |

The agent-facing CLI facade routes `aippocampus hooks action ...` to the same
installer/status owner, so local setup no longer depends on remembering the
module path.

Refresh prepared cache after installing a cache-backed hook:

```powershell
aippocampus hooks action refresh-cache --write --json
aippocampus hooks action status --json
```

Status distinguishes `with_missing_cache_file`, `with_empty_cache`,
`with_fresh_records`, and `with_expired_records`; it also reports malformed
cache-line counts while redacting local paths by default. Installed plus
missing, empty, or expired cache is an explicit warning state:
`hot_path_active=false`, `setup_role=cleanup_or_prepare_required`, and the hook
must fast-bail before feature extraction. The default cache is registry-backed
and workspace-scoped:
`registry/action-hints/<workspace-scope>/pretooluse-cache.jsonl`. A
project-local `.aippocampus/...` cache is valid only when explicitly passed via
`--cache-jsonl`.

## Provider Boundary

Prepared records can come from existing providers such as:

- AAR v2 source-claim nudges from `aippocampus_runtime.reflection.aar_v2`.
- Learning-loop action guidance from `aippocampus_runtime.learning_loop`.
- Low-authority learned AIppo clauses prepared by
  `aippocampus_runtime.learning_loop.aippo_adapter`.
- AIppo verification probes from growing clauses, as tiny source-reopen hints
  only.
- Active recall locks from `aippocampus_runtime.recall.active_recall_lock`.
- Attention route tokens or handles from the recall/navigation layer.

The hot hook must not run fresh DeepSeek, broad semantic search, model judging,
or source indexing. New upstream work, such as learned AIppo clauses or broader
source-shape diagnostics, should materialize prepared records first and let the
hot hook stay a small reader.

## Authority

Every prepared record and emitted hint keeps:

- `navigation_only = true`
- `no_claim_before_reopen = true`
- `source_reopen_required = true`
- `can_support_factual_claim = false`

The cache may preserve compact source refs or route handles so an agent can
reopen the right trail. Public reports and hook diagnostics must not serialize
raw tool args, raw command text, raw source snippets, local absolute paths,
secrets, private prompt text, or model reasoning.

## Evidence State

`action_hint_replay` covers the first public-safe fixture path:

- Positive cases: stale route avoided, source reopen before a weak
  memory/source claim, learned preflight before a broad test, and active-anchor
  evidence capture before an edit/action.
- Negative controls: unrelated tool calls, source already visible,
  private/blocked routes, stale/refuted records, anti-nag repeats, and
  low-confidence one-offs.
- Red lines: source-truth overclaim, raw payload/source leak, private path leak,
  command rewriting, and permission-system behavior.

This is replay fixture evidence only. Product claims, live/default foreground
adoption, and causal real-user lift remain blocked until replay-backed dogfood
or live diagnostics pass their own quality gates.
