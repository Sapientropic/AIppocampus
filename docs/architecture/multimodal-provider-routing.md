# Multimodal Provider Routing

Role: current contract.

Status: internal provider capability-routing contract and public-safe fixture
for GitHub #542 and the #528 multimodal source-backed recall track.

This contract decides whether a declared provider route may process a requested
multimodal source or derived artifact. It does not call providers, inspect raw
media, score vision quality, or turn captions/OCR/tags into source truth.

## Runtime Owner

The deterministic evaluator lives at
`skills/aippocampus/scripts/aippocampus_runtime/model/multimodal_routing.py`.
The public-safe route fixture lives at
`tests/fixtures/multimodal_sources/public_safe_provider_routes.json`, with
coverage in `tests/aippocampus/test_multimodal_provider_routing.py`.

This layer builds on the typed capability-contract vocabulary from
`docs/architecture/agent-skill-capability-contracts.md` and the source/origin
policy from `docs/architecture/multimodal-source-manifests.md`.

## Route Record

A provider route record declares:

- `route_id`, `provider`, and `model_id`;
- `input_modalities`, such as `text`, `image`, `video`, `audio`, or
  `document`;
- `output_artifacts`, such as OCR, captions, entity tags, thumbnails, schema
  rows, or derived text summaries;
- `execution_location`: `local_runtime`, `external_provider`, or
  `host_provided`;
- whether the route is an `external_provider`;
- privacy policy for raw media bytes, source text, local paths, and provider
  secret values;
- `media_origin_allowances` for `user_provided_media`,
  `connected_library_media`, and `background_filesystem_media`;
- the typed `capability_contract` family and permission profile it belongs to.

Every route in this slice has `output_authority: "navigation_only"`. That is
intentional: OCR, captions, tags, thumbnails, schema rows, and text summaries
can help routing or source reopen, but they cannot become source truth.

## Routing Rules

The evaluator blocks a route when:

- a text-only route is selected for raw image or video understanding;
- the route lacks the required modality for the requested media type;
- the route is not allowed to consume raw media or derived text for that media
  origin;
- user-provided media was not selected for the current task;
- connected-library media lacks a configured scope;
- background filesystem media is still denied by default;
- task-scoped access tries to grant hidden durable writes or cross-domain
  reuse.

Text-only routes may process derived text candidates when the case is explicitly
`derived_text` and the media-origin policy allows it. The report still marks
the output as navigation-only and includes cannot-claim boundaries such as
`derived_text_is_navigation_only`.

## Relationship To Source Manifests

Source manifests answer "what is this source and what policy governs it?"
Provider routes answer "which declared route, if any, may process this source
or derived artifact?"

The routing contract must not infer source truth. A later source-reopen answer
gate still owns visual or document claims. This prevents a convenient text-only
model route from silently converting captions, OCR, or entity tags into facts.

The answer-time source-reopen gate now lives in
`docs/architecture/multimodal-answer-gate.md`. Provider routing decides whether
a route may process a source or derived artifact; the answer gate decides
whether selected candidates have enough reopened source support to answer or
abstain.

## Non-Goals

- No live external vision provider.
- No requirement that DeepSeek-compatible text routes support vision.
- No public SDK schema.
- No background filesystem indexing.
- No claim that static provider routing proves live model quality, private
  history coverage, or end-to-end #528 product behavior.

## Verification

The deterministic fixture proves:

- text-only routes reject raw image/video extraction;
- the same text-only route can process navigation-only derived text;
- user-provided raw media can route under current-task policy;
- background filesystem media remains denied by default;
- route reports expose sanitized ids, hashes, policy decisions, and blocker
  codes without emitting raw media bytes, raw prompt text, local paths, or
  provider secret values.
