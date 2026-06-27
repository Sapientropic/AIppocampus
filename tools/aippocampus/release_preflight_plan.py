from __future__ import annotations

from guard_registry import decorate_command, guard_registry_summary
from test_plan_commands import py_command, py_script


def _command_row(command: str, reason: str, scope: str) -> dict[str, object]:
    return decorate_command({"command": command, "reason": reason, "scope": scope})


def _ci_owned_command_row(command: str, reason: str, scope: str = "surface") -> dict[str, object]:
    row = _command_row(command, reason, scope)
    row.update(
        {
            "gate_class": "ci_owned",
            "verification_owner": "ci_required",
            "cost_budget": "ci",
            "cost_budget_ms": 0,
            "ci_owned": True,
            "default_local": False,
        }
    )
    return row


def build_release_preflight_plan(
    *,
    local_executable: bool = False,
    ci_ruff_command: str,
    ci_mypy_command: str,
) -> dict[str, object]:
    return {
        "kind": "aippocampus_release_preflight_plan",
        "schema_version": 2,
        "command_mode": "local_executable" if local_executable else "portable",
        "verification_ownership": guard_registry_summary(),
        "assumption": "Use after the release PR CI is green and before pushing the tag.",
        "gate_policy": {
            "default_local_closeout": "focused_plan_then_pr_once",
            "do_not_stack_quick_before_pr": True,
            "do_not_repeat_ci_owned_gates_after_green_pr": True,
            "broad_pr_benchmark_full_are_escalations": True,
            "publish_workflow_owns_wheel_and_registry_checks": True,
        },
        "local_closeout_sequence": [
            _command_row(
                py_script(
                    "tools/aippocampus/test_plan.py",
                    "--json",
                    local_executable=local_executable,
                ),
                "Record the changed-surface plan before release closeout.",
                "decision",
            ),
            _command_row(
                "run focused commands named by the plan that have not already passed",
                "Human/agent step: execute only the focused proof the changed-surface plan names.",
                "focused",
            ),
            _command_row(
                py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier pr",
                    local_executable=local_executable,
                ),
                "`pr` is the local closeout tier; do not stack quick immediately before it.",
                "pre-push",
            ),
            _command_row(
                py_script(
                    "tools/aippocampus/release/check_public_boundary.py",
                    "--json",
                    local_executable=local_executable,
                ),
                "Release-facing tracked files need a local public-boundary scan.",
                "public-boundary",
            ),
            _command_row(
                py_script(
                    "tools/aippocampus/docs/check_docs_health.py",
                    "--json",
                    local_executable=local_executable,
                ),
                "Release notes, docs pointers, and public claims must still resolve.",
                "release-preflight",
            ),
        ],
        "local_required": _local_required(local_executable=local_executable),
        "local_if_ci_unavailable_or_changed_after_ci": [
            _command_row(
                ci_ruff_command,
                "CI already mirrors this for a green PR; rerun locally only if CI is unavailable or stale.",
                "static",
            ),
            _command_row(
                ci_mypy_command,
                "CI already mirrors this for a green PR; rerun locally only if CI is unavailable or stale.",
                "static",
            ),
            _command_row(
                py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier pr",
                    local_executable=local_executable,
                ),
                "`pr` includes `quick`; do not run both as a closeout ritual. CI already owns this for a green PR.",
                "pre-push",
            ),
        ],
        "ci_owned_do_not_repeat_locally_by_default": _ci_owned_rows(
            local_executable=local_executable
        ),
        "publish_workflow_owned": _publish_owned_rows(local_executable=local_executable),
        "escalate_locally_when": [
            "Run broad-pr locally only for tier-runner/manifest/CI changes when waiting for CI would hide the failure source.",
            "Run benchmark-smoke locally only for benchmark runner, benchmark fixture, or public benchmark claim changes.",
            "Run full locally only for repository-health or public-readiness claims that explicitly need the slow/benchmark/release-heavy surface.",
            "Run manual macOS install smoke for package/install/path-identity changes, or when the release itself claims fresh macOS install behavior.",
        ],
        "post_publish_required": _post_publish_required(local_executable=local_executable),
        "boundary": (
            "A routine patch/minor release should not re-run broad-pr, benchmark-smoke, "
            "coverage, full, and manual macOS smoke locally after green PR CI. Those "
            "lanes are escalation tools or CI/publish responsibilities."
        ),
    }


def _local_required(*, local_executable: bool) -> list[dict[str, object]]:
    return [
        _command_row(
            py_script("tools/aippocampus/test_plan.py", "--json", local_executable=local_executable),
            "Record the changed-surface plan and run only the focused commands it names that have not already passed in CI.",
            "decision",
        ),
        _command_row(
            py_script(
                "tools/aippocampus/docs/check_docs_health.py",
                "--json",
                local_executable=local_executable,
            ),
            "Release notes, docs pointers, and public claims must still resolve.",
            "release-preflight",
        ),
        _command_row(
            py_script(
                "tools/aippocampus/release/check_public_boundary.py",
                "--json",
                local_executable=local_executable,
            ),
            "Scan release-facing tracked files for local paths, credentials, and private strings.",
            "public-boundary",
        ),
        _command_row(
            py_script(
                "tools/aippocampus/release/check_agent_discovery_release.py",
                "--offline --json",
                local_executable=local_executable,
            ),
            "Before publication, verify local PyPI/MCP metadata without waiting on remote indexes.",
            "release-preflight",
        ),
        _command_row(
            "git clean -ndX",
            "Preview ignored generated artifacts; remove only owned build output, never private memory surfaces.",
            "public-boundary",
        ),
        _command_row("git diff --check", "Catch whitespace/conflict-marker mistakes cheaply before tagging.", "public-boundary"),
    ]


def _ci_owned_rows(*, local_executable: bool) -> list[dict[str, object]]:
    return [
        _ci_owned_command_row(
            py_script("tools/aippocampus/run_tests.py", "--tier quick", local_executable=local_executable),
            "CI runs quick in a clean environment; do not rerun after green CI unless local state changed.",
            "sanity",
        ),
        _ci_owned_command_row(
            py_script("tools/aippocampus/run_tests.py", "--tier broad-pr", local_executable=local_executable),
            "CI owns broad deterministic shards for normal closeout.",
        ),
        _ci_owned_command_row(
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier benchmark-smoke --benchmark-suite-profile public-fast",
                local_executable=local_executable,
            ),
            "CI owns benchmark smoke unless the changed surface is benchmark evidence itself.",
        ),
        _ci_owned_command_row(
            py_script("tools/aippocampus/run_coverage.py", "--tier pr", local_executable=local_executable),
            "Coverage is a CI/public-readiness lane, not a default local ritual.",
        ),
        _ci_owned_command_row(
            py_script("tools/aippocampus/run_tests.py", "--tier full", local_executable=local_executable),
            "Full is release-heavy CI evidence unless a release claim explicitly needs it locally.",
        ),
        _ci_owned_command_row(
            "gh workflow run macos-install-smoke.yml -f runner-label=macos-latest -f python-version=3.12",
            "macOS install behavior is platform CI/manual evidence, not a routine local command.",
        ),
    ]


def _publish_owned_rows(*, local_executable: bool) -> list[dict[str, object]]:
    return [
        _command_row(
            py_command('-m pip install -e ".[release]"', local_executable=local_executable),
            "Publish workflow owns release extras installation in a clean environment.",
            "publish",
        ),
        _command_row(
            py_script("tools/aippocampus/run_tests.py", "--tier pr", local_executable=local_executable),
            "Publish workflow re-proves PR tier for the artifact path.",
            "publish",
        ),
        _command_row("check-jsonschema server.json", "Publish workflow validates MCP server metadata.", "publish"),
        _command_row(
            py_command("-m build --sdist --wheel", local_executable=local_executable),
            "Publish workflow owns package artifact construction.",
            "publish",
        ),
        _command_row(
            py_command("-m twine check dist/*", local_executable=local_executable),
            "Publish workflow owns wheel/sdist metadata validation.",
            "publish",
        ),
        _command_row(
            py_script(
                "tools/aippocampus/release/check_wheel_contract.py",
                "--wheel dist/*.whl --json",
                local_executable=local_executable,
            ),
            "Publish workflow owns final wheel contract verification.",
            "publish",
        ),
        _command_row("PyPI publish", "Remote publication is owned by the release workflow.", "publish"),
        _command_row(
            "MCP Registry validate and publish",
            "Remote MCP registry validation/publication is owned by the release workflow.",
            "publish",
        ),
    ]


def _post_publish_required(*, local_executable: bool) -> list[dict[str, object]]:
    return [
        _command_row(
            py_script(
                "tools/aippocampus/release/check_agent_discovery_release.py",
                "--wait-ready --wait-seconds 300 --poll-interval 20 --fail-on-not-ready --json",
                local_executable=local_executable,
            ),
            "After PyPI and MCP Registry publication, remote agent discovery must be claim-ready.",
            "post-publish",
        ),
        _command_row(
            py_command("-m pip index versions aippocampus --no-cache-dir", local_executable=local_executable),
            "Confirm PyPI's public simple/index view has caught up before saying latest is available.",
            "post-publish",
        ),
        _command_row(
            py_command("-m pip install aippocampus==<version>", local_executable=local_executable),
            "Install the released wheel in a fresh environment, not the checkout.",
            "post-publish",
        ),
    ]
