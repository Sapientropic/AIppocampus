# Security Policy

AIppocampus is a local-first memory and continuity layer. Conversation source,
registry rows, rollouts, sync bundles, vault exports, and generated indexes may
contain private user history even when the code is open source.

## Supported Versions

Until the first tagged release, security fixes target the `main` branch. After
tagging begins, this file should list the currently supported release line and
any unsupported versions.

## Reporting A Vulnerability

Please report security issues privately through GitHub's private vulnerability
reporting flow when available, or by contacting the maintainer through the
repository owner profile if private reporting is not available.

Do not open a public issue that contains:

- API keys, bearer tokens, cookies, connection strings, SSH keys, or age private
  identities.
- Raw Codex rollouts, registry exports, clean-source bundles, vault exports, or
  sync bundle contents.
- Absolute local paths that identify a private machine, user, or organization.

Include a minimal description of the affected surface, reproduction steps using
synthetic data when possible, and the version, commit, or branch where you saw
the behavior.

## Response Boundary

This is a public open-source project without an enterprise SLA. The maintainer
will triage good-faith reports as capacity allows, prioritize issues that could
expose private memory data or secret material, and publish fixes with clear
claim boundaries.

## Project-Specific Sensitive Surfaces

- Prompt and lifecycle hooks are opt-in and must not silently exfiltrate prompt
  text.
- External-model routes are optional and must pass through redaction and
  mostly-secret hard-skip boundaries.
- Raw rollout sync is explicit, and raw rollout transfer outside a trusted local
  folder must use encrypted sync.
- Encrypted sync must never copy `AGE-SECRET-KEY...` identities or recovery
  material into a sync directory, object-storage prefix, demo bundle, issue, or
  documentation example.

Use `docs/guides/privacy-security-checklist.md` and
`docs/guides/release-checklist.md` before publishing a release, demo, or plugin
package.
