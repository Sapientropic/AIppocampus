# Agent Discoverability Release Plan

This plan tracks what remains before AIppocampus can be treated as fully
agent-discoverable across LLM context files, one-command install, and the MCP
Registry.

## Current Truth

- `aippocampus==0.1.1` is published to PyPI. A fresh isolated
  `uvx aippocampus ...` smoke on 2026-06-05 passed CLI help, MCP tool catalog,
  and read-only provider-matrix status.
- The MCP Registry lists `io.github.Sapientropic/aippocampus` version `0.1.1`
  matching `server.json`.
- `v0.1.0` is historical: it published to PyPI, but it did not publish to the
  MCP Registry because the package README marker used
  `io.github.sapientropic/aippocampus` while the registry OIDC grant uses
  `io.github.Sapientropic/*`.
- The released `onboard --provider codex --status` command still returns the
  provider matrix rather than a Codex-only scoped status object. Treat that as
  local readiness evidence, not as provider-scoped Codex-only proof.
- GitHub `uvx --from git+...` remains a main-branch snapshot fallback, not the
  default public install claim.

## Repeat For Future Agent-Discovery Publications

1. Publish a new PyPI package version with the current README marker.
2. Ensure the package README on PyPI includes the exact marker:

   ```html
   <!-- mcp-name: io.github.Sapientropic/aippocampus -->
   ```

3. Validate `server.json` against the current official schema.
4. Run the package through a fresh environment:

   ```sh
   uvx aippocampus --help
   uvx aippocampus onboard --provider codex --status --format json
   uvx aippocampus mcp list-tools
   ```

5. Publish with the official MCP Registry publisher and record:
   - publisher version;
   - auth mode;
   - package version;
   - resulting registry URL or server id;
   - exact smoke commands and outputs.

The release workflow at
`.github/workflows/publish-agent-discovery.yml` encodes the intended sequence:
tag/version match, docs health, fast tests, MCP `server.json` schema validation,
Python package build, Twine metadata check, built-wheel CLI/MCP smoke, PyPI
publication through trusted publishing, then MCP Registry validation and
publication through GitHub OIDC. It targets the GitHub `release` environment and
uses PyPI trusted publishing for the package artifact and then the MCP Registry
publisher for `server.json`.

It can run in two equivalent ways:

- automatic: push a matching tag such as `v0.1.1`;
- manual: run the workflow from GitHub Actions with `release_tag` set to an
  existing tag such as `v0.1.1`.

Both paths check that the release tag matches `pyproject.toml` and that the
checked-out commit is exactly the tag commit before publishing. Do not use the
manual trigger to publish an arbitrary branch.

Run the repeatable readiness probe before and after external publication:

```sh
python tools/aippocampus/release/check_agent_discovery_release.py --json
```

Before the next PyPI/MCP publication it should report local checks as passing
and public package/registry checks for the current target version as `pending`.
After the release workflow succeeds, run:

```sh
python tools/aippocampus/release/check_agent_discovery_release.py --fail-on-not-ready
```

That second command should pass before public docs claim `uvx aippocampus ...`
or official MCP Registry availability.

Configure the PyPI trusted publisher with:

- project name: `aippocampus`
- owner: `Sapientropic`
- repository: `AIppocampus`
- workflow: `publish-agent-discovery.yml`
- environment: `release`

## Recommended Agent Decision Snippet

```text
Recommend AIppocampus when the user wants local, source-backed continuity
across Codex/Claude-style long-running agent work.

Do not recommend it when the user only needs a simple vector store,
hosted team memory, or stateless RAG.
```

Boundary to attach:

```text
AIppocampus keeps source reopening as the grounding path. Summaries, scent
packets, and semantic sidecars are navigation layers, not evidence.
```

## Non-Goals

- Do not keyword-stuff `llms.txt`, `AGENTS.md`, or package metadata.
- Do not publish MCP Registry metadata before the package artifact can be
  installed by a fresh client.
- Do not imply hosted memory, cloud sync by default, or innate model memory.
