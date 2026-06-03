# Path Identity Contract

AIppocampus compares local workspaces and registry artifacts across hosts,
symlinks, temporary directories, sync targets, and agent surfaces. Path handling
therefore has three separate meanings:

- identity key: the stable comparison surface for registry joins, cache keys,
  thread fallback ids, and same-workspace checks.
- display path: the spelling the caller supplied or the host returned, used
  only when an operator needs to inspect a local diagnostic.
- privacy-safe public path: a redacted projection for docs, PR notes, reports,
  evidence ledgers, and model-visible payloads.

Do not collapse these meanings. A fix for one layer can break another.

## Identity Key

Use `aippocampus_runtime.core.canonical_path`,
`path_identity_key`, `workspace_identity`, `workspace_identity_key`, or
`workspace_fingerprint` for identity-bearing comparisons. These helpers own the
recurring #404 / #589 regression family:

- macOS `/var` and `/private/var` spellings;
- Windows drive-letter case and UNC server/share case;
- symlink and bind mount style workspace aliases;
- registry project keys, workspace fallback thread keys, and ambient cache
  fingerprints.

The identity helpers may call `Path.resolve()` because their job is to make two
spellings of the same local path compare as one identity. Plain project labels
are intentionally not resolved against the current process directory; resolving
`"Project Alpha"` would make portable cache keys drift by machine.

## Display Path

Display paths are for trusted local operators. Keep caller spelling when a
diagnostic is explaining exactly what the user configured, such as a hook
command, explicit sync directory, or CLI argument. Do not blindly replace every
display path with a resolved path; spelling can be the evidence needed to debug
UNC, symlink, bind mount, or macOS temporary-directory behavior.

## Privacy-Safe Public Path

Public reports must not include absolute local paths. Use the existing
privacy-safe projections, such as `aippocampus_runtime.privacy.redact_private_paths`,
when a payload can leave the local machine or be copied into docs, public issue
comments, PR bodies, benchmark evidence, or model-visible summaries.

Identity hashes are allowed in public-safe payloads only when they cannot be
reversed into a local path and when the surrounding payload does not include raw
path text.

## Implementation Notes

Registry, sync, MCP, hook diagnostics, and recall/cache code may still store
real local paths in private registry artifacts. When they compare paths or build
long-lived join ids, they should go through the central identity helpers instead
of ad hoc `str(path).casefold()` normalization.

When adding coverage:

- include at least one Windows-style edge, such as UNC or drive spelling;
- include a symlink or bind mount style alias where the platform permits it;
- assert that public/cache payloads do not serialize raw workspace paths;
- link new platform regressions back to #404 and #589.
