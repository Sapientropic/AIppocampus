# Standalone Binary Packaging Plan

This is the packaging plan and claim boundary for optional Python-free
AIppocampus binaries. The canonical implementation remains the source-backed
Python runtime; direct Python/script usage stays supported as the fallback.

As of 2026-05-31, Windows x64 has a PyInstaller artifact smoke, plus
post-package-refactor binary MCP re-smokes through current `main` commit
`a5217d1`, recorded in
`docs/evidence/readiness/public-readiness-verification.md`. Do not claim any
other platform until its artifact is built, smoke-tested, and linked from the
dated evidence ledger.

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
| Windows x64 | `aippocampus --help`; `aippocampus health --help`; public-bundle search; `aippocampus mcp list-tools`; `aippocampus onboard --status --format json`; `aippocampus sync status --sync-dir <empty-dir> --json`; `aippocampus hooks status`; staged-runtime private-data guard; optional Claude Code strict MCP tool-call with `aippocampus.exe mcp` when claiming host integration. |
| macOS arm64 | Same checks as Windows, plus Gatekeeper/quarantine note if distributing a downloaded binary. |
| macOS x64 | Same checks as Windows; may be deferred if the project explicitly drops Intel Mac binary claims. |
| Linux x64 | Same checks as Windows on a clean container or VM with no repo checkout on `PYTHONPATH`. |

Smoke outputs must preserve child command JSON and exit codes. The binary must
not silently install hooks, scan private host history, or mutate registries
outside explicit operator commands. Direct script invocation remains the
fallback until the matrix above passes.

## Windows x64 Implementation

`tools/aippocampus/package_windows_binary.py` builds the Windows artifact with
PyInstaller. It stages `skills/aippocampus/scripts` into a temporary runtime
copy, generates a small frozen entrypoint for `aippocampus_runtime.cli.facade`
while keeping the `aippocampus_cli.py` compatibility shim available, and then
runs the smoke matrix above against the built executable.
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
