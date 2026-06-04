# Standalone Binary Packaging Plan

This is the packaging plan and claim boundary for optional Python-free
AIppocampus binaries. The canonical implementation remains the source-backed
Python runtime; direct Python/script usage stays supported as the fallback.

As of 2026-05-31, Windows x64 has a PyInstaller artifact smoke, plus
post-package-refactor binary MCP re-smokes and a content-level
`tools/call:memory_health` JSON-RPC guard recorded in
`docs/evidence/readiness/public-readiness-verification.md`. Do not claim any
other platform until its artifact is built, smoke-tested, and linked from the
dated evidence ledger.

## Current Platform Decision

As of 2026-06-01, the standalone binary claim is intentionally narrow:

| Platform | Status | Public claim |
| --- | --- | --- |
| Windows x64 | Smoke-tested first platform | Maintainer-built PyInstaller path only. |
| macOS arm64 | Deferred for standalone binary support | Use Python/source or GitHub `uvx --from`. |
| macOS x64 / Intel Mac | Dropped from initial standalone binary claims | Use Python/source or GitHub `uvx --from`. |
| Linux x64 | Deferred for standalone binary support | Use Python/source or GitHub `uvx --from`. |

Evidence and next gates:

- Windows x64 evidence is recorded in
  `docs/evidence/readiness/public-readiness-verification.md`. It proves a
  maintainer-built `aippocampus.exe` artifact path, including MCP stdio smoke.
  It is not a signed installer, updater, marketplace download, or broad
  end-user binary distribution claim.
- macOS arm64 needs a real artifact built on macOS arm64, the full matrix below,
  Gatekeeper/quarantine notes, and dated ledger evidence before support can be
  claimed. The existing `macOS Install Smoke` workflow is a package/source
  install smoke, not a standalone-binary smoke.
- macOS x64 is intentionally outside the initial binary claim. Reopen it only
  if user demand or release requirements justify a separate Intel Mac artifact
  and runner.
- Linux x64 needs a clean container or VM build with no repository checkout on
  `PYTHONPATH`, the full matrix below, and dated ledger evidence before support
  can be claimed.

Public docs should point here for binary status instead of mirroring the full
matrix. If a platform is not marked smoke-tested above, the fallback is the
Python/source or `uvx --from` install path, not an implied standalone download.

## Candidate Tooling

| Candidate | Why consider it | Main risk |
| --- | --- | --- |
| PyInstaller | Mature single-file or folder-style Python app packaging; good Windows support. | Hidden imports and dynamic script dispatch need explicit collection rules. |
| Nuitka | Produces compiled artifacts and can improve startup for larger Python apps. | Build matrix is heavier and platform-specific failures can be slower to diagnose. |
| Pex / Shiv / zipapp | Keeps packaging close to Python semantics and is easier to audit. | Still requires a compatible Python runtime, so it does not satisfy a Python-free claim. |

Start with PyInstaller for a real Python-free spike. Keep Pex/Shiv as a
portable fallback for users who want a single-file launcher but already have
Python installed.

## Smoke Matrix

Each claimed platform needs a fresh artifact built on or for that platform:

| Platform | Required smoke checks |
| --- | --- |
| Windows x64 | `aippocampus --help`; `aippocampus health --help`; public-bundle search; `aippocampus mcp list-tools`; stdio JSON-RPC `tools/call:memory_health` through `aippocampus.exe mcp`; `aippocampus onboard --status --format json`; `aippocampus sync status --sync-dir <empty-dir> --json`; `aippocampus hooks status`; staged-runtime private-data guard; optional Claude Code strict MCP tool-call with `aippocampus.exe mcp` when claiming host integration. |
| macOS arm64 | Same checks as Windows, plus Gatekeeper/quarantine note if distributing a downloaded binary. |
| macOS x64 | Same checks as Windows; may be deferred if the project explicitly drops Intel Mac binary claims. |
| Linux x64 | Same checks as Windows on a clean container or VM with no repo checkout on `PYTHONPATH`. |

Smoke outputs must preserve child command JSON and exit codes. The binary must
not silently install hooks, scan private host history, or mutate registries
outside explicit operator commands. Direct script invocation is no longer a
fallback surface; repo and installed-skill flows should use the `aippocampus`
facade or package modules.

## Windows x64 Implementation

`tools/aippocampus/package_windows_binary.py` builds the Windows artifact with
PyInstaller. It stages `skills/aippocampus/scripts` into a temporary runtime
copy, generates a small frozen entrypoint for `aippocampus_runtime.cli.facade`
and then runs the smoke matrix above against the built executable.
The executable can also launch the stdio MCP server through
`aippocampus.exe mcp`; host-level proof still requires the dedicated Claude
Code smoke because `mcp list-tools` only proves local catalog generation.

The private-data guard intentionally checks the build input rather than treating
the executable as an arbitrary secret scanner. PyInstaller diagnostics may carry
machine-local build paths, but the artifact input is limited to the staged
installable runtime; repo-local `.aippocampus`, `aippocampus-registry`,
`transcripts`, `rollouts`, and private registry directories are not copied into
that staged runtime or passed as PyInstaller inputs.

The script only sets `python_free_support_claimed=true` after the artifact smoke
passes. `--dry-run` is allowed for planning and CI checks, but it must never be
reported as binary support.
