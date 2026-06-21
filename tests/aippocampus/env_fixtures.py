from __future__ import annotations

import os
import unittest
from collections.abc import Iterable, Mapping

DEEPSEEK_MODEL_ENV_VARS = (
    "AIPPOCAMPUS_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_BASE_URL",
    "AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL",
    "AIPPOCAMPUS_DEEPSEEK_BASE_URL",
    "AIPPOCAMPUS_DEEPSEEK_PRO_MODEL",
    "DEEPSEEK_PRO_MODEL",
)

OPENAI_COMPAT_MODEL_ENV_VARS = (
    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE",
    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER",
    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL",
    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL",
    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
    "AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY",
    "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON",
    "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID",
    "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING",
    "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT",
    "AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING",
    "AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT",
    "AIPPOCAMPUS_OPENAI_COMPAT_REASONING_CONTENT_HANDLING",
    "AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND",
)

MODEL_ROUTING_ENV_VARS = (
    *DEEPSEEK_MODEL_ENV_VARS,
    *OPENAI_COMPAT_MODEL_ENV_VARS,
)


def isolate_env_vars_for_testcase(
    testcase: unittest.TestCase,
    names: Iterable[str],
    *,
    defaults: Mapping[str, str | None] | None = None,
) -> None:
    """Clear selected env vars for a unittest and restore them after the test.

    Provider-routing tests deliberately mutate public config names that local
    dogfood runs may also use. Keep that boundary in one fixture so a future
    test cannot quietly leak an operator's real model route or key-env setting
    into another case.
    """

    target_names = tuple(dict.fromkeys(names))
    previous = {name: os.environ.get(name) for name in target_names}
    for name in target_names:
        os.environ.pop(name, None)
    for name, value in (defaults or {}).items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def restore() -> None:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    testcase.addCleanup(restore)
