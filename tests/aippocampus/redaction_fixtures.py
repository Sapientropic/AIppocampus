"""Shared fake literals for redaction tests.

These values intentionally match the redaction regexes while carrying a clear
FAKE_TEST marker, so public secret/local-path scanners do not mistake them for
real credentials or a developer machine path.
"""

from __future__ import annotations


def fake_test_openai_api_key(label: str = "OPENAI_REDACTION") -> str:
    prefix = "s" + "k" + "-"
    return f"{prefix}FAKE_TEST_{label}_1234567890"

def fake_test_bearer_token(label: str = "BEARERTOKEN") -> str:
    return f"FAKETEST{label}1234567890"

def fake_test_bearer_header(label: str = "BEARERTOKEN") -> str:
    return ("Bear" + "er") + " " + fake_test_bearer_token(label)

FAKE_TEST_OPENAI_API_KEY = fake_test_openai_api_key()
FAKE_TEST_BEARER_TOKEN = fake_test_bearer_token()
FAKE_TEST_SECRET_VALUE = "FAKE_TEST_SECRET_VALUE_1234567890"
FAKE_TEST_PASSWORD_VALUE = "FAKE_TEST_PASSWORD_VALUE_1234567890"
FAKE_TEST_WINDOWS_LOCAL_PATH_ROOT = r"C:\FAKE_TEST_LOCAL_PATH\Secrets"
FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER = r"C:\\FAKE_TEST_LOCAL_PATH"

def fake_test_email() -> str:
    return "person" + "@" + "example.com"

def fake_test_database_dsn() -> str:
    return "postgres://db.internal:5432/app"

def fake_test_credential_url() -> str:
    credential = "".join(chr(code) for code in (112, 97, 115, 115))
    return "https://user:" + credential + "@service.internal/path"

def fake_test_windows_path(filename: str) -> str:
    return FAKE_TEST_WINDOWS_LOCAL_PATH_ROOT + "\\" + filename
