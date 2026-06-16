# Ecosystem Integration Matrix

Status checked: 2026-06-02.

This is the canonical public matrix for AIppocampus ecosystem-support claims.
It distinguishes source import, agent read tools, native host integration, and
automatic ambient recall so the project does not clear integration issues by
overstating what has actually been smoked.

For the shared host-readiness labels (`cli_only`, `recall_only`,
`recall_deepen`, `ambient_recall_deepen`, and `full_continuity_path`), use the
[host-agnostic continuity conformance contract](../architecture/host/continuity-conformance-contract.md).

## Support Terms

- **Data import/export** means AIppocampus can ingest or emit source-backed
  artifacts for a host, usually through generic JSONL, clean source, or sync
  bundles. It does not imply the host can call memory tools at runtime.
- **Agent read tools** means an agent host can call the local CLI or MCP
  read-only surfaces after the user has installed and configured them.
- **Native host integration** means AIppocampus has host-specific setup,
  documented permissions, and at least one host-specific smoke.
- **Ambient automatic recall** means the host receives memory cues without the
  user manually running import/search. Today this is host-specific, not a
  generic ecosystem promise.
- **Verified** means repository tests or smoke scripts exercise the path.
  **Documented** means setup is described, but a row may still be
  host-specific or diagnostic-only. **Planned** means the shape is plausible but
  the repository does not yet carry a dedicated adapter or smoke.

## Matrix

| Host family | Supported path today | Minimum integration shape | Permissions and privacy | Latency and foreground/background | Failure modes and degradation | Smoke status | Smallest runnable example or blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Codex Desktop / Codex CLI | Verified local provider, Codex-specific hooks, CLI, MCP, plugin packaging, and clean-source registry paths. Codex hooks are not a generic host contract. | Codex provider discovery plus `aippocampus onboard --provider codex`, MCP tools, or explicit Codex hook install. | Reads local Codex history and may install Codex hook config only after explicit operator command. Generated artifacts stay in the configured AIppocampus registry, not the project repo. | CLI/MCP reads are foreground. Codex prompt/lifecycle hooks can run ambiently after install. Background jobs are optional. | Missing Codex history, stale clean source, disabled hooks, or unavailable registry degrade to status diagnostics and explicit onboarding/search. | Verified by Stage 0-5 readiness, prompt-hook, Codex long-session, plugin, and registry smokes listed in the evidence map. | Start with [install-guide.md](install-guide.md) and [public-api.md](public-api.md). |
| Claude Code | Supported through Claude Code local-history onboarding and MCP setup. No Claude hook or native ambient-recall claim. | `aippocampus onboard --provider claude-code` plus Claude Code MCP configuration. | Reads local Claude Code history selected by the user/operator. MCP outputs default to redacted local paths. | Foreground setup and MCP calls. No background Claude hook is claimed. | Missing local history, incomplete MCP config, or host stdio issues degrade to status probes and manual CLI checks. | Verified by Claude Code MCP host and local-history parser smokes listed in the evidence map; the provider conformance kit covers the normalizer/source-ref contract. | Use [claude-code-mcp.md](setup/claude-code-mcp.md). |
| Generic MCP hosts | MCP protocol surface exists, but each host remains unverified until a host-specific round trip is added. | Configure the host to launch `aippocampus mcp` or the packaged MCP server and call documented read tools. | Read-mostly. Broad memory writes, hook install/uninstall, sync push/pull, and arbitrary file ingest through MCP are intentionally unsupported. | Foreground host tool calls over local stdio. Background behavior belongs to the host and is not claimed here. | Client schema mismatch, missing stdio support, or unsupported mutation requests return structured MCP errors instead of broad writes. | Tool catalog and JSON-RPC surfaces are covered by MCP tests/smokes; generic host compatibility is not a blanket claim. | Run `aippocampus mcp status` first; use `aippocampus mcp list-tools --json` only when schema inspection is needed. Add a host-specific smoke before claiming that host. |
| Generic JSONL producers | Verified provider-neutral import for visible transcripts from hosts without bespoke providers. This is data import, not native runtime integration. | Emit one JSONL row per visible message with `session_id`, `role`, and `text`, then run `aippocampus import conversation --format generic-jsonl --input <path>`. | Local transcript file is private operator input. Stable ids and source refs are identity; local paths are private locators. | Foreground validation/import. Search becomes available after registry clean source is built. | Missing required fields, changed `session_id`, unsupported roles, unknown `turn_id`, or orphan assistant rows fail with line-level diagnostics. | Verified by registry/clean-source tests, the generic JSONL ecosystem smoke, and the provider conformance kit normalizer/failure examples. | See the runnable example in [../../examples/generic-jsonl-integration/README.md](../../examples/generic-jsonl-integration/README.md). |
| LangGraph | Planned/unverified framework integration. AIppocampus does not ship a LangGraph adapter today. | Until a real adapter exists, a LangGraph app can only be documented as producing generic JSONL or invoking local CLI/MCP wrappers in its own code. | The app owner must decide what transcript text is exported and get user consent before importing. | Framework callbacks would be foreground or app-background depending on the app. AIppocampus has not smoked that path. | Callback drift, dependency churn, and unclear source refs degrade to generic JSONL export/import only. | No dedicated smoke. | Blocker: add a minimal LangGraph sample plus import/search smoke before claiming support. |
| AutoGen | Planned/unverified framework integration. | Export visible messages as generic JSONL or call local CLI/MCP from an AutoGen-controlled tool wrapper after a sample exists. | Treat agent transcripts as private; do not import hidden prompts, credentials, or non-visible tool payloads as memory truth. | Not characterized. | Group-chat role ambiguity and tool payload noise should fail closed until the sample preserves user/assistant source refs. | No dedicated smoke. | Blocker: add a minimal AutoGen transcript fixture and smoke. |
| CrewAI | Planned/unverified framework integration. | Export visible task/agent conversation rows as generic JSONL or call CLI/MCP from a CrewAI tool wrapper after a sample exists. | The app owner must separate visible conversation from internal planning or secrets before import. | Not characterized. | Role/task mapping ambiguity degrades to explicit JSONL validation errors or no import. | No dedicated smoke. | Blocker: add a minimal CrewAI sample with source-ref policy. |
| OpenAI Agents SDK | Optional function-tool contract smoke exists. This is not native host support and not an official OpenAI partnership claim. | Install `.[openai-agents]`, then wrap local AIppocampus read surfaces as app-owned SDK function tools. The current smoke verifies `Agent` + `function_tool` schema wiring only; it does not run `Runner` or call a model. | Hosted model inputs must stay limited to app-owned query text plus source ids/titles. Do not forward private registry locators, raw transcripts, credentials, or local machine details. | Foreground SDK app/tool execution only. No OpenAI Agents SDK ambient-recall hook or background ingestion is claimed. | Missing optional dependency, API-key/model setup for real runner calls, SDK tool-contract drift, or lack of local operator consent degrade to generic JSONL, CLI/MCP read tools, or no native claim. | Verified by the optional CI smoke after `python -m pip install -e ".[openai-agents-smoke]"`; the user-facing extra remains `.[openai-agents]`. Official SDK quickstart/tools docs checked 2026-06-02. | Run `python -m unittest tests.aippocampus.test_openai_agents_sdk_smoke -v`. Next blocker for stronger support: add an app-owned Runner/MCP round trip with explicit consent and sanitized hosted inputs. |
| Cursor / VS Code agent surfaces | MCP-compatible path only when the specific IDE agent surface supports a compatible local MCP setup; otherwise use explicit generic JSONL import. No IDE-native adapter is claimed. | Per-host MCP config or exported transcript import. | Local IDE workspace paths and chat history are private locators unless redacted. | Foreground MCP calls or manual import. No ambient IDE hook is claimed. | IDE MCP differences, extension sandboxing, or unavailable transcript export degrade to manual CLI checks. | No dedicated Cursor or VS Code smoke. | Blocker: add a per-IDE setup doc and smoke before claiming support. |
| Browser chat capture or companion flows | Prototype browser companion can explicitly export redacted generic JSONL. It is not an official browser-chat integration and does not auto-import. | User-enabled local capture/search in the prototype, then explicit `aippocampus import conversation --format generic-jsonl`. | Capture is off by default; v1 records store redacted/bounded visible text in browser local storage, and export remains redacted. Legacy/raw localStorage records are treated as mixed/legacy state, not a safe wider-web support claim. | Local browser foreground interaction. No background service or remote browser API is claimed. | DOM drift, disabled capture, local storage loss, legacy/raw localStorage records, malformed export, or assistant-only turns degrade to no import or validation errors. | Covered by `tests/aippocampus/test_browser_memory_companion.py`; current browser DOM stability and extension-isolated storage are not proved. | See [../../examples/browser-memory-companion/README.md](../../examples/browser-memory-companion/README.md). |
| Enterprise/internal agent runtimes | Supported as a composable pattern through generic JSONL import, local CLI/MCP read tools, and documented sync/export surfaces. No enterprise runtime adapter or hosted service is claimed. | Internal runtime writes visible transcript rows or bundles clean source, imports locally, then exposes read access through CLI/MCP under its own policy. | Requires local operator consent, storage selection, path redaction for forwarded results, and a decision about whether sync bundles may leave the device. | Import/search is foreground unless the enterprise runtime builds its own scheduler. AIppocampus does not claim managed background ingestion here. | Policy restrictions, malformed exports, missing registry, or sync refusal degrade to dry-run diagnostics and no memory write. | Verified by the generic JSONL ecosystem smoke for data import plus MCP search; sync surfaces have separate smokes in the evidence map. | Run `python tools/aippocampus/smoke/smoke_generic_jsonl_integration.py --json`. |

## Claim Boundary

Public copy may say AIppocampus provides source-backed local memory surfaces for
Codex, Claude Code, MCP-compatible read tools, and provider-neutral JSONL
imports. Public copy may also mention the optional OpenAI Agents SDK
function-tool contract smoke, but must not call it native OpenAI Agents SDK
support, ambient recall, or hosted Runner integration. Public copy must not say
LangGraph, AutoGen, CrewAI, Cursor, VS Code, or browser chat products have
native AIppocampus support until their rows gain host-specific examples and
smokes.

When adding a new ecosystem row, include a runnable example or an explicit
blocker, then update the evidence map if the claim depends on a new smoke
script. Keep schema details in [public-api.md](public-api.md) and
[public-core-boundary.md](public-core-boundary.md) instead of mirroring them
here.
