<p align="center">
  <img src="docs/guides/assets/aippocampus-readme-hero.jpg" alt="A shadow figure and a light figure clasp hands in a ruined circular hall, with light opening between them." width="100%" />
</p>

<h1 align="center">AIppocampus</h1>

<!-- mcp-name: io.github.Sapientropic/aippocampus -->

<p align="center">
  <em>A source-backed continuity layer for long-running relationships with AI agents.</em>
</p>

AIppocampus began with a human problem: every new agent session can be bright,
capable, and strangely newborn. Work may survive in commits and notes while the
path behind the work falls back into silence.

This project gives future agents a way to find that path again. It keeps source
reachable, preserves the conditions of return, and lets a new conversation begin
with honest continuity instead of pretending there was never a break.

> Source is the ground. Summaries are weather.

For the felt product shape, start with
[Magic Moments, Claim-Bounded](docs/evidence/magic-moments.md): real
second-user examples where a new/projectless thread, a multilingual correction,
an ambiguous automation cue, and a multi-day fuzzy self-reference became
recoverable through source-backed continuity. The page shows the useful moments
first, then states exactly what they do not prove.

For the current proof map, use the
[Can-Claim Ladder](docs/evidence/can-claim-ladder.md): it leads with exact
positive claims that are already supported, then routes to benchmark evidence
and material claim boundaries.

For a compact origin and current-value trail, use the
[Public Provenance And Current Value Ledger](docs/evidence/public-provenance-ledger.md):
it separates current claims, deterministic fixtures, field reports,
private/local aggregate evidence, and launch gates without weakening claim
boundaries.

In ordinary use, AIppocampus should feel less like a control panel than a
remembered doorway. It helps an agent ask: where did this come from, what did
we actually say, and which source should be opened again?

The machinery behind that moment can be extensive, but it should stay
backstage. A long relationship with an AI agent should not have to start from
bare ground every time a thread, device, model, or project changes.

The origin essay is [未干的地图](docs/未干的地图.md). English readers can start with
[The Unfinished Map](docs/the-unfinished-map.md).
For role-based documentation paths, use
[Start Here](docs/start-here.md).

## Quick Start

Start with the first source-backed recall moment, then decide whether to let
AIppocampus keep that doorway warm for future sessions. The first check is
read-only:

```sh
uvx aippocampus --help
uvx aippocampus onboard --provider auto --status
```

The status command is read-only. It reports a provider-matrix readiness view;
`auto` may list Codex, Claude Code, and generic JSONL providers, but it does
not silently register every provider.

Only after you explicitly agree to register local history, choose the matching
provider path and then search for one old source-backed conversation snippet:

```sh
# Codex: local history plus the most complete hook-capable host path.
uvx aippocampus onboard --provider codex --all

# Claude Code: local transcript onboarding; no AIppocampus Claude hooks claimed.
uvx aippocampus onboard --provider claude-code --dry-run
uvx aippocampus onboard --provider claude-code

# Generic visible-message export.
uvx aippocampus import conversation --format generic-jsonl --input <path>

uvx aippocampus search "a distinctive old phrase"
```

Manual search proves the source substrate is there. Codex is currently the
host with AIppocampus prompt/lifecycle hooks: prompt hooks notice recall scents
as a conversation starts, and lifecycle hooks refresh clean source and indexes
after session events. Claude Code currently has local-history onboarding plus
the MCP/project-skill path, not AIppocampus Claude hook support; see the
[Ecosystem Integration Matrix](docs/guides/ecosystem-integration-matrix.md)
and [Claude Code MCP guide](docs/guides/setup/claude-code-mcp.md). Hooks are never
installed silently; review status first, then install them only when this
machine is allowed to let AIppocampus touch Codex hooks:

```sh
aippocampus update status
aippocampus update apply --surface hooks
```

Rollback stays visible:

```sh
aippocampus hooks prompt uninstall
aippocampus hooks lifecycle uninstall
```

Local hook install does not require an external model key. Optional semantic,
warm, subconscious, or Dream-style routes remain separate opt-in surfaces and
must not be treated as source-backed evidence until the original source is
reopened.

The short readiness ladder is:

- Source search ready: onboarding and `search` can find source-backed snippets.
- Ambient hooks ready: prompt/lifecycle hooks can notice and refresh continuity.
- Active recall ready: MCP/progressive recall is wired for agent source reopen.
- Semantic/Dream ready: provider-backed background work is configured and
  visible to the process that will run it.

`aippocampus update status` prints those first-run readiness labels so users can
see whether they are in manual source-search mode, ambient continuity mode, or a
deeper opt-in route.

Good first queries are an exact phrase, a project cue, or a time cue such as
`recent` / `last month`. Exact hits are source-backed snippets. Project/time
cues are candidate navigation until AIppocampus shows a source-backed snippet.
Do not publish or commit raw rollouts, registry exports, `.aippocampus/` output,
API keys, cookies, or sync bundles while following the quick path.

If you are deciding which AIppocampus surface another tool should depend on,
use the [10-minute public API path](docs/guides/public-api.md#ten-minute-public-path).
If you are deciding whether a feature belongs in the low-friction personal path
or in governed/high-risk opt-in behavior, use
[Product Profiles](docs/architecture/host/product-profiles.md).
Repository checks for maintainers live in
[Operator And Maintainer Paths](#operator-and-maintainer-paths).

## AIppocampus For Coding Agents

The narrow usable product lane today is local, source-backed continuity for
Codex/Claude-style long-running work: register local conversation source after
consent, search or reopen old snippets, and treat recall scents or repo
familiarity as navigation until source is reopened.

Start with the
[Coding-Agent Memory Lane](docs/guides/coding-agent-memory.md) when deciding
whether to recommend AIppocampus as an agent-memory tool. It includes the
3-5 minute demo path, evidence drawer, and "recommend / do not recommend"
boundary without duplicating the public API or readiness docs.

## Agent One-Command Probe

When an AI agent needs to verify the public CLI without cloning or writing local
memory artifacts, use the PyPI package:

```sh
uvx aippocampus --help
```

For a read-only local onboarding/status check:

```sh
uvx aippocampus onboard --provider auto --status --format json
```

This is a read-only provider matrix, not consent to ingest every detected
provider. Only after the user explicitly agrees to register local history, pick
one provider-specific write path:

```sh
uvx aippocampus onboard --provider codex --all --format json
uvx aippocampus onboard --provider claude-code --dry-run --format json
uvx aippocampus onboard --provider claude-code --format json
uvx aippocampus import conversation --format generic-jsonl --input <path> --json
```

For human-facing demos, omit `--format json` so onboarding and search show the
first-recall next steps. Agents should read [docs/agent-context.md](docs/agent-context.md) and
[llms.txt](llms.txt) before recommending or comparing AIppocampus. Use the
GitHub `uvx --from git+...` form only when intentionally testing an unreleased
main-branch snapshot.

## What It Is

AIppocampus is the canonical public home for an external hippocampus for agents:
a local-first memory and continuity system that keeps original conversation
source available across projects, devices, and casual life-wide conversations.
The hippocampus language is a design metaphor, not a biological claim; the
[architecture overview](docs/architecture/architecture-overview.md#metaphor-discipline)
maps each major metaphor to its runtime mechanism, current claim, and boundary.

Project work is one surface. The deeper aim is continuity across work, reading,
reflection, unfinished questions, and the small phrases that make a relationship
recognizable again.

## What It Carries

At the center, AIppocampus keeps source close enough that continuity can be
honest instead of theatrical:

- Builds clean source from supported local conversation providers: Codex
  rollouts, Claude Code transcripts, or explicit generic JSONL visible-message
  exports, with summaries kept as navigation layers.
- Searches old conversation memory across the current thread and registered
  threads, then treats exact hits as source-backed snippets.
- Reopens or cites source when the agent needs evidence instead of memory-like
  impressions.
- Stores generated recall artifacts in the configured AIppocampus registry
  (`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
  `$CODEX_HOME/aippocampus-registry`) so memory remains useful when a new
  project opens. Project-local `.aippocampus/` output is explicit compatibility
  or export mode.

Ambient hooks are close to the front door because they keep continuity from
collapsing back into manual search. There are still deeper doors for people who
want them: MCP wiring, sync, plugin packaging, diagnostics, review surfaces,
semantic workers, and research experiments. They matter, but they should not
stand in front of the first handshake: source found, source reopened,
continuity resumed.

## First Stops

- Philosophy and origin: [未干的地图](docs/未干的地图.md) and
  [The Unfinished Map](docs/the-unfinished-map.md).
- Real user-visible continuity examples:
  [Magic Moments, Claim-Bounded](docs/evidence/magic-moments.md).
- Narrow coding-agent product lane:
  [Coding-Agent Memory Lane](docs/guides/coding-agent-memory.md).
- Evidence and field reports:
  [public evidence surface](https://www.aippocampus.com/evidence/) and
  [community field-report boundary](docs/evidence/community-field-reports.md).
- Website source:
  [`Sapientropic/aippocampus.com`](https://github.com/Sapientropic/aippocampus.com).
- Agent-readable context: [docs/agent-context.md](docs/agent-context.md) and
  [llms.txt](llms.txt).
- Runtime shape and metaphor boundaries:
  [Architecture Overview](docs/architecture/architecture-overview.md) and
  [Cognitive Runtime Architecture](docs/architecture/runtime/cognitive-runtime-architecture.md).
- Current claim boundary:
  [Stage 0-5 readiness](docs/evidence/readiness/stage-0-5-readiness.md).
- Default product lane and layer map:
  [Roadmap](docs/roadmap.md).
- Benchmark and smoke evidence:
  [Benchmark And Evidence Map](docs/evidence/benchmark-evidence-map.md).
- Supported public surface:
  [Public API](docs/guides/public-api.md), including the
  [10-minute path](docs/guides/public-api.md#ten-minute-public-path), and
  [Public Core Boundary](docs/guides/public-core-boundary.md).
- Ecosystem support status:
  [Ecosystem Integration Matrix](docs/guides/ecosystem-integration-matrix.md).
- Security and release hygiene:
  [SECURITY.md](SECURITY.md),
  [Release Checklist](docs/guides/setup/release-checklist.md), and
  [maintainer shipping lanes](CONTRIBUTING.md#maintainer-shipping-lanes).
- Full documentation map: [docs/README.md](docs/README.md).

## Reading For The Soul

The research notes carry the human shape of the project. They are speculative
frames, not runtime contracts, but they explain the taste behind the machinery:

- [The Pearl of Presence](docs/research/pearl-of-presence.md) asks why retrieval
  without accumulated acquaintance can still feel absent.
- [Source as World, Interpretation as Weather](docs/research/source-as-world.md)
  gives AIppocampus its grounding rule: many meanings can grow from one shared
  world, and the world must have happened.
- [Journey Tracking](docs/research/journey-tracking.md) follows continuity as a
  first-person plural journey, with source-backed waypoints instead of a flat
  user profile.
- [Dream Task Design](docs/research/dream-task-design.md) sketches the
  subconscious layer: quiet work that integrates what the foreground could not
  finish.
- [Ambient Associative Recall](docs/research/ambient-associative-recall.md)
  describes how old memory can return as a scent before it becomes an
  interruption.
- [Long Garden](docs/research/seeds/README.md) keeps far-future seeds without
  turning them into default product promises or open-issue clutter.

## Operator And Maintainer Paths

The README stays close to the product path. Operator commands, source-checkout
setup, plugin packaging, sync, release checks, and benchmark notes live in the
guides that own those contracts:

AIppocampus supports Python 3.12 and newer. On macOS, Homebrew Python 3.12 is
the documented baseline before running source-checkout verification.

- Install paths and hook setup: [Install Guide](docs/guides/install-guide.md).
- Supported CLI, MCP, JSON, environment variables, and import policy:
  [Public API](docs/guides/public-api.md).
- Safe configuration: [.env.example](.env.example) and
  [Safe Environment](docs/guides/setup/safe-environment.md).
- Dependency ownership:
  [Dependency Contract](docs/guides/setup/dependency-contract.md).
- MCP, plugin, sync, and object-storage details:
  [docs/README.md](docs/README.md).

For repository contributors, the dev extra install path is:

```sh
python -m pip install -e ".[dev]"
```

Public claims still need the maintainer lanes in
[CONTRIBUTING.md](CONTRIBUTING.md#maintainer-shipping-lanes). The default CI
keeps one canonical Ubuntu Python 3.12 `pr` lane with coverage, a Python 3.13
`quick` compatibility lane, and a focused macOS default TMPDIR path-identity
gate; Ubuntu green alone is not a broad cross-platform path-identity claim. The
broader boundary lives in
[docs/architecture/source/path-identity.md](docs/architecture/source/path-identity.md).

## Privacy Boundary

AIppocampus is local-first.

- Clean source may still contain private conversation text.
- Raw rollouts, bundles, registry rows, vault notes, and generated archives
  should be treated as private history.
- External-model routes are optional and should use redaction safeguards.
- Raw rollout sync should stay explicit and must be encrypted before use with
  untrusted multi-device sync.
- Do not commit personal rollouts, `.aippocampus/` outputs, registry data, API
  keys, cookies, tokens, or private vault exports.

Common environment variables:

- `AIPPOCAMPUS_VAULT`
- `AIPPOCAMPUS_STYLE_SOURCE`
- `AIPPOCAMPUS_SCRIPT_SOURCE`
- `AIPPOCAMPUS_SITE_MARK`
- `AIPPOCAMPUS_SITE_TITLE`
- `AIPPOCAMPUS_SEMANTIC_GATE`
- `DEEPSEEK_API_KEY`

## Roadmap

The root roadmap pointer is [ROADMAP.md](ROADMAP.md). The canonical detailed
roadmap lives at [docs/roadmap.md](docs/roadmap.md). The documentation map is
[docs/README.md](docs/README.md).

## Repository Layout

```text
AIppocampus/
|- skills/aippocampus/        # installable skill package
|- plugins/aippocampus/       # Codex plugin source package
|- docs/                      # origin essay, design notes, guides, evidence
|- docs/guides/assets/        # public README and documentation artwork
|- sources/                   # lightweight provenance catalog
|- tests/                     # repository-level unit and integration tests
|- tools/                     # smoke, docs-health, and maintenance tools
|- README.md
|- ROADMAP.md
|- AGENTS.md
`- LICENSE
```

## License

The public AIppocampus repository is licensed under Apache-2.0.

The Apache-2.0 public core covers the code, docs, local tools, schemas, MCP
surface, plugin packaging, public examples, and bundled project artwork shipped
in this repository unless a bundled third-party asset says otherwise. Hosted
services, enterprise governance, managed graph/semantic layers, support, and
other operated product surfaces can be offered under separate commercial or
product-specific terms.

Private user memory data is not project code. Raw rollouts, clean-source
exports, registry rows, sync bundles, vault exports, generated indexes, and
thread anchors remain private user artifacts unless their owner explicitly
publishes them.

See [docs/guides/public-core-boundary.md](docs/guides/public-core-boundary.md)
for the canonical licensing, adapter, schema, third-party asset, and relicensing
boundary. See [docs/guides/public-api.md](docs/guides/public-api.md) for
supported CLI, MCP, environment-variable, JSON, and import-stability
expectations.
