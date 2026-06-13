# Runtime Envelope And Failure Taxonomy

Role: current contract.

Status: current contract for GitHub #817.

AIppocampus has many focused runtime subpackages. File layout is useful, but it
is not itself a public contract. Public and agent-facing boundaries need a small
shared vocabulary for observable status, failures, configuration, and redaction
without forcing every internal helper or generated sidecar into the same schema.

The runtime vocabulary lives in
`aippocampus_runtime.contracts`. The configuration registry lives in
`aippocampus_runtime.config.registry`.

## Surface Classes

Use these classes when documenting or testing a runtime boundary:

| Class | Meaning | Envelope pressure |
| --- | --- | --- |
| `public_api` | End-user or agent-facing JSON surface such as CLI, MCP, hooks, import/export, search, and no-write diagnostics. | Prefer the shared public envelope vocabulary or map local errors into it. |
| `package_owner_cli` | Maintainer/operator CLI that may expose more detail but still runs from the packaged runtime. | Keep statuses and errors observable, redacted, and classified. |
| `generated_sidecar` | Local indexes, maps, cache rows, and status files consumed by another subpackage. | Local schemas are allowed, but cross-subpackage consumers need a named owner and failure/status fields. |
| `internal_helper` | Private module helpers, scoring functions, fixtures, and one-subpackage details. | Do not force a generic envelope; tests should guard the owner contract instead. |

Current subpackages allowed to export public runtime contracts are `cli`,
`config`, `hooks`, `mcp`, `onboarding`, `ops`, `registry`, `source`, `sync`, and
`update`. Other subpackages may own internal helpers, generated sidecars, or
domain contracts, but promoting them to a public surface should add a short
contract note and deterministic coverage.

## Public Envelope Vocabulary

Public runtime reports should use or map to these fields when practical:

| Field | Meaning |
| --- | --- |
| `ok` | Machine-readable success of the reported operation, not source truth. |
| `status` | One of `ok`, `partial`, `skipped`, `degraded`, `blocked`, or `error`. |
| `data` | Surface-owned payload. It may keep a local schema. |
| `warnings` | Non-fatal classified observations. |
| `errors` | Classified failures for callers and agents. |
| `next` | Optional next actions, retry hints, or source-reopen guidance. |
| `meta` | Version, surface class, owner, or timing metadata. |
| `cannot_claim` | Explicit claim boundaries. These are not ordinary errors. |

The envelope does not make a claim true. Source truth still belongs to clean
source, source refs, governed registries, lifecycle/freshness checks, and
domain-specific gates.

## Failure Families

Use these family names for public errors, warning codes, and diagnostic status
mapping:

- `source_missing`
- `source_stale`
- `privacy_blocked`
- `permission_blocked`
- `provider_unavailable`
- `foreground_budget`
- `partial_failure`
- `degraded_fallback`
- `schema_invalid`
- `writer_busy`
- `unsupported_mode`
- `no_evidence`

Local owners may keep more precise codes, for example MCP
`registry_writer_busy` or CLI `missing_api_key`, but public diagnostics should
map them to one of these families when crossing package boundaries.

## Existing Owners Stay Canonical

This contract deliberately reuses existing local owners:

- CLI error classes remain in `aippocampus_runtime.cli.errors`.
- MCP read-mostly/control-plane errors remain in `aippocampus_runtime.mcp.server`.
- Ambient packet authority and action grammar remain in
  `aippocampus_runtime.recall.authority` and
  `skills/aippocampus/references/ambient-hooks.md`.
- Maintenance degraded-report behavior remains in
  `skills/aippocampus/references/maintenance-and-operations.md`.
- Sync manifests and import/export schemas remain with their package owners.

Do not flatten `direction_only`, `reopenable_route`, `bounded_evidence`, or
`source_open` into ordinary `ok=true` facts. They are action guidance and source
authority states. A public envelope may carry them, but it must not reinterpret
them.

## Configuration Registry

`aippocampus_runtime.config.registry` is the code-level registry for
`AIPPOCAMPUS_*` configuration names used by the packaged runtime and documented
public maintenance surfaces. Each entry declares:

- `name`
- `owner`
- `stability`
- `surface`
- `default`
- `sensitive`
- optional notes

Stability buckets are `stable_public`, `provider_specific`, `experimental`,
`test_only`, `legacy_fallback`, and `internal_maintainer`.

`aippocampus doctor config --json` emits a no-write report:

```powershell
aippocampus doctor config --json
```

The report only exposes whether a variable is configured, its owner/stability,
and whether the value was redacted. It must not print secret values, local
absolute paths, provider base URLs, account IDs, bucket names, raw prompts,
source snippets, registry row paths, rollout paths, or hook/debug payloads.

The public docs matrix in `docs/guides/public-api.md#environment-variables`
remains the human-facing explanation. The runtime registry is the deterministic
drift guard for code.

## Verification

Deterministic coverage lives in
`tests/aippocampus/test_runtime_contracts_and_config_registry.py`:

- public envelope fields and failure families stay stable;
- unknown statuses fail closed;
- every runtime `AIPPOCAMPUS_*` name is registered;
- `.env.example` and the public API env matrix cannot mention an
  unregistered `AIPPOCAMPUS_*` name;
- config reports redact values, paths, provider endpoints, and unknown env
  values;
- `doctor config --json` is no-write and value-redacted.
