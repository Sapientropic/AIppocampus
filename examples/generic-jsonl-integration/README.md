# Generic JSONL Integration Example

This example shows the safest non-Codex/non-Claude integration path:
an internal or third-party agent runtime exports visible conversation rows as
AIppocampus `generic-jsonl`, then a local operator imports that file into the
registry.

It demonstrates **data import** and, after import, **agent read access through
CLI/MCP**. It does not demonstrate native framework support, automatic ambient
recall, hosted memory, or official partnership with any agent framework.

## Example Transcript

[`internal-agent-session.jsonl`](internal-agent-session.jsonl) contains one
synthetic user/assistant turn. Each row has the required public fields:

- `session_id`
- `role`
- `text`

The optional `timestamp`, `turn_id`, `source_ref`, and `provider_metadata`
fields make the example easier to audit but are not a second schema owner. The
canonical schema and validation boundary remain in
[../../docs/guides/public-api.md](../../docs/guides/public-api.md#generic-jsonl-import).

## Validate Only

From the repository root:

```sh
python skills/aippocampus/scripts/aippocampus_cli.py import conversation --format generic-jsonl --input examples/generic-jsonl-integration/internal-agent-session.jsonl --project "Internal Agent Demo" --dry-run --json
```

PowerShell users can run the same command; no shell-specific environment
variable is needed for this explicit input path.

The dry run should report:

- `ok: true`
- `dry_run: true`
- `source_provider: generic-jsonl`
- `thread_key: generic-jsonl:session:internal-agent-demo-001`

## Import Locally

To create clean-source artifacts in your configured AIppocampus registry:

```sh
python skills/aippocampus/scripts/aippocampus_cli.py import conversation --format generic-jsonl --input examples/generic-jsonl-integration/internal-agent-session.jsonl --project "Internal Agent Demo" --json
```

Use `AIPPOCAMPUS_REGISTRY_DIR` or `AIPPOCAMPUS_HOME` if you want the import to
land outside the default local registry. Do not commit generated registry
artifacts, raw exports, or private local paths.

## Repository Smoke

The deterministic smoke uses a temporary transcript and registry, then searches
the imported clean source through MCP:

```sh
python tools/aippocampus/smoke/smoke_generic_jsonl_integration.py --json
```

That smoke is the dated evidence for the ecosystem matrix's
generic-JSONL/internal-runtime claim. Framework-specific claims still need their
own adapter examples and smokes.
