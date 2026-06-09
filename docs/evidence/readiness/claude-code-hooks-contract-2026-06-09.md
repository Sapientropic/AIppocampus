# Claude Code Hooks Contract Evidence - 2026-06-09

Role: dated readiness evidence for #1020.

This report records the first scoped AIppocampus Claude Code hook contract
slice. It is based on the official Claude Code hooks reference and guide:

- <https://code.claude.com/docs/en/hooks>
- <https://code.claude.com/docs/en/hooks-guide>

## Positive Evidence

- `aippocampus hooks claude-code status --json` reports a Claude Code hook
  contract surface with `not_installed`, `installable`, `installed`, `firing`,
  `blocked`, `unsupported_version`, and `unsupported_event` status vocabulary.
- `aippocampus hooks claude-code dry-run --json` reports the scoped
  `UserPromptSubmit` and `Stop` handler shape without writing Claude Code
  settings.
- `aippocampus hooks claude-code smoke --json` feeds synthetic Claude-shaped
  `UserPromptSubmit` and `Stop` JSON into the handler and verifies exit code 0
  without printing raw prompt text, session ids, transcript paths, cwd values,
  or synthetic tool payload text.
- The handler defaults to fail-open silence. It emits bounded
  `additionalContext` only under the explicit diagnostic-context mode used by
  the synthetic smoke.

## Event Status

| Event | Status | Evidence | Boundary |
| --- | --- | --- | --- |
| `UserPromptSubmit` | Scoped handler available | Synthetic Claude-shaped smoke passes; dry-run reports handler shape. | Real-host firing needs an observed event log or local dogfood report. |
| `Stop` | Scoped handler available | Synthetic Claude-shaped smoke passes; handler exits 0 and does not block completion. | Real maintenance usefulness is not claimed. |
| `PostToolUse` / `PostToolBatch` | `unsupported_event` | Official contract intaken; no AIppocampus payload sanitizer ships yet. | Do not capture or store raw tool payloads. |
| `PreCompact` / `PostCompact` | `unsupported_event` | Official contract intaken; summary/source-truth handling is not implemented. | Do not treat compact summaries as clean-source truth. |

## Cannot Claim

This evidence does not claim:

- Claude Code settings were mutated or a configuration-mutating installer
  exists.
- Hooks fired in a real Claude Code host session.
- `PostToolUse`, `PostToolBatch`, `PreCompact`, or `PostCompact` are supported
  beyond event-level status/blocker reporting.
- Claude Code hooks prove MCP health, transcript onboarding, cross-device sync,
  hosted/cloud continuity, or broad private-history quality.
