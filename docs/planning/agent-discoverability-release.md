# Agent Discoverability Release Plan

This plan tracks what remains before AIppocampus can be treated as fully
agent-discoverable across LLM context files, one-command install, and the MCP
Registry.

## Current Truth

- `uvx --from git+https://github.com/Sapientropic/AIppocampus.git aippocampus --help`
  is the verified clone-free probe.
- `uvx --from git+https://github.com/Sapientropic/AIppocampus.git aippocampus onboard --provider codex --status --format json`
  is the verified read-only onboarding/status probe.
- `uvx --from git+https://github.com/Sapientropic/AIppocampus.git aippocampus mcp list-tools`
  is the verified clone-free MCP tool catalog probe.
- The shorter `uvx aippocampus ...` form is not yet valid because the package is
  not published on PyPI.
- `server.json` is a conservative MCP Registry metadata draft. Publishing it
  still requires a package artifact accepted by the official registry flow.

## Required Before MCP Registry Publication

1. Publish an installable artifact through a registry supported by the MCP
   Registry.
   - Preferred first path: PyPI package `aippocampus`.
   - Alternative later path: MCPB or OCI artifact if the binary/package story
     becomes clearer.
2. Ensure the package README on PyPI includes the exact marker:

   ```html
   <!-- mcp-name: io.github.sapientropic/aippocampus -->
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
will not succeed until the PyPI trusted publisher/project setup exists for
`aippocampus`.

It can run in two equivalent ways:

- automatic: push a matching tag such as `v0.1.0`;
- manual: run the workflow from GitHub Actions with `release_tag` set to an
  existing tag such as `v0.1.0`.

Both paths check that the release tag matches `pyproject.toml` and that the
checked-out commit is exactly the tag commit before publishing. Do not use the
manual trigger to publish an arbitrary branch.

Run the repeatable readiness probe before and after external publication:

```sh
python tools/aippocampus/release/check_agent_discovery_release.py --json
```

Before PyPI/MCP publication it should report local checks as passing and public
package/registry checks as `pending`. After the release workflow succeeds, run:

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
