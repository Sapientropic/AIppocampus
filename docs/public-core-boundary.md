# Public Core Boundary

This document is the canonical public-core boundary for AIppocampus licensing,
adapter architecture, and minimal data-contract scope. It is not legal advice.
If a release needs formal relicensing diligence, use the checklist below before
publishing release notes or package metadata.

## Licensing Decision

The public AIppocampus repository is Apache-2.0 licensed.

The reason is adoption: the core continuity substrate should be easy for agent
runtimes, plugin authors, internal platform teams, and research projects to
embed, implement, and interoperate with. The commercial product surface should
live in managed operations and higher-level services, not in a restrictive core
protocol that blocks interoperability.

This is not a "dual licensed" repository. Code, docs, plugin metadata, schemas,
and local tools shipped in this public repository are Apache-2.0 unless a file
or bundled third-party asset says otherwise.

## Apache-2.0 Public Core

The public core includes:

- Canonical source event, clean-source chunk, source-reference, and import
  manifest contracts documented in this repository.
- The installable `skills/aippocampus/` package.
- Local CLI tools for build, import, export, validate, search, health, sync
  status, and local maintenance.
- Local clean-source registry and index formats.
- MCP tools for local read/write control-plane access.
- Codex plugin packaging and host-specific install metadata.
- Local-folder and object-storage sync client code that is present in this
  repository.
- Minimal runtime adapters that map external agent logs into canonical source
  events or import manifests.
- Public sample bundles, tests, smoke tools, and benchmark harnesses that are
  safe to publish.

## Commercial Or Separate-License Surface

The following are reserved for commercial, source-available, hosted, or
otherwise separately licensed products unless they are later published in this
repository under an explicit open-source license:

- Hosted sync service operations.
- Managed backup, retention, audit, compliance, and recovery services.
- Team or enterprise admin, governance, policy, and UI surfaces.
- Proprietary hosted graph, semantic, cognitive-map, or consolidation services.
- Enterprise connectors, deployment automation, and support packaging.
- Product-specific cloud infrastructure, SLOs, billing, and managed-model
  orchestration.

Local scripts that already ship in this repository are part of the Apache-2.0
public core. A future hosted implementation may reuse the same contracts while
remaining a separate product.

## Private User Data Boundary

The repository license covers project code, documentation, schemas, tests, and
bundled public assets. It does not license a user's private memory data.

Private user data includes raw rollouts, clean-source exports, registry rows,
sync bundles, vault exports, generated indexes, thread anchors, and any local
artifacts derived from a person's conversations unless that person explicitly
publishes them.

Do not describe user memory data as project code. Do not imply that Apache-2.0
permission to use AIppocampus grants permission to redistribute someone else's
conversation archive.

## Third-Party Assets

Bundled third-party assets keep their upstream notices and licenses. Before a
release, check at least:

- `skills/aippocampus/assets/pixi-7.2.4.min.js`
- `skills/aippocampus/assets/d3-7.9.0.min.js`
- public benchmark corpora and manifests under `benchmark_corpus/`

The `NOTICE` file is intentionally short. Add attribution there only when a
bundled dependency or distribution policy requires downstream NOTICE retention.

## Adapter Architecture

MCP, plugin packaging, and adapters are separate responsibilities:

- MCP is the runtime-neutral tool/control plane. It exposes search, list,
  latest reply, health, sync status, registration, import preview, and source
  retrieval tools to compatible clients.
- Plugin packaging is host-specific installation and metadata. Codex plugin
  packaging may include MCP config, skill files, UI metadata, and optional hook
  installers, but it must not become the canonical data contract.
- Adapters are data-normalization layers. They map external agent logs or host
  exports into canonical source events, clean-source chunks, source refs, and
  import manifests.

New integrations should target the adapter/schema contract first, then expose
the result through MCP or a host plugin. That keeps Claude, Codex, Cursor,
VS Code, and future runtimes interoperable instead of producing one-off
importers.

## Minimal Public Schema Contract

These shapes are the stable public contract. Field names may grow, but existing
meaning should not be silently reused for a different concept.

### Canonical Source Event

```json
{
  "schema_version": "aippocampus.source_event.v1",
  "source_id": "thread-or-export-stable-id",
  "event_id": "stable-event-id-within-source",
  "runtime": "codex",
  "thread_id": "optional-host-thread-id",
  "turn_id": "optional-turn-id",
  "role": "user",
  "created_at": "2026-05-29T00:00:00Z",
  "text": "visible conversation text",
  "metadata": {}
}
```

Required semantics:

- `schema_version`, `source_id`, `event_id`, `runtime`, `role`, and `text`
  are required.
- `event_id` must be stable for the same imported event.
- `text` is the visible source text. It is private unless the exporting user
  intentionally publishes it.
- `metadata` must not contain credentials or host-private absolute paths unless
  an explicit private export mode says so.

### Clean-Source Chunk

```json
{
  "schema_version": "aippocampus.clean_chunk.v1",
  "chunk_id": "stable-clean-chunk-id",
  "source_id": "thread-or-export-stable-id",
  "role": "assistant",
  "text": "cleaned visible text",
  "source_refs": [
    {
      "source_id": "thread-or-export-stable-id",
      "event_id": "stable-event-id-within-source",
      "line_start": 10,
      "line_end": 18,
      "text_sha256": "hex-or-null"
    }
  ],
  "labels": []
}
```

Required semantics:

- `chunk_id`, `source_id`, `role`, `text`, and `source_refs` are required.
- A chunk may combine or split source events, but it must retain source refs
  precise enough for audit and repair.
- `labels` are navigation hints, not replacement truth.

### Source Ref

```json
{
  "source_id": "thread-or-export-stable-id",
  "event_id": "stable-event-id-within-source",
  "line_start": 10,
  "line_end": 18,
  "message_id": "optional-host-message-id",
  "turn_id": "optional-turn-id",
  "text_sha256": "hex-or-null"
}
```

Required semantics:

- `source_id` and at least one of `event_id`, `message_id`, or a stable line
  span are required.
- `text_sha256` is for integrity checks. It is not a global public identity for
  private memory.

### Import Manifest

```json
{
  "schema_version": "aippocampus.import_manifest.v1",
  "manifest_id": "stable-import-id",
  "created_at": "2026-05-29T00:00:00Z",
  "producer": "adapter-name-and-version",
  "source_runtime": "codex",
  "events": "clean-source/events.jsonl",
  "chunks": "clean-source/chunks.jsonl",
  "privacy": {
    "contains_private_text": true,
    "raw_rollout_included": false
  }
}
```

Required semantics:

- `schema_version`, `manifest_id`, `producer`, `source_runtime`, `events`, and
  `privacy.contains_private_text` are required.
- Manifest paths are relative to the import bundle root.
- `raw_rollout_included` must be explicit because raw provenance has a higher
  privacy risk than clean source.

## Relicensing Checklist

Before tagging the first Apache-2.0 release or publishing distribution
metadata:

- Confirm the copyright owner is authorized to relicense the current public
  repository contents.
- Review contributor history. If a non-owner contribution is material and was
  not already covered by an inbound Apache-compatible contribution policy,
  decide whether consent is required.
- Preserve old release history: earlier AGPL releases remain available under
  their original terms unless separately relicensed.
- Keep `LICENSE`, `NOTICE`, `README.md`, `COMMERCIAL-LICENSE.md`,
  `pyproject.toml`, plugin metadata, and provenance catalogs aligned.
- Verify bundled third-party assets and public corpora can be redistributed
  under their own terms.
- Run the public-readiness privacy scan before release so private rollouts,
  registry exports, local paths, credentials, and generated memory artifacts do
  not enter the public package.
