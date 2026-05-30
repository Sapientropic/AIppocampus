# Standalone Binary Packaging Plan

This is a follow-up packaging plan, not a release claim. The current public
surface is the Python `aippocampus` console facade plus direct script fallback.
Do not claim Python-free installs until the binary artifact for each platform
below has been built, smoke-tested, and linked from the dated evidence ledger.

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
| Windows x64 | `aippocampus --help`; `aippocampus health --help`; `aippocampus mcp list-tools`; `aippocampus onboard --status --format json`; `aippocampus sync status --sync-dir <empty-dir> --json`; product-surface secret/path scan. |
| macOS arm64 | Same checks as Windows, plus Gatekeeper/quarantine note if distributing a downloaded binary. |
| macOS x64 | Same checks as Windows; may be deferred if the project explicitly drops Intel Mac binary claims. |
| Linux x64 | Same checks as Windows on a clean container or VM with no repo checkout on `PYTHONPATH`. |

Smoke outputs must preserve child command JSON and exit codes. The binary must
not silently install hooks, scan private host history, or mutate registries
outside explicit operator commands. Direct script invocation remains the
fallback until the matrix above passes.
