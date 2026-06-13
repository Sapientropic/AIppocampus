# Public Core Boundary

This document is the canonical public-core boundary for AIppocampus licensing,
adapter architecture, and minimal data-contract scope. It is not legal advice.
If a release needs formal relicensing diligence, use the checklist below before
publishing release notes or package metadata.

For supported CLI, MCP, JSON, environment-variable, and Python import stability,
see [public-api.md](public-api.md).
For the product profile split between personal defaults, optional diagnostics,
and governed/enterprise behavior, see
[product-profiles.md](../architecture/host/product-profiles.md).

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

## Product Profile Boundary

This licensing boundary is separate from product profile friction. The public
local core can still include high-risk gates or governance helpers, but those
surfaces should be labeled `enterprise_governed` or explicit opt-in when they
would make ordinary personal recall feel like a compliance console.

The public core supports multiple product profiles, but the default personal
experience must stay low-friction. This is the canonical #680 boundary for
features that could otherwise turn ordinary recall into enterprise ceremony.

### Core Complexity Budget

A feature can enter the personal/core default only when it clearly improves at
least one of these outcomes:

- Makes first use simpler.
- Reduces the agent's need to manually grep or ask the user to restate context.
- Reduces false or unsupported source claims.
- Removes an existing concept from the ordinary user path.

If a mechanism adds a new concept ordinary users must understand and does not
clearly improve one of those outcomes, keep it outside Core. Put it in a
power-user surface, an enterprise/high-risk profile, or the research garden.
This budget applies to new scoring layers, attribution layers, governance
layers, dashboards, glyphs, workers, and meta-contracts as much as to runtime
code.

### Personal/Core Default

The personal default is the ordinary local AIppocampus path: clean-source
registration, source-backed search, progressive recall, import/export, and
privacy-safe diagnostics. It should help a user reach a first source-backed
recall before asking them to understand governance machinery.

Purpose-bound memory access tokens are not a personal-default prerequisite.
Personal users should be able to use pause, forget, do-not-use-here, export,
and why-not diagnostics without approving every memory access. The default may
still block unsafe routes, require source reopen for
strong claims, and avoid over-personalization; low friction does not weaken
source truth or privacy.

### Power-User Optional

Power-user surfaces add control without becoming mandatory setup. Examples
include optional review inboxes, route/entity review, advanced why-recall /
why-not-recall inspection, configurable partitions, and explicit sensitive-area
checks. These features are available when a user wants them, but they must not
make the default install, first recall, or ordinary local search look broken.

why-recall and why-not-recall remain diagnostics. They can explain route
eligibility, silence, degradation, or suppression with public-safe reason
codes, but they are not source evidence and not a control plane by themselves.

### Enterprise/High-Risk Governed

Enterprise and high-risk profiles cover legal, medical, therapy-like, regulated,
team, sensitive multimodal, or compliance-heavy deployments. Purpose-bound
access, capability contracts, audit logs, human review queues, retention
governance, policy reports, and high-risk answer gates belong here unless a
future design explicitly promotes a smaller piece into the personal default.

This profile boundary is not an enterprise compliance claim. It only says where
heavier controls belong and why they should not be baseline ceremony for a
personal external-hippocampus workflow.

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
When adding optional metadata, follow
[`schema-field-profiles.md`](../architecture/runtime/schema-field-profiles.md): minimal
identity, retrieval runtime, governance, diagnostic, and high-risk projections
must remain separate instead of widening every base record.

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
  "metadata": {
    "core": {"schema_version": "aippocampus.metadata.core.v1"},
    "provider": {
      "namespace": "codex",
      "schema_version": "codex.source_event_metadata.v1"
    },
    "extensions": {}
  }
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

### Metadata Namespace And Extension Rules

Public schemas may carry a `metadata` object so adapters can preserve useful
host context without corrupting the core event meaning. The namespace contract is
small on purpose:

- `metadata.core` is reserved for AIppocampus-owned public metadata. It may add
  optional fields, but it must not change the semantics of top-level fields.
- `metadata.provider` belongs to the adapter that produced the event. It should
  include a stable `namespace` such as `codex`, `claude_code`, or
  `generic_jsonl`, plus a provider-local `schema_version` when the payload is
  more than a flat hint.
- `metadata.extensions` is for third-party or downstream adapter extensions.
  Keys should be stable extension ids such as a package name, URI, or reverse
  DNS-style namespace. Extension payloads should include their own
  `schema_version` when consumers might branch on the contents.

Metadata must not override or reinterpret top-level public fields. If
`metadata.provider.role` conflicts with top-level `role`, or a model-generated
metadata label conflicts with the source text, the top-level field and source
refs win. Model-generated labels remain navigation, not source truth.

Public metadata must not contain credentials, tokens, cookies, raw auth headers,
secret-bearing environment values, or host-private absolute paths. Raw host ids
that are not safe to share should be redacted, hashed, bundle-relative, or left
out. Private export mode may include local locators only when the export is
explicitly marked private and intended for the original owner or trusted local
operator.

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

### Runtime Clean-Source Manifest

Runtime clean-source directories also contain a private operator
`manifest.json`. This manifest is not the portable import manifest, but its
provider-neutral fields are stable enough for local automation:

- `source_id`, `source_provider`, and `source_thread_key` identify the provider
  source without treating local paths as identity.
- `source_transcript`, `source_transcript_size`, `source_transcript_mtime`, and
  `source_transcript_sha256` describe the private provider transcript used to
  build the clean-source artifact.
- `source_artifact` is the structured provider-neutral form of the same
  transcript locator and integrity metadata. Its `path` is private and should be
  redacted or bundle-relativized outside trusted local operator flows.
- `source_rollout`, `source_rollout_size`, `source_rollout_mtime`, and
  `source_rollout_sha256` are legacy compatibility aliases for the
  `source_transcript*` fields. New integrations should read
  `source_artifact` or `source_transcript*`; old consumers may keep reading the
  rollout-named aliases during the compatibility window.

The generated runtime files map back to the public schema as follows:

- `messages.jsonl` rows are provider-normalized visible-message chunks. They
  carry `source_id`, `source_ref`, `message_id`, raw line spans, text hashes,
  `kind`, and `phase` as metadata for audit and navigation.
- `turns.jsonl` rows are a join/navigation sidecar over message ids and turn
  boundaries. They are useful for reconstruction but do not replace canonical
  source refs.
- `events.jsonl` rows are structured behavior provenance when a provider can
  safely extract tool/test events without storing raw payload text.

`kind` and `phase` are provider-normalized metadata fields, not Codex-only truth
fields and not claims about the user's intent. Source text and source refs remain
the audit authority.

The installable reference `skills/aippocampus/references/retrieval-and-storage.md`
owns the critical-operation integrity contract over `events.jsonl`. Public
consumers should treat its diagnostic as a coverage/gap report, not as license
to reopen raw payloads or infer operation facts from assistant narration.
`events.jsonl` breadcrumbs such as command family, target class, failure family,
path category, generated-file flag, and safe path fingerprint are bounded
metadata only; they are not raw process transcript fields.

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

### Knowledge Source Manifest

Knowledge-source manifests are the governed source-eligibility layer for
future high-impact knowledge features. They are not generic RAG chunk metadata:
they decide whether a source is eligible to support promoted claims, while clean
source and source refs remain the audit authority.

```json
{
  "schema_version": "aippocampus.knowledge_source_manifest.v1",
  "source_id": "ksrc-official-guideline-like",
  "source_type": "official_guideline_like",
  "publisher": "Synthetic Public Safety Board",
  "authority_level": "official_primary",
  "jurisdiction_scope": ["synthetic-jurisdiction"],
  "domain_scope": ["synthetic-safety"],
  "effective_date": "2026-01-01",
  "last_verified_at": "2026-06-01T00:00:00Z",
  "license": "CC0-1.0-synthetic",
  "access_policy": "public_fixture",
  "privacy_class": "public",
  "content_hash_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "ingest_status": "active",
  "taint_labels": [],
  "provenance_chain": [
    {"kind": "synthetic_fixture", "ref": "fixture:official-guideline-like"}
  ],
  "superseded_by": null,
  "retracted_status": "not_retracted"
}
```

Required semantics:

- `schema_version`, `source_id`, `source_type`, `publisher`,
  `authority_level`, `ingest_status`, and `privacy_class` are required for a
  valid manifest record.
- High-stakes activation eligibility additionally requires integrity,
  provenance, scope, freshness, licensing/access, and jurisdiction metadata:
  `content_hash_sha256`, `provenance_chain`, `domain_scope`,
  `jurisdiction_scope`, `effective_date`, `last_verified_at`, `license`, and
  `access_policy`.
- `ingest_status` separates storage from truth. `quarantined` and `candidate`
  material may be kept for audit or navigation but must not support activated
  claims. `retired`, `retracted`, and `superseded` sources remain auditable but
  inactive.
- Model summaries, extracted triples, dream findings, low-quality web pages,
  raw uploads, and unreviewed notes are candidate/navigation material unless a
  later reviewed source manifest promotes the underlying source span.
- Conversation turns can be active source artifacts for conversation-memory
  claims, but they do not become legal, medical, financial, or general-world
  authority just because the user said something.
- `taint_labels` such as `generated`, `untrusted`, `copied_web`, or
  `missing_provenance` block activation until the material is reviewed through
  a stronger source manifest.

### Knowledge Claim Record

Knowledge-claim records are assertion-level promotion records. A document,
chunk, summary, or model output does not become a promoted fact wholesale; each
activated claim must point back to a reviewed source span.

```json
{
  "schema_version": "aippocampus.knowledge_claim.v1",
  "claim_id": "claim-official-span",
  "source_id": "ksrc-official-guideline-like",
  "source_anchor": {
    "section_anchor": "sec-guideline-duty",
    "span_id": "sec-guideline-duty:p1",
    "char_start": 0,
    "char_end": 120
  },
  "claim_text": "Synthetic operators must verify current source before high-impact advice.",
  "claim_scope": ["synthetic-safety"],
  "authority_level": "official_primary",
  "jurisdiction_scope": ["synthetic-jurisdiction"],
  "effective_date_scope": {"valid_from": "2026-01-01", "valid_to": null},
  "review_status": "reviewed",
  "reviewed_by": "synthetic-reviewer:source-governance",
  "review_signed_at": "2026-06-01T00:00:00Z",
  "extraction_provenance": "human_reviewed_span",
  "promotion_status": "activated",
  "confidence": {"level": "high", "basis": "reviewed official fixture span"},
  "conflict_status": "none",
  "conflict_set_id": null,
  "superseded_by": null,
  "uncertainty_notes": "Synthetic fixture claim only."
}
```

Required semantics:

- `schema_version`, `claim_id`, `source_id`, `source_anchor`, `claim_text`,
  `claim_scope`, `authority_level`, `jurisdiction_scope`,
  `effective_date_scope`, `review_status`, `extraction_provenance`, and
  `promotion_status` are required.
- Activated high-stakes claims require an assertion-level span
  (`section_anchor`, `span_id`, `char_start`, and `char_end`), not a
  whole-document blessing.
- Activated high-stakes claims require `review_status: "reviewed"`,
  `reviewed_by`, `review_signed_at`, non-low `confidence`, and a cleared
  `conflict_status` such as `none` or `resolved`.
- Claim domain and jurisdiction scopes must stay within the source manifest's
  scopes. Conversation-memory evidence cannot be promoted into unrelated
  professional advice domains.
- Generated summaries or triples may help navigation, but claims derived only
  from generated artifacts must remain candidate, uncertain, or blocked until a
  reviewed source span supports them.
- Superseded, conflicted, uncertain, or unreviewed claims remain auditable but
  must not be activated.

### Knowledge Update Event

Knowledge update events are append-only lifecycle overlays for governed source
changes. They are the public record shape for added, changed, superseded,
retracted, and rollback source versions. The detailed state machine, rollback
boundary, and high-stakes review-gate behavior are owned by
[knowledge-source-lifecycle.md](../architecture/source/knowledge-source-lifecycle.md).

Required semantics:

- `schema_version` is `aippocampus.knowledge_update_event.v1`.
- `event_id`, `diff_type`, `impact_scope`, `affected_claims`,
  `requires_review`, and `created_at` are required.
- `old_source_id`, `new_source_id`, and `rollback_source_id` must resolve when
  the selected `diff_type` needs them.
- `affected_claims` is always present and may be empty for source additions.
- In high-stakes mode, candidate updates may be written as audit events, but
  activation requires explicit review/signature metadata and an
  activation-eligible new source.
- Supersession, retraction, and rollback are lifecycle overlays. They never
  delete source history or silently rewrite promoted claims.

### High-Risk Answer Gate Policy

High-risk answer-time use of governed knowledge claims is owned by
[high-risk-answer-gates.md](../architecture/host/high-risk-answer-gates.md). The
policy is a deterministic local gate over already selected claims and evidence:
it requires source reopen, applicability context, lifecycle eligibility, visible
conflict handling, and privacy-safe cannot-claim boundaries before a claim can
support a high-impact answer. It is not a public answer-generation API and it
must not export raw source text or claim text in its report.

### Typed Capability Manifest Boundary

Typed agent-skill capability manifests are currently an architecture prototype,
not part of the minimal public schema contract. Their canonical design boundary
lives in
[agent-skill-capability-contracts.md](../architecture/host/agent-skill-capability-contracts.md).
They may describe execution permissions, privacy partitions, tool profiles, and
evaluation protocols for a skill path, but source manifests, claim records,
source refs, and answer gates remain the public-core proof surfaces.

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
