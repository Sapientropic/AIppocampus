# Privacy And Security Checklist

Use this checklist before treating AIppocampus as public-ready or sharing a
bundle, demo, release, or plugin package.

## Source Boundaries

- Clean source may contain private visible conversation text.
- Raw rollout is audit provenance, not the daily recall surface.
- Registry rows, vault exports, thread anchors, and sync bundles are private
  unless intentionally sanitized.
- Local absolute paths are locators, not identity.

## Before Publishing

- Run docs health and the full test suite.
- Scan for real local paths, API keys, bearer headers, cookies, tokens, and
  credential URLs.
- Inspect scan hits manually. `FAKE_TEST_` fixtures are allowed; real private
  values are not.
- Confirm `.aippocampus/`, registry exports, `thread-anchors.md`, logs, and
  archives remain gitignored.
- Confirm public examples do not include `rollout.jsonl`.

## Hooks

- Prompt hooks are opt-in because they run on every prompt.
- Lifecycle hooks may refresh generated artifacts, but they must not delete,
  archive, or run expensive model work synchronously.
- Hook installers must preserve unrelated hooks and support uninstall.

## External Models

- DeepSeek-compatible routes are optional.
- Non-DeepSeek OpenAI-compatible or local/offline routes must be explicitly
  configured and selected; they are privacy/fallback routes, not default
  quality-parity claims.
- Provider-specific fields such as DeepSeek `user_id`, `thinking`, and
  prefix-cache metrics must be gated by route capabilities.
- Prompt-time external-model calls must pass through shared redaction.
- Mostly-secret prompts should hard-skip external calls.
- Missing API keys should return structured errors, not tracebacks.
- Semantic sidecars from external-model jobs are navigation hints only; they
  must target existing clean-source message ids with source refs and must not
  rewrite source text or enter the default promotion-review path.

## Sync And Plugin Distribution

- Raw rollout sync is excluded by default and must be explicitly requested.
- Once encrypted sync ships, any raw rollout sync must also require encryption,
  including local-folder sync.
- Encrypted sync does not automatically remove older plaintext sync copies.
  Use a new sync directory/object prefix or an explicit migration cleanup.
- Public recipients are less sensitive than private identities, but real
  recipient ids and vault ids are stable correlation handles; avoid posting them
  in public issues unless intentionally sanitized.
- Never commit or publish `AGE-SECRET-KEY...` identities, SSH private keys,
  recovery kits, decrypted bundles, or plaintext temporary sync directories.
- Pull operations must preserve local conflicts instead of overwriting.
- Plugin installation must not silently enable hooks or external-model routes.
- The standalone repository remains the source of truth; plugin packaging is a
  distribution surface.
