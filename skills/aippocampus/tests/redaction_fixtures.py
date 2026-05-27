"""Shared fake literals for redaction tests.

These values intentionally match the redaction regexes while carrying a clear
FAKE_TEST marker, so public secret/local-path scanners do not mistake them for
real credentials or a developer machine path.
"""

from __future__ import annotations

FAKE_TEST_OPENAI_API_KEY = "sk-FAKE_TEST_OPENAI_REDACTION_1234567890"
FAKE_TEST_BEARER_TOKEN = "FAKETESTBEARERTOKEN1234567890"
FAKE_TEST_SECRET_VALUE = "FAKE_TEST_SECRET_VALUE_1234567890"
FAKE_TEST_PASSWORD_VALUE = "FAKE_TEST_PASSWORD_VALUE_1234567890"
FAKE_TEST_WINDOWS_LOCAL_PATH_ROOT = r"C:\FAKE_TEST_LOCAL_PATH\Secrets"
FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER = r"C:\\FAKE_TEST_LOCAL_PATH"


def fake_test_windows_path(filename: str) -> str:
    return FAKE_TEST_WINDOWS_LOCAL_PATH_ROOT + "\\" + filename
