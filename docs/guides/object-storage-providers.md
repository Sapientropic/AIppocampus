# Object Storage Provider Notes

Status: initial provider-aware object-storage client implemented for encrypted
sync testing and real-provider bring-up.

AIppocampus object storage uses the same sync bundle contract for every
provider. The provider layer only decides endpoint shape and request signing.
Manifest hashes remain the integrity source of truth; provider ETags are not
trusted as cross-provider hashes.

## Supported Provider Modes

| Provider | `--object-provider` | Auth | Endpoint behavior |
| --- | --- | --- | --- |
| Generic HTTP | `generic-http` | optional bearer token | Uses `--object-store-url` exactly. |
| AWS S3 / S3-compatible | `s3` | SigV4 HMAC | Uses virtual-hosted AWS S3 when no endpoint override is provided; endpoint overrides use path-style `/bucket/key`. |
| Cloudflare R2 | `r2` | S3 SigV4 HMAC | Defaults to `https://<account-id>.r2.cloudflarestorage.com/<bucket>`, region `auto`. |
| Google Cloud Storage XML API | `gcs-xml` | HMAC interoperability key | Defaults to `https://storage.googleapis.com/<bucket>` and `GOOG4-HMAC-SHA256`. |

Relevant provider docs:

- AWS S3 SigV4 header signing: <https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html>
- Cloudflare R2 S3 API compatibility: <https://developers.cloudflare.com/r2/api/s3/api/>
- Google Cloud Storage XML API: <https://cloud.google.com/storage/docs/xml-api/overview>
- Google Cloud Storage HMAC keys: <https://cloud.google.com/storage/docs/authentication/hmackeys>
- Google Cloud Storage V4 signatures: <https://cloud.google.com/storage/docs/authentication/signatures>

## Environment

```sh
export AIPPOCAMPUS_OBJECT_PROVIDER="s3" # generic-http, s3, r2, gcs-xml
export AIPPOCAMPUS_OBJECT_STORE_URL="https://s3-compatible.example"
export AIPPOCAMPUS_OBJECT_BUCKET="aippocampus-memory"
export AIPPOCAMPUS_OBJECT_PREFIX="aippocampus/sync"
export AIPPOCAMPUS_OBJECT_REGION="us-east-1"
export AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID="<access key id>"
export AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY="<secret access key>"
export AIPPOCAMPUS_OBJECT_SESSION_TOKEN="<optional session token>"
```

For R2, set `AIPPOCAMPUS_OBJECT_PROVIDER=r2` and
`AIPPOCAMPUS_OBJECT_ACCOUNT_ID=<account id>` instead of a custom endpoint unless
you need to test a local or proxy endpoint.

For GCS, set `AIPPOCAMPUS_OBJECT_PROVIDER=gcs-xml` and use Cloud Storage
interoperability HMAC keys. This does not use the JSON API OAuth flow.

## Real-Provider Smoke

After exporting provider credentials, run the real-provider encrypted smoke:

```sh
python tools/aippocampus/smoke/smoke_real_provider_encrypted_sync.py --json
```

The smoke generates an ephemeral `age` identity, pushes an encrypted bundle,
runs status/repair/pull, then deletes every encrypted object discovered from
the decrypted inner manifest. Cleanup fails if the discovered object count does
not match the encrypted push `object_count`; this catches cases where only the
outer manifest is deleted while ciphertext objects remain.

The JSON output includes `provider_metadata`, a public-safe evidence block with
encrypted object counts, aggregate ciphertext byte sizes, coarse size buckets,
and path-shape counts. It intentionally omits object keys, credentials,
endpoint URLs, and decrypted registry contents. Treat this as provider-visible
metadata leakage evidence for padding/cost discussions; it does not claim that
metadata padding has been evaluated or that traffic-analysis resistance exists.

Use `--keep-objects` only for debugging a temporary test prefix.

Encrypted sync hides synced registry/source contents from the provider, but it
does not hide object counts, object sizes, or upload timing. Current provider
evidence is dated per smoke run; do not generalize one R2-compatible smoke to a
full S3/GCS/cloud-folder matrix, and do not claim metadata padding unless a
focused padding smoke records the cost and leakage tradeoff.

Plaintext migration cleanup uses HTTP `DELETE` for objects listed in the
plaintext sync manifest and deletes the manifest object last. Providers that do
not expose delete permissions can still use migration dry-run and encrypted
push, but old plaintext cleanup must then be performed in the provider console
or lifecycle tooling.

## Provider-Specific Pitfalls

- Signing credentials require HTTPS unless the endpoint is loopback. This keeps
  local test servers usable without permitting real credentials over network
  HTTP.
- R2's S3 region is `auto`; empty and `us-east-1` can alias for compatibility,
  but AIppocampus emits `auto` by default.
- GCS XML uses `x-goog-*` headers and `GOOG4-HMAC-SHA256` when using HMAC keys.
  Do not mix this with bearer-token JSON API assumptions.
- Endpoint overrides use path-style bucket addressing. This avoids DNS and TLS
  wildcard surprises for local MinIO/R2 proxies and dotted bucket names.
- Provider ETags are intentionally ignored. Multipart uploads, encryption, and
  provider differences make ETag semantics unreliable as a portable integrity
  check.
- Use a new object prefix for the first encrypted push. Encrypted push refuses
  a prefix that already exposes the plaintext sync manifest, but it cannot prove
  that a cloud bucket has no unrelated old plaintext copies elsewhere.
- Clock skew can break signed requests. Keep devices close to real UTC before
  debugging object-storage auth failures.
