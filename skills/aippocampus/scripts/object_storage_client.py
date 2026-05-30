#!/usr/bin/env python3
"""HTTP client boundary for AIppocampus object storage sync."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import object_storage_providers
import sync_bundle
from aippocampuslib import validate_http_endpoint_url, validate_private_credential_transport

OBJECT_BACKEND = "http_object_store"
DEFAULT_PREFIX = "aippocampus/sync"
DEFAULT_TIMEOUT_SECONDS = 20.0


def normalize_object_prefix(value: str | None) -> str:
    text = str(value or "").replace("\\", "/").strip("/")
    if not text:
        return ""
    return sync_bundle.validate_relative_sync_path(text).as_posix()


def object_key(prefix: str | None, relative_path: str | Path) -> str:
    path = sync_bundle.validate_relative_sync_path(relative_path)
    normalized_prefix = normalize_object_prefix(prefix)
    if not normalized_prefix:
        return path.as_posix()
    return f"{normalized_prefix}/{path.as_posix()}"


def safe_endpoint_label(endpoint_url: str) -> str:
    parsed = urlsplit(endpoint_url)
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class HttpObjectStoreClient:
    endpoint_url: str
    prefix: str = DEFAULT_PREFIX
    token: str | None = None
    provider: str = object_storage_providers.GENERIC_HTTP_PROVIDER
    auth: object_storage_providers.SigV4Auth | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        validate_http_endpoint_url(self.endpoint_url, service_name="object store endpoint")
        if self.token and self.auth:
            raise ValueError("object store token cannot be combined with signing credentials")
        if self.token:
            validate_private_credential_transport(
                self.endpoint_url,
                service_name="object store endpoint",
                credential_label="object store token",
            )
        if self.auth:
            validate_private_credential_transport(
                self.endpoint_url,
                service_name="object store endpoint",
                credential_label="object store signing key",
            )
        normalize_object_prefix(self.prefix)

    def url_for(self, relative_path: str | Path) -> str:
        key = object_key(self.prefix, relative_path)
        quoted = "/".join(quote(part, safe="") for part in key.split("/"))
        return f"{self.endpoint_url.rstrip('/')}/{quoted}"

    def headers(
        self,
        content_type: str | None = None,
        *,
        method: str = "GET",
        url: str | None = None,
        data: bytes | None = None,
    ) -> dict[str, str]:
        headers = {"User-Agent": "AIppocampus-object-sync/0.1"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.auth:
            headers = self.auth.sign(
                method=method,
                url=url or self.endpoint_url,
                payload=data or b"",
                headers=headers,
            )
        return headers

    def request(self, method: str, relative_path: str | Path, data: bytes | None = None) -> bytes:
        key = object_key(self.prefix, relative_path)
        url = self.url_for(relative_path)
        request = Request(
            url,
            data=data,
            headers=self.headers(
                "application/octet-stream" if data is not None else None,
                method=method,
                url=url,
                data=data or b"",
            ),
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(key) from exc
            detail = exc.read(512).decode("utf-8", errors="replace")
            raise RuntimeError(
                f"object store {method} failed for {key}: HTTP {exc.code} {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"object store {method} failed for {key}: {exc.reason}") from exc

    def put_object(self, relative_path: str | Path, data: bytes) -> dict[str, Any]:
        self.request("PUT", relative_path, data)
        return {"key": object_key(self.prefix, relative_path), "size": len(data)}

    def get_object(self, relative_path: str | Path) -> bytes:
        return self.request("GET", relative_path)

    def delete_object(self, relative_path: str | Path) -> dict[str, Any]:
        self.request("DELETE", relative_path)
        return {"key": object_key(self.prefix, relative_path)}


def client_for(
    object_store_url: str,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> HttpObjectStoreClient:
    return HttpObjectStoreClient(object_store_url, prefix=prefix, token=token, timeout=timeout)


def client_for_provider(
    *,
    provider: str | None = None,
    endpoint_url: str | None = None,
    bucket: str | None = None,
    prefix: str = DEFAULT_PREFIX,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> HttpObjectStoreClient:
    config = object_storage_providers.provider_config(
        provider,
        endpoint_url=endpoint_url,
        bucket=bucket,
        region=region,
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
    )
    return HttpObjectStoreClient(
        config.endpoint_url,
        prefix=prefix,
        token=token,
        provider=config.provider,
        auth=config.auth,
        timeout=timeout,
    )


def object_storage_client_for(
    object_store_url: str | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> HttpObjectStoreClient:
    provider_requested = any(
        value
        for value in (
            provider,
            bucket,
            region,
            account_id,
            access_key_id,
            secret_access_key,
            session_token,
        )
    )
    if provider_requested:
        return client_for_provider(
            provider=provider,
            endpoint_url=object_store_url,
            bucket=bucket,
            prefix=prefix,
            region=region,
            account_id=account_id,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            session_token=session_token,
            token=token,
            timeout=timeout,
        )
    if not object_store_url:
        raise ValueError("object store URL is required")
    return client_for(object_store_url, prefix=prefix, token=token, timeout=timeout)
