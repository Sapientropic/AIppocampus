# Clean-Source Redaction Profiles

Role: current contract.

Issue: #591. Related privacy surfaces: #352 and #357.

Clean source is the canonical evidence source for AIppocampus. Its default
`raw-private` profile keeps visible conversation text source-faithful so source
refs, line spans, message ids, and content hashes can reopen what actually
happened. Redaction profiles are optional projections; they are privacy
surfaces, not replacement truth.
Keep source refs as the durable reopen bridge; do not treat redacted snippets as
standalone evidence.

## Profiles

| Profile | Purpose | Source-fidelity boundary |
| --- | --- | --- |
| `raw-private` | Full local clean source for authorized local recall. | Canonical evidence source. It may contain private visible text and must stay local/private unless intentionally exported. |
| `redacted-local` | Optional at-rest local projection for machines or folders where full text should not sit in every copy. | Projection only. It preserves join keys so an authorized local user can reopen private source. |
| `public-export` | Strict projection for demos, evidence reports, public bundles, and community sharing. | Public candidate only. It must not include raw rollout, raw private clean-source text, private-key material, API keys, emails, connection strings, or local paths. |
| `external-model` | Existing outbound prompt/payload redaction for model calls. | Separate transport boundary from at-rest storage. It may keep safe surrounding context for recall, but it is not an at-rest clean-source profile. |

## Detection Boundary

The shared runtime policy is `aippocampus_runtime.safety.project_clean_source_text`.
It reuses the external-model redaction contract from #352 for private-key
blocks, API keys, bearer tokens, passwords/secrets, credential URLs, and
project-safe path anchors. It also applies the benchmark/privacy sensitivity
classes from #357 for emails and likely database connection strings.

This is a safeguard, not a complete PII detector. It must never be described as
legal privacy certification or full secret discovery.

## Source Reopen Contract

Projected rows keep deterministic mapping fields such as `source_id`,
`source_ref`, `turn_id`, `message_id`, raw line spans, and original
`content_sha256`. They may add `redaction_profile`, `redaction_policy`, and
`redacted_text_sha256`.

Those fields let an authorized local agent reopen the private source when it is
allowed to do so. They do not make the redacted text itself the canonical
source, and they must not replace raw-private hashes used for exact evidence.

## Sync And Export

Clean-source sync and registry artifacts remain private unless an explicit
profile says otherwise. `public-export` bundle/index paths must use projected
text and exclude raw rollout. `--no-raw` and `public-export` serve different
purposes: `--no-raw` prevents raw transcript inclusion, while the redaction
profile controls the text stored in generated index/report artifacts.
Private interpretation sidecars such as `source-texture.jsonl` are omitted from
`public-export` projections by default; future public projections need their
own allowlist and must preserve source-ref reopen boundaries.

Do not fix a public export leak by destructively rewriting canonical
`messages.jsonl`. Generate a projection instead, then keep public artifacts
bounded to that projection.

## Non-Goals

- Do not make lossy redaction the default clean-source storage mode.
- Do not send private clean source to external NER services.
- Do not claim full PII detection.
- Do not weaken source-backed recall or exact source reopen to make export
  easier.
