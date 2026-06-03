# Multimodal Source Manifests

Status: internal source contract and public-safe fixture for GitHub #541 and
the #528 multimodal source-backed recall track.

This contract defines how AIppocampus names multimodal sources before any
retrieval, provider routing, source reopen, or answer gate tries to use them.
It is not a full-device indexer, photo manager, captioning system, provider
adapter, or answer-generation API.

## Runtime Owner

The deterministic validator lives at
`skills/aippocampus/scripts/aippocampus_runtime/source/multimodal_manifest.py`.
The public-safe fixture lives at
`tests/fixtures/multimodal_sources/public_safe_manifest.json`, with coverage in
`tests/aippocampus/test_multimodal_source_manifest.py`.

The validator checks manifest shape, source authority, media-origin policy, and
derived-artifact provenance. It does not read raw media, write registry rows,
call models, build embeddings, or decide whether an answer is correct.

## Source Record

A multimodal source record represents original source material. Each record
must carry:

- stable identity: `schema_version`, `source_id`, `source_type`, `media_type`;
- origin and privacy: `origin_policy`, `privacy_class`, `source_owner`,
  `access_policy`, `license`;
- audit metadata: `captured_at`, `timezone`, optional `location_hint`,
  `content_hash_sha256`, `source_anchor`, and `provenance_chain`;
- task policy: `task_scoped_access` with current-task access, configured-scope
  requirements, hidden durable-write policy, cross-domain reuse policy, and
  audit-event requirements.

The current source types cover images, video frames and segments, email, chat,
receipts, invoices, calendar events, and document pages. A source anchor is the
reopen point for later visual, document, or event claims. The hash and anchor
belong to the original source, not to a generated caption or tag.

## Media-Origin Policy

AIppocampus must keep these three situations separate:

| Origin policy | Meaning | Default boundary |
| --- | --- | --- |
| `user_provided_media` | The user selected or uploaded the source for the current task. | May be used in the current task; does not grant hidden durable writes or cross-domain reuse. |
| `connected_library_media` | The source comes from an explicitly configured connected library or scoped connector. | Requires a configured scope before access; no hidden durable writes or cross-domain reuse. |
| `background_filesystem_media` | The source exists in an unselected local/background surface. | Denied by default until a future explicit scope or user action selects it. |

Task-scoped consent is intentionally narrow. Using selected media to answer the
current request does not allow background scanning, hidden provider routes,
silent memory creation, cross-domain reuse, or durable profile updates.

## Derived Artifacts

Derived artifacts include OCR, ASR, captions, object/entity tags, visual
embeddings, thumbnails, perceptual hashes, and schema rows. They can route or
accelerate recall, but they are not source truth.

Each derived artifact must carry:

- `artifact_id`, `artifact_type`, and `schema_version`;
- `parent_source_id` and `parent_anchor_id`;
- its own `source_anchor` for reopening the artifact;
- `provider_route`, `model_id`, `confidence`, and `created_at`;
- `authority: "navigation_only"`;
- `output_artifacts` and `provenance_chain`.

The validator blocks a derived artifact when its parent source is missing, when
its parent anchor does not match the original source anchor, or when it tries to
claim authority beyond `navigation_only`.

## Truth Boundary

Original source anchors remain the audit boundary. Captions, OCR, tags,
schema rows, embeddings, and thumbnails are navigation layers unless a future
contract explicitly promotes a frozen public fixture label. For product use,
visual or document claims should reopen the original source or reach a later
answer gate that can explain why source reopen is unavailable.

This keeps #528 from accidentally treating generated descriptions as personal
memory. The source manifest can say where to look, what policy allows looking,
and which derived artifacts may help. It cannot say that a generated caption is
true just because it exists.

## Non-Goals

- No whole-device indexing.
- No personal photo manager.
- No private raw media in the public repository.
- No provider capability routing. That belongs to a separate contract.
- No source-reopen answer gate. That belongs to a later #528 slice.
- No claim that public-safe synthetic fixtures prove private-history lift or
  live vision-model quality.

Provider-route capability gating is tracked separately in
`docs/architecture/multimodal-provider-routing.md`. Source manifests describe
the source and origin policy; provider routing decides whether a declared route
may process that source or a navigation-only derived artifact.

## Verification

The public-safe fixture covers:

- one user-provided raw image source;
- one user-provided chat source;
- one connected receipt/document-like source;
- one background calendar/event source;
- caption, entity-tag, OCR, and schema-row derived artifacts.

The deterministic tests prove that:

- the fixture validates and exposes the three media-origin policies;
- derived artifacts are `navigation_only` and resolve to parent source anchors;
- missing parent sources or parent anchors block validation;
- background filesystem media cannot be treated as current-task selected media;
- original sources require both content hashes and reopenable anchors.
