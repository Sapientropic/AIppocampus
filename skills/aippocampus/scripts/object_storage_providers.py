#!/usr/bin/env python3
"""Provider-aware object storage endpoint and signing helpers."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from aippocampuslib import validate_http_endpoint_url

GENERIC_HTTP_PROVIDER = "generic-http"
S3_PROVIDER = "s3"
R2_PROVIDER = "r2"
GCS_XML_PROVIDER = "gcs-xml"


def normalize_provider(value: str | None) -> str:
    provider = (value or GENERIC_HTTP_PROVIDER).strip().replace("_", "-").casefold()
    aliases = {
        "http": GENERIC_HTTP_PROVIDER,
        "generic": GENERIC_HTTP_PROVIDER,
        "generic-http": GENERIC_HTTP_PROVIDER,
        "generic-http-object-store": GENERIC_HTTP_PROVIDER,
        "s3": S3_PROVIDER,
        "aws-s3": S3_PROVIDER,
        "s3-compatible": S3_PROVIDER,
        "r2": R2_PROVIDER,
        "cloudflare-r2": R2_PROVIDER,
        "gcs": GCS_XML_PROVIDER,
        "gcs-xml": GCS_XML_PROVIDER,
        "google-cloud-storage-xml": GCS_XML_PROVIDER,
    }
    if provider not in aliases:
        raise ValueError(f"unsupported object storage provider: {value}")
    return aliases[provider]


def require_bucket(bucket: str | None) -> str:
    text = str(bucket or "").strip()
    if not text:
        raise ValueError("object storage bucket is required for this provider")
    if "/" in text or "\\" in text:
        raise ValueError("object storage bucket must not contain path separators")
    return text


def append_bucket_path(endpoint_url: str, bucket: str) -> str:
    parsed = validate_http_endpoint_url(endpoint_url, service_name="object store endpoint")
    encoded_bucket = quote(bucket, safe="")
    path = parsed.path.rstrip("/")
    if path.casefold().rstrip("/").endswith(f"/{encoded_bucket.casefold()}"):
        bucket_path = path
    else:
        bucket_path = f"{path}/{encoded_bucket}" if path else f"/{encoded_bucket}"
    return urlunsplit((parsed.scheme, parsed.netloc, bucket_path, "", ""))


def canonical_query(query: str) -> str:
    pairs = parse_qsl(query, keep_blank_values=True)
    encoded = [
        (quote(key, safe="-_.~"), quote(value, safe="-_.~"))
        for key, value in pairs
    ]
    return "&".join(f"{key}={value}" for key, value in sorted(encoded))


def hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


@dataclass(frozen=True)
class SigV4Auth:
    access_key_id: str
    secret_access_key: str
    region: str
    service: str
    algorithm: str = "AWS4-HMAC-SHA256"
    request_type: str = "aws4_request"
    header_prefix: str = "x-amz"
    signing_key_prefix: str = "AWS4"
    session_token: str | None = None

    def __post_init__(self) -> None:
        if not self.access_key_id:
            raise ValueError("object storage access key id is required")
        if not self.secret_access_key:
            raise ValueError("object storage secret access key is required")

    def sign(
        self,
        *,
        method: str,
        url: str,
        payload: bytes,
        headers: dict[str, str],
        now: datetime | None = None,
    ) -> dict[str, str]:
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
        datestamp = timestamp.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload).hexdigest()
        parsed = urlsplit(url)
        host = parsed.netloc.lower()

        signed_headers: dict[str, str] = {
            "host": host,
            f"{self.header_prefix}-content-sha256": payload_hash,
            f"{self.header_prefix}-date": amz_date,
        }
        if self.session_token:
            signed_headers[f"{self.header_prefix}-security-token"] = self.session_token

        canonical_headers = "".join(
            f"{name}:{value.strip()}\n" for name, value in sorted(signed_headers.items())
        )
        signed_header_names = ";".join(sorted(signed_headers))
        canonical_request = "\n".join(
            [
                method.upper(),
                quote(parsed.path or "/", safe="/~"),
                canonical_query(parsed.query),
                canonical_headers,
                signed_header_names,
                payload_hash,
            ]
        )
        credential_scope = (
            f"{datestamp}/{self.region}/{self.service}/{self.request_type}"
        )
        string_to_sign = "\n".join(
            [
                self.algorithm,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        date_key = hmac_sha256((self.signing_key_prefix + self.secret_access_key).encode(), datestamp)
        region_key = hmac_sha256(date_key, self.region)
        service_key = hmac_sha256(region_key, self.service)
        signing_key = hmac_sha256(service_key, self.request_type)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        output = dict(headers)
        output["Host"] = host
        output[f"{self.header_prefix.title()}-Content-Sha256"] = payload_hash
        output[f"{self.header_prefix.title()}-Date"] = amz_date
        if self.session_token:
            output[f"{self.header_prefix.title()}-Security-Token"] = self.session_token
        output["Authorization"] = (
            f"{self.algorithm} "
            f"Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_header_names}, "
            f"Signature={signature}"
        )
        return output


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    endpoint_url: str
    region: str | None = None
    service: str | None = None
    auth: SigV4Auth | None = None
    notes: tuple[str, ...] = ()


def auth_for_provider(
    *,
    provider: str,
    access_key_id: str | None,
    secret_access_key: str | None,
    region: str,
    session_token: str | None,
) -> SigV4Auth | None:
    if not access_key_id and not secret_access_key and not session_token:
        return None
    if not access_key_id:
        raise ValueError("object storage access key id is required")
    if not secret_access_key:
        raise ValueError("object storage secret access key is required")
    if provider == GCS_XML_PROVIDER:
        return SigV4Auth(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=region,
            service="storage",
            algorithm="GOOG4-HMAC-SHA256",
            request_type="goog4_request",
            header_prefix="x-goog",
            signing_key_prefix="GOOG4",
            session_token=session_token,
        )
    return SigV4Auth(
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=region,
        service="s3",
        session_token=session_token,
    )


def provider_config(
    provider: str | None,
    *,
    endpoint_url: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    account_id: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> ProviderConfig:
    normalized = normalize_provider(provider)
    if normalized == GENERIC_HTTP_PROVIDER:
        if not endpoint_url:
            raise ValueError("object store URL is required for generic HTTP object storage")
        return ProviderConfig(provider=normalized, endpoint_url=endpoint_url)

    bucket_name = require_bucket(bucket)
    if normalized == S3_PROVIDER:
        resolved_region = region or "us-east-1"
        if endpoint_url:
            resolved_endpoint = append_bucket_path(endpoint_url, bucket_name)
        elif resolved_region == "us-east-1":
            resolved_endpoint = f"https://{bucket_name}.s3.amazonaws.com"
        else:
            resolved_endpoint = f"https://{bucket_name}.s3.{resolved_region}.amazonaws.com"
        auth = auth_for_provider(
            provider=normalized,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=resolved_region,
            session_token=session_token,
        )
        return ProviderConfig(
            provider=normalized,
            endpoint_url=resolved_endpoint,
            region=resolved_region,
            service="s3",
            auth=auth,
            notes=("s3-compatible endpoint override uses path-style bucket addressing",)
            if endpoint_url
            else (),
        )

    if normalized == R2_PROVIDER:
        resolved_region = region or "auto"
        if endpoint_url:
            resolved_endpoint = append_bucket_path(endpoint_url, bucket_name)
        else:
            account = str(account_id or "").strip()
            if not account:
                raise ValueError("Cloudflare R2 account id is required without endpoint override")
            resolved_endpoint = append_bucket_path(
                f"https://{account}.r2.cloudflarestorage.com",
                bucket_name,
            )
        auth = auth_for_provider(
            provider=normalized,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=resolved_region,
            session_token=session_token,
        )
        return ProviderConfig(
            provider=normalized,
            endpoint_url=resolved_endpoint,
            region=resolved_region,
            service="s3",
            auth=auth,
            notes=("Cloudflare R2 uses S3-compatible SigV4 with region auto",),
        )

    resolved_region = region or "auto"
    resolved_endpoint = append_bucket_path(endpoint_url or "https://storage.googleapis.com", bucket_name)
    auth = auth_for_provider(
        provider=normalized,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=resolved_region,
        session_token=session_token,
    )
    return ProviderConfig(
        provider=normalized,
        endpoint_url=resolved_endpoint,
        region=resolved_region,
        service="storage",
        auth=auth,
        notes=("Google Cloud Storage XML API requires interoperability HMAC keys",),
    )
