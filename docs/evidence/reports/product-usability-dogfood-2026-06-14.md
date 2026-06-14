# Product Usability Dogfood - 2026-06-14

This note records a local product-usability dogfood run after syncing the local
AIppocampus install, plus the fix-verification pass from the same product
usability closeout. It is evidence for issue/PR review, not a broad release
certification.

## Scope

- Checkout: product-usability closeout branch after syncing from `main`.
- Local install path tested:
  - `git pull --ff-only --prune`
  - `aippocampus update apply --surface skill --json`
  - `aippocampus update apply --surface plugin --json`
  - `aippocampus plugin install --codex --verify --json`
  - `aippocampus update apply --surface hooks --json`
- Product surfaces tested:
  - readiness/status cards
  - plugin install and real Codex host probe
  - hooks and provider diagnostics
  - health, clean-source, index, checkpoint, and graphify maintenance
  - CLI help, `sync`, `mcp`, `search`, and `agent recall`
  - MCP tools through dynamic tool discovery
  - prompt-hook positive and negative dry-runs

Local paths, thread ids, private source text, handles, and credential values are
omitted from this report.

## What Worked

- Skill and repo-local plugin package sync succeeded. Verification reported no
  missing, stale, or extra files for both surfaces.
- Hook refresh was idempotent. Prompt and lifecycle hooks remained installed,
  and no hook change was needed.
- `aippocampus plugin install --codex --verify --json` succeeded and the real
  Codex app-server probe listed AIppocampus MCP tools. The probe called
  `sync_status` successfully and returned `agent_callable_status:
  host_live_probe_ok`.
- Provider diagnostics reported the configured external-model route as ready
  without printing credential values.
- Prompt hook behavior was directionally good:
  - relevant AIppocampus/product prompts surfaced a compact scent in roughly
    100 ms;
  - unrelated casual chat stayed silent;
  - an intentionally tiny elapsed-time budget failed open instead of blocking.
- MCP tools can be dynamically discovered and called from the foreground thread.
  `memory_health`, `sync_status`, and `recall_context` all returned structured
  results when invoked through the MCP surface.
- Clean source and index maintenance commands rebuilt the current thread
  artifacts successfully.

## Fix Verification Pass

After the product-usability fixes, the local installed AIppocampus command was
synced again and verified through the same frontstage surfaces.

- `aippocampus plugin install --codex --verify --json` succeeded with
  `agent_callable_status: host_live_probe_ok`, sixteen discovered tools, and
  the four agent-native read tools: `agent_aippo`, `agent_deepen`,
  `agent_explain`, and `agent_recall`.
- The verified host-probe result is now reused by `aippocampus plugin status
  --json` / `aippocampus update status --json`, so a successful install no
  longer leaves the canonical status card in an unverified state.
- Host probe stderr from unrelated Codex/RMCP integrations is now classified as
  nonfatal when the AIppocampus validation transaction succeeds.
- `aippocampus sync status --json` works without `--sync-dir` and reports the
  capability truth instead of failing usage parsing.
- `aippocampus mcp list-tools` works as the positional command shape and lists
  the new agent-native read tools.
- Hook foreground copy now names the selected agent-native pull action
  (`agent_aippo`, `agent_recall`, or `agent_deepen` with a handle fallback)
  instead of only pointing to legacy generic `recall_context`.
- `aippocampus health --json` and `aippocampus search --json` redact local
  paths by default; exact paths are opt-in through `--include-paths`.
- `aippocampus health --json` reports `ready_with_live_delta` when only a tiny
  active-thread delta remains after maintenance, with no blocking action.
- `aippocampus maintenance --cwd "$PWD" --json` runs clean-source before index
  and returns no failures or skipped build steps for the repaired surface.
- AIppo and Avatar posture foregrounding stay silent for unrelated tasks, while
  coding/product tasks still receive relevant working-contract guidance.
- `aippocampus agent recall` packets expose compact next-action hints and
  route-delta reason codes without moving source/provenance outside deepen or
  explain.
- Default human `aippocampus agent recall` output is now a compact frontstage
  route summary; the full structured packet and callable handles remain behind
  `--json` / MCP.

## Product Friction Findings Observed Before Fix

### 1. Verified Plugin Install Does Not Close The Readiness Loop

`aippocampus plugin install --codex --verify --json` can prove
`host_live_probe_ok`, but a subsequent `aippocampus update status --json` still
reports:

- `agent_callable_ready: false`
- `agent_callable_status: host_registered_tools_unverified`
- `next_command: aippocampus update status --json`

That is safe from an overclaim perspective, but it is not a finished product
experience. A user can run the exact verification command, get a successful live
probe, and still see the canonical status card say the agent-callable surface is
unfinished.

The same install result also mixed unrelated host/plugin stderr into the
success path. The top-level install reported `ok: true`, while the warning
summary said the probe had fatal stderr because another host integration needed
auth. The AIppocampus-specific probe was fine; the output did not make that
calmly obvious.

### 2. Privacy Boundaries And Local Path Redaction Are Inconsistent

Human `aippocampus health` output printed exact registry and rollout paths.
`health --json` also included exact local paths in several fields.

The MCP `memory_health` tool was better because many fields were redacted when
called with `include_private_paths=false`, but several nested fields still
included exact local paths. The same payload also stated privacy boundaries such
as `local_paths_included: false` / `local_paths_emitted: false`, which makes the
remaining path fields a trust bug rather than only a cosmetic issue.

Other path-heavy examples:

- `aippocampus search --json` included a source file path.
- health `recommended_actions[].command` embedded an absolute cwd.
- maintenance command success output printed artifact paths.

### 3. Health Feels Perpetually Dirty On Active Threads

After rebuilding clean source, index, checkpoint, and graphify corpus, a new
health run still returned `thread memory health: needs maintenance` because one
new visible message had arrived after the index build.

The strict freshness signal is useful for operators, but it makes an active
thread feel impossible to get clean. For an Apple-like personal path, the
frontstage should distinguish:

- fresh enough for normal use;
- slightly behind because the conversation is active;
- materially stale and action-needed;
- blocked/degraded.

The current output collapses tiny live deltas into the same "needs maintenance"
feeling as materially stale state.

Checkpoint maintenance also felt ambiguous. The command produced a "checkpoint
suggested" message, but later health still reported hundreds of messages since
the last captured checkpoint. A normal user cannot tell whether the command
captured, suggested, or merely previewed the checkpoint.

### 4. CLI And MCP Contracts Diverge

The MCP `sync_status` tool can report `available_requires_sync_dir` without
failing. The CLI command `aippocampus sync status --json` exits with a usage
error unless `--sync-dir` is supplied.

Other command-shape mismatches:

- Top-level help advertises `mcp list-tools`; subcommand help advertises
  `mcp --list-tools`. Both work or appear in different places, but the product
  vocabulary is not crisp.
- `aippocampus plugin status --json` feels like an obvious command after
  install, but `plugin` only exposes `install` and `uninstall`.
- health recommends raw `PYTHONPATH=... python -m ...` maintenance commands
  instead of a calm first-class maintenance command.
- `aippocampus maintenance --help` is not a command, even though the health
  problem is explicitly framed as "needs maintenance."

### 5. User-Facing Status Is Still Too Diagnostic-Shaped

`onboard --provider auto --status` and several non-`--json` commands emitted
JSON-like or path-heavy diagnostic payloads. That is helpful for maintainers but
too noisy for the ordinary personal path.

The product wants two different layers:

- a short frontstage card with state, one next action, and privacy-safe wording;
- an operator/debug layer with paths, counts, commands, host stderr, and
  low-level reason codes.

Right now those layers are still mixed in multiple places.

### 6. Prompt-Hook Affordance Is Compact, But Assumes Tool Discovery

The actual hook injection for a relevant prompt was compact and privacy-safe:
it said prior context may matter, suggested `recall_context`, and reminded the
agent to reopen source before claims. That shape is much better than the
diagnostic JSON.

The remaining product gap is discoverability. In a lazy-tool environment, the
foreground agent may first need dynamic tool discovery before it can call
`recall_context`. The hook text should either name the MCP/plugin surface in a
host-agnostic way or provide a fallback path when the tool is not currently
callable.

### 7. Recall CLI Defaults Are Not Human-First

`aippocampus agent recall` without `--json` still emitted a large structured
payload. Some `copy_paste_command` fields contain object-like handles that are
not shell-quoted. This is acceptable for a diagnostic surface, but not for a
frontstage recall command.

## Issue Slices

Recommended public issues from this run:

1. Agent-callable install/readiness regression after host live probe.
2. Local path redaction and privacy-boundary consistency across health/search
   and MCP tools.
3. Tolerant, action-complete health/maintenance frontstage for active threads.
4. CLI/MCP command contract cleanup for first-run personal workflows.
5. Optional follow-up under the existing AIppo/agent-affordance track for hook
   wording and lazy tool discovery.

## Cannot Claim

- This run does not prove retrieval quality across a benchmark corpus.
- This run does not prove every host, platform, or Codex Desktop version behaves
  the same way.
- The positive prompt-hook behavior was tested with public-safe prompts only.
- The local maintenance refresh produced usable artifacts, but health still
  marked the active thread as needing maintenance due to live conversation
  churn.
