# Safe Environment Setup

This is the safe local configuration entrypoint for contributors and operators.
The canonical environment-variable matrix remains
[public-api.md#environment-configuration-matrix](../public-api.md#environment-configuration-matrix);
this guide explains how to use the sample without leaking secrets or local
paths.

## Sample Config

Start from the checked-in template:

```sh
cp .env.example .env
```

`.env.example` contains only blank values or safe numeric examples. Real `.env`
files are ignored by git. Keep API keys, object-storage credentials, private
registry paths, local executable paths, and provider account ids in your private
shell or private `.env`, never in repository docs, issues, PRs, or plugin
metadata.

Provider-key discovery stays explicit. `aippocampus doctor provider` normally
checks only whether the selected environment variable is visible to the current
process and a child process. If you run
`aippocampus doctor provider --discover-credential-sources --credential-dotenv <path> --json`,
AIppocampus reads only that specified file and reports redacted candidate
metadata; it does not scan the repository, print the secret, or install a
credential bridge. Bridge installation is a separate explicit action through
`aippocampus onboard provider-key --apply`, which writes only local wrapper /
manifest glue and never stores the key value in public output or `hooks.json`.

Use `AIPPOCAMPUS_HOME` or `AIPPOCAMPUS_REGISTRY_DIR` for non-Codex storage.
`CODEX_HOME` remains a compatibility fallback for Codex installs, not the
preferred new storage API.

Optional external-model routes stay opt-in. Leaving `DEEPSEEK_API_KEY`,
`AIPPOCAMPUS_OPENAI_COMPAT_*`, object-storage credentials, or GitHub planning
tokens blank must not block local-first install, MCP listing, docs health, or
the manifest-classified `quick` / `pr` test tiers.

## Plugin MCP Environment

`plugins/aippocampus/.mcp.json` intentionally has no `env` block. Plugin-local
MCP configuration inherits the calling process environment so the public plugin
manifest does not duplicate the environment matrix or carry secret/local-path
placeholders.

If a host needs explicit env handoff, configure that host's private MCP settings
from your private `.env` or shell. Do not add real paths, API keys, bearer
tokens, object-store credentials, or registry exports to
`plugins/aippocampus/.mcp.json`.

## Isolated Runtime Option

AIppocampus does not currently ship a Dockerfile, docker-compose file, or
devcontainer as a supported contributor runtime. That is intentional for now:
a checked-in container would become a platform support signal and would need its
own package-install, sync, path-identity, and secret-handling smoke coverage.

Current substitutes:

- Use a repo-local virtual environment plus the pinned `.[dev]` extra from
  [dependency-contract.md](dependency-contract.md).
- Use the GitHub macOS install smoke for a clean hosted macOS install path:
  `.github/workflows/macos-install-smoke.yml`.
- Use `tools/aippocampus/smoke/smoke_alternate_runtime_sync.py` when Docker or
  WSL is available and you specifically need an alternate-runtime sync boundary.

The alternate-runtime smoke proves local-folder sync repair across a Docker/WSL
runtime boundary when that runtime is already available. This is not a release claim for a maintained container image,
managed cloud storage, or Python-free binary distribution.
