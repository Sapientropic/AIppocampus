"""Privacy and credential-transport guards for external runtime routes."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable
from urllib.parse import SplitResult, urlsplit

KEY_BLOCK_BOUNDARY = "-----"
GENERIC_PRIVATE_KEY_BLOCK = (
    rf"{KEY_BLOCK_BOUNDARY}BEGIN [A-Z ]*PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
    rf".*?"
    rf"{KEY_BLOCK_BOUNDARY}END [A-Z ]*PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
)
OPENSSH_PRIVATE_KEY_BLOCK = (
    rf"{KEY_BLOCK_BOUNDARY}BEGIN OPENSSH PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
    rf".*?"
    rf"{KEY_BLOCK_BOUNDARY}END OPENSSH PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
)

PATH_CLASS_BY_EXTENSION = {
    "bat": "script",
    "c": "source",
    "cfg": "config",
    "conf": "config",
    "cpp": "source",
    "cs": "source",
    "css": "style",
    "csv": "data",
    "go": "source",
    "h": "source",
    "hpp": "source",
    "html": "markup",
    "ini": "config",
    "java": "source",
    "js": "javascript",
    "json": "data",
    "jsx": "javascript",
    "log": "log",
    "md": "markdown",
    "ps1": "script",
    "py": "python",
    "rs": "rust",
    "sh": "script",
    "sql": "sql",
    "toml": "config",
    "ts": "typescript",
    "tsx": "typescript",
    "txt": "text",
    "yaml": "config",
    "yml": "config",
}
SAFE_PATH_EXTENSION_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")
MACOS_PRIVATE_VAR_PREFIX = "/private/var/"
MACOS_VAR_PREFIX = "/var/"


def _path_anchor_extension(raw_path: str) -> str:
    normalized = raw_path.replace("\\\\", "\\").replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1].strip()
    if "." not in filename:
        return ""
    ext = filename.rsplit(".", 1)[-1].casefold()
    return ext if SAFE_PATH_EXTENSION_RE.fullmatch(ext) else ""


def _relative_windows_path(raw_path: str, project_root: str) -> str | None:
    try:
        path = PureWindowsPath(raw_path.replace("\\\\", "\\"))
        root = PureWindowsPath(project_root.replace("\\\\", "\\"))
    except Exception:
        return None
    if not path.is_absolute() or not root.is_absolute():
        return None
    path_parts = [part.casefold() for part in path.parts]
    root_parts = [part.casefold() for part in root.parts]
    if len(path_parts) <= len(root_parts) or path_parts[: len(root_parts)] != root_parts:
        return None
    return "/".join(path.parts[len(root.parts) :])


def _macos_var_path_spellings(path: str) -> tuple[str, ...]:
    # GitHub macOS runners and Python temp APIs can expose the same workspace as
    # /var/... or /private/var/.... Keep that known host alias from turning a
    # project-local path into an external identity, while still using lexical
    # comparison instead of resolving arbitrary user-supplied paths.
    if path.startswith(MACOS_PRIVATE_VAR_PREFIX):
        return (path, path.removeprefix("/private"))
    if path.startswith(MACOS_VAR_PREFIX):
        return (path, f"/private{path}")
    return (path,)


def _relative_posix_path_once(raw_path: str, project_root: str) -> str | None:
    try:
        path = PurePosixPath(raw_path)
        root = PurePosixPath(project_root)
    except Exception:
        return None
    if not path.is_absolute() or not root.is_absolute():
        return None
    path_parts = list(path.parts)
    root_parts = list(root.parts)
    if len(path_parts) <= len(root_parts) or path_parts[: len(root_parts)] != root_parts:
        return None
    return "/".join(path.parts[len(root.parts) :])


def _relative_posix_path(raw_path: str, project_root: str) -> str | None:
    for path_text in _macos_var_path_spellings(raw_path):
        for root_text in _macos_var_path_spellings(project_root):
            relative_path = _relative_posix_path_once(path_text, root_text)
            if relative_path:
                return relative_path
    return None


def _project_relative_path(raw_path: str, project_root: str | Path | None) -> str | None:
    if not project_root:
        return None
    root_text = str(project_root)
    normalized = raw_path.replace("\\\\", "\\")
    if re.match(r"^[A-Za-z]:[\\/]", normalized) or re.match(r"^[A-Za-z]:[\\/]", root_text):
        return _relative_windows_path(normalized, root_text)
    if normalized.startswith("/") and str(root_text).startswith("/"):
        return _relative_posix_path(normalized, root_text)
    return None


def _local_path_anchor(
    raw_path: str,
    *,
    kind: str,
    project_root: str | Path | None = None,
) -> str:
    ext = _path_anchor_extension(raw_path)
    path_class = PATH_CLASS_BY_EXTENSION.get(ext, "unknown")
    relative_path = _project_relative_path(raw_path, project_root)
    scope = "project" if relative_path else "external"
    parts = [
        "<redacted:local-path><path-anchor",
        f"scope={scope}",
        f"kind={kind}",
        f"class={path_class}",
    ]
    if ext:
        parts.append(f"ext={ext}")
    if relative_path:
        digest = hashlib.sha256(
            relative_path.casefold().encode("utf-8", errors="replace")
        ).hexdigest()[:16]
        parts.append(f"hash=sha256:{digest}")
    return " ".join(parts) + ">"


PathAnchorReplacement = Callable[[re.Match[str], str | Path | None], str]


def _path_anchor_replacement(kind: str) -> PathAnchorReplacement:
    def replace(match: re.Match[str], project_root: str | Path | None = None) -> str:
        return _local_path_anchor(match.group(0), kind=kind, project_root=project_root)

    return replace


EXTERNAL_MODEL_REDACTION_PATTERNS: list[
    tuple[str, re.Pattern[str], str | PathAnchorReplacement]
] = [
    (
        "private_key_block",
        re.compile(GENERIC_PRIVATE_KEY_BLOCK, re.IGNORECASE | re.DOTALL),
        "<redacted:private-key-block>",
    ),
    (
        "private_key_block",
        re.compile(OPENSSH_PRIVATE_KEY_BLOCK, re.IGNORECASE | re.DOTALL),
        "<redacted:private-key-block>",
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
        "<redacted:api-key>",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
        "Bearer <redacted:bearer-token>",
    ),
    (
        "credential_url",
        re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)[^@\s:/]+:[^@\s]+@"),
        r"\1<redacted:credentials>@",
    ),
    (
        "secret_assignment",
        re.compile(
            r"\b(api[_-]?key|secret|token|password|passwd|cookie|authorization)\b\s*[:=]\s*"
            r"(\"[^\"]*\"|'[^']*'|(?!(?:<redacted:))[^\s,;&]+)",
            re.IGNORECASE,
        ),
        r"\1=<redacted:secret>",
    ),
    (
        "json_escaped_windows_local_path",
        re.compile(r"(?<![\w])(?:[A-Za-z]:\\\\[^\"'\s<>]+)"),
        _path_anchor_replacement("windows_json_escaped"),
    ),
    (
        "windows_local_path",
        re.compile(
            r"(?<![\w])(?:[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n\t ]+\\?)+"
            r"[^\\/:*?\"<>|\r\n\t ]*)"
        ),
        _path_anchor_replacement("windows"),
    ),
    (
        "posix_local_path",
        re.compile(
            r"(?<![\w:/])/(?:Users|home|root|tmp|var|mnt|Volumes|private)/"
            r"(?:[^\s\"'<>]+)"
        ),
        _path_anchor_replacement("posix"),
    ),
]

BENCHMARK_PRIVATE_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
BENCHMARK_DATABASE_DSN_PATTERN = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|mssql|sqlserver)"
    r"://[^\s\"'<>]+",
    re.IGNORECASE,
)
BENCHMARK_DATABASE_KV_PATTERN = re.compile(
    r"\b(?:Server|Data Source|Initial Catalog|Database|User ID|Uid|PWD|Password)\s*=",
    re.IGNORECASE,
)
BENCHMARK_PRIVATE_HOST_PATTERN = re.compile(
    r"\b(?:localhost|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\."
    r"(?:internal|intranet|corp|lan|local))(?:[:/][^\s\"'<>]*)?",
    re.IGNORECASE,
)
BENCHMARK_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
CLEAN_SOURCE_REDACTION_PROFILES = {"raw-private", "redacted-local", "public-export"}
CLEAN_SOURCE_DATABASE_KV_PATTERN = re.compile(
    r"\b(?:(?:Server|Data Source|Initial Catalog|Database|User ID|Uid|PWD|Password)"
    r"\s*=[^;\s]+;?\s*){2,}",
    re.IGNORECASE,
)


def _text_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def sanitize_external_model_text(
    text: str,
    *,
    project_root: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Redact likely secrets before automatic external-model calls.

    Clean source can include pasted credentials or machine-local paths. This
    helper is intentionally shared by all model-compatible routes so new
    workers do not accidentally bypass the prompt-hook privacy boundary.
    """

    original = str(text or "")
    sanitized = original
    redaction_types: list[str] = []
    redaction_count = 0
    for label, pattern, replacement in EXTERNAL_MODEL_REDACTION_PATTERNS:
        if isinstance(replacement, str):
            sanitized, count = pattern.subn(replacement, sanitized)
        else:
            path_replacement = replacement

            def replace_path(
                match: re.Match[str],
                repl: PathAnchorReplacement = path_replacement,
            ) -> str:
                return repl(match, project_root)

            sanitized, count = pattern.subn(replace_path, sanitized)
        if count:
            redaction_types.append(label)
            redaction_count += count

    remaining = re.sub(r"<redacted:[^>]+>", " ", sanitized)
    remaining = re.sub(r"<path-anchor[^>]+>", " ", remaining)
    remaining = re.sub(r"\s+", " ", remaining).strip()
    hard_block = bool(redaction_count and len(remaining) < 12)
    return sanitized, {
        "redacted": bool(redaction_count),
        "redaction_count": redaction_count,
        "redaction_types": list(dict.fromkeys(redaction_types))[:8],
        "hard_block": hard_block,
        "reason": "prompt mostly secret/credential material after redaction" if hard_block else "",
    }


def sanitize_external_model_payload(
    value: Any,
    *,
    project_root: str | Path | None = None,
) -> Any:
    if isinstance(value, str):
        sanitized, _ = sanitize_external_model_text(value, project_root=project_root)
        return sanitized
    if isinstance(value, list):
        return [sanitize_external_model_payload(item, project_root=project_root) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_external_model_payload(item, project_root=project_root) for item in value)
    if isinstance(value, dict):
        return {
            key: sanitize_external_model_payload(item, project_root=project_root)
            for key, item in value.items()
        }
    return value


def _benchmark_private_ip_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    for match in BENCHMARK_IPV4_PATTERN.finditer(text):
        try:
            address = ipaddress.ip_address(match.group(0))
        except ValueError:
            continue
        if address.is_private or address.is_loopback or address.is_link_local:
            reasons.append("private_ip_address")
            break
    return reasons


def benchmark_sensitive_text_policy(text: str) -> dict[str, Any]:
    """Classify text that must not be selected into publishable benchmark cases.

    Benchmark case selection is deliberately stricter than prompt redaction:
    external-model routes may redact and continue when safe context remains,
    while public benchmark fixtures should skip obvious private material before
    it becomes a case target. The returned policy stores only bounded reason
    labels, never the matched text.
    """

    original = str(text or "")
    _, redaction_policy = sanitize_external_model_text(original)
    reasons: list[str] = []
    if redaction_policy.get("hard_block"):
        reasons.append("runtime_hard_block")
    for label in redaction_policy.get("redaction_types") or []:
        reasons.append(str(label))
    if BENCHMARK_PRIVATE_EMAIL_PATTERN.search(original):
        reasons.append("email_address")
    if BENCHMARK_DATABASE_DSN_PATTERN.search(original) or BENCHMARK_DATABASE_KV_PATTERN.search(
        original
    ):
        reasons.append("database_connection_string")
    if BENCHMARK_PRIVATE_HOST_PATTERN.search(original):
        reasons.append("private_hostname")
    reasons.extend(_benchmark_private_ip_reasons(original))
    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "sensitive": bool(unique_reasons),
        "policy": "aippocampus_runtime.safety.benchmark_sensitive_text_policy",
        "uses_runtime_redaction": True,
        "redaction_count": int(redaction_policy.get("redaction_count") or 0),
        "hard_block": bool(redaction_policy.get("hard_block")),
        "reason_categories": unique_reasons[:12],
    }


def benchmark_text_is_sensitive(text: str) -> bool:
    return bool(benchmark_sensitive_text_policy(text)["sensitive"])


def project_clean_source_text(
    text: str,
    *,
    profile: str = "raw-private",
    project_root: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Project clean-source text into an optional at-rest privacy profile.

    `raw-private` is the canonical source text. Redacted profiles are privacy
    projections only; callers must preserve source refs / message ids if they
    need to reopen the private source later.
    """

    profile = str(profile or "raw-private")
    if profile not in CLEAN_SOURCE_REDACTION_PROFILES:
        raise ValueError(f"unknown clean-source redaction profile: {profile}")

    original = str(text or "")
    if profile == "raw-private":
        return original, {
            "profile": profile,
            "redacted": False,
            "redaction_count": 0,
            "redaction_types": [],
            "hard_block": False,
            "source_fidelity": "canonical",
            "policy": "aippocampus_runtime.safety.project_clean_source_text",
        }

    projected = original
    redaction_types: list[str] = []
    redaction_count = 0
    extra_patterns: list[tuple[str, re.Pattern[str], str]] = [
        (
            "database_connection_string",
            BENCHMARK_DATABASE_DSN_PATTERN,
            "<redacted:connection-string>",
        ),
        (
            "database_connection_string",
            CLEAN_SOURCE_DATABASE_KV_PATTERN,
            "<redacted:connection-string>",
        ),
        ("email_address", BENCHMARK_PRIVATE_EMAIL_PATTERN, "<redacted:email>"),
    ]
    for label, pattern, replacement in extra_patterns:
        projected, count = pattern.subn(replacement, projected)
        if count:
            redaction_types.append(label)
            redaction_count += count

    projected, external_policy = sanitize_external_model_text(
        projected,
        project_root=project_root,
    )
    redaction_count += int(external_policy.get("redaction_count") or 0)
    redaction_types.extend(str(item) for item in external_policy.get("redaction_types") or [])
    unique_types = list(dict.fromkeys(redaction_types))
    return projected, {
        "profile": profile,
        "redacted": bool(redaction_count),
        "redaction_count": redaction_count,
        "redaction_types": unique_types[:12],
        "hard_block": bool(external_policy.get("hard_block")),
        "source_fidelity": "projection",
        "policy": "aippocampus_runtime.safety.project_clean_source_text",
        "external_model_policy": external_policy,
    }


def project_clean_source_row(
    row: dict[str, Any],
    *,
    profile: str = "raw-private",
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a clean-source row projected for an optional privacy profile."""

    projected = dict(row)
    projected_text, policy = project_clean_source_text(
        str(projected.get("text") or ""),
        profile=profile,
        project_root=project_root,
    )
    if profile != "raw-private":
        # Keep original ids/hashes as source-reopen join keys. The redacted hash
        # identifies only this projection text and must not replace content_sha256.
        projected["text"] = projected_text
        projected["redaction_profile"] = profile
        projected["redaction_policy"] = policy
        projected["redacted_text_sha256"] = _text_sha256(projected_text)
    return projected


def is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_http_endpoint_url(endpoint_url: str, *, service_name: str) -> SplitResult:
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{service_name} must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{service_name} must not include credentials")
    return parsed


def validate_private_credential_transport(
    endpoint_url: str, *, service_name: str, credential_label: str
) -> None:
    parsed = validate_http_endpoint_url(endpoint_url, service_name=service_name)
    # Local model proxies and dev object stores commonly use plain HTTP. Keep
    # that loopback path usable, but never let bearer-style credentials travel
    # over network HTTP because the receiving service may still look legitimate.
    if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
        raise ValueError(
            f"{credential_label} for {service_name} requires HTTPS unless endpoint is loopback"
        )


def deepseek_cache_metrics_from_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage if isinstance(usage, dict) else {}
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or 0)
    total = hit + miss
    return {
        "available": "prompt_cache_hit_tokens" in usage or "prompt_cache_miss_tokens" in usage,
        "hit_tokens": hit,
        "miss_tokens": miss,
        "hit_rate": round(hit / total, 4) if total else 0.0,
    }
