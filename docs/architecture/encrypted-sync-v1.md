# Encrypted Sync V1

Role: current contract.

This document defines the first encrypted sync design for AIppocampus. It is a
design contract, not an implementation note. The goal is to make multi-device
sync safe before HTTP object storage or cloud-synced folders become normal use.

## Conclusion

Encrypted sync v1 should be client-side, end-to-end encryption over the current
sync bundle contract.

The local folder, object store, or future service is only a blob transport. It
must not receive plaintext clean source, registry rows, sidecars, raw rollouts,
or usable encryption keys. Raw rollouts remain excluded by default; if a user
opts into raw rollout sync, encrypted sync is mandatory.

## Goals

- Preserve the current local-first privacy model while enabling multi-device
  sync through untrusted storage.
- Reuse the existing `aippocampus_runtime.sync.bundle` and `aippocampus_runtime.sync.object_storage.cli` data model
  instead of inventing a parallel sync system.
- Encrypt clean source, registry rows, semantic sidecars, working memory,
  cognitive-map artifacts, and opt-in raw rollouts before they leave a device.
- Detect tampering, missing objects, wrong keys, stale manifests, and path
  traversal before importing synced data.
- Keep the first implementation understandable enough to test with local
  folders, local HTTP object storage, and two real devices.

## Non-Goals

- No server-side plaintext search in v1.
- No account service, hosted key escrow, or cloud-based recovery service.
- No silent hook installation, external-model enablement, or raw rollout sync.
- No custom cryptographic primitive design.
- No promise that object sizes, update timing, or total object counts are fully
  hidden in v1.
- No secure-delete guarantee for temporary plaintext on modern SSDs. V1 should
  minimize plaintext lifetime and location, but not claim forensic erasure.

## Threat Model

V1 protects against:

- A cloud folder provider, object-storage provider, or network observer reading
  synced AIppocampus memory content.
- A storage provider modifying or dropping objects without detection.
- A device pulling a bundle encrypted for another vault or schema version.
- Accidental publication of sync folders that contain private memory artifacts.

V1 does not fully protect against:

- A compromised local device after the user unlocks AIppocampus.
- Malware that can read the local keychain or the live process memory.
- Traffic analysis from object size, upload cadence, or object count.
- A provider replaying an older but valid encrypted snapshot unless the client
  has local state to compare manifest revisions.

## Data Classification

All synced AIppocampus artifacts are private by default.

| Class | Examples | V1 policy |
| --- | --- | --- |
| Clean source | `messages.jsonl`, `turns.jsonl`, `events.jsonl`, clean-source manifests | Always encrypt |
| Registry | `threads.json`, `threads.md`, generated-artifact locators | Always encrypt |
| Sidecars | semantic triggers, working memory, cognitive map, concept graph | Always encrypt |
| Indexes | SQLite/source indexes, graph metadata | Always encrypt if synced |
| Raw rollout | original Codex Desktop JSONL audit source | Excluded unless explicit; encrypt when included |
| Public examples | synthetic demo bundle | May remain plaintext only when intentionally public |

## Recommended Shape

V1 should use direct `age` recipient encryption around the existing bundle
objects.

1. Generate or import one local `age` identity per trusted device.
2. Encrypt every synced bundle file and the inner manifest for the configured
   recipients.
3. Publish encrypted objects first and the outer encrypted-sync manifest last.
4. Decrypt into a temporary local plaintext bundle only during pull or repair.
5. Import through the existing sync validation and conflict-preserving pull
   path.

This is intentionally simpler than a true application-level envelope format.
Recipient changes in v1 require repushing or re-encrypting the object set.
That tradeoff is acceptable for the first encrypted sync release because it
avoids custom nonce, KDF, and AEAD binding logic. A later object-level format can
introduce a vault root key, domain keys, and recipient-wrapped keyrings after
the v1 product path is proven.

## Primitive Choice

V1 should prefer mature tools and formats:

- For v1, use direct `age` recipients. It is a small file-encryption format with
  native multi-recipient support and is a good fit for local-folder and
  object-storage bundle exchange.
- V1 should not implement application-layer nonce management, HKDF trees, or
  custom AEAD wrappers. The inner manifest binding described below is the
  application-level safety layer.
- For a later library-level object format, use libsodium secretstream or
  XChaCha20-Poly1305 AEAD. XChaCha reduces nonce-management risk for many small
  local objects.
- AES-GCM is acceptable only through a well-reviewed library and only when nonce
  uniqueness is enforced. AIppocampus should not hand-roll AES-GCM nonce
  management.
- If a later fallback encrypts private key material with an AIppocampus-managed
  passphrase, it should use Argon2id with stored parameters and salts. V1 should
  not ship passphrase-only recovery.

References:

- `age`: <https://github.com/FiloSottile/age>
- libsodium secretstream:
  <https://libsodium.gitbook.io/doc/secret-key_cryptography/secretstream>
- libsodium AEAD XChaCha20-Poly1305:
  <https://doc.libsodium.org/secret-key_cryptography/aead/chacha20-poly1305>
- Python `cryptography` AEAD APIs:
  <https://cryptography.io/en/latest/hazmat/primitives/aead/>
- OWASP password storage guidance:
  <https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>

## Age Dependency And Preflight

V1 should start by shelling out to the external `age` CLI instead of vendoring a
crypto library. That keeps the first implementation close to the documented
file format and avoids application-layer primitive choices.

The command layer must provide a preflight:

- locate `age` through `AIPPOCAMPUS_AGE_BIN` first, then `PATH`
- run `age --version`
- fail with `age_missing` when the binary is absent
- explain that macOS GUI clients may not inherit the user's shell `PATH`
- never pass private identity material through command-line arguments when a
  file descriptor or local identity file is available

Install docs should include platform-specific pointers for Homebrew, Windows
package managers, Linux distro packages, and upstream prebuilt binaries when
encrypted sync is implemented.

## Key Model

V1 has three identities:

- **Vault identity:** a stable random vault id used for sync binding and replay
  checks. V1 does not introduce an application-level vault root key.
- **Device identity:** each device has a local encryption recipient identity.
- **Recovery identity:** an optional offline recovery recipient.

Suggested storage:

- macOS stores local private recipient keys in Keychain where possible. The
  service/account names should be stable, documented, and scoped to
  AIppocampus encrypted sync.
- Other platforms use the nearest OS credential store when available. If no
  supported credential store exists, the command should fail closed unless the
  user explicitly chooses a local encrypted-key fallback.
- CLI fallback stores encrypted private key material in `$CODEX_HOME` only after
  explicit user confirmation, with owner-only file permissions.
- Private keys, recovery kits, and unwrapped vault keys must never be written
  into the sync directory, object-storage prefix, exported demo bundle, or repo
  docs.
- Status output may report that a local key is available, but must not print
  private key material, recovery text, or full secret-bearing file contents.

Device enrollment should support:

- Local recipient file import for early CLI users.
- QR code or one-time enrollment phrase later.
- Explicit device names shown in status output.
- Revocation by removing a recipient from future manifests. In v1, existing
  ciphertext remains readable by a device that already has a matching private
  key until the bundle is re-encrypted for the new recipient set.

Recovery must be explicit. The product must choose between:

- No recovery: losing all trusted devices loses encrypted sync data.
- Recovery kit: printable or storable recovery recipient.
- Passphrase recovery: deferred until unlock UX, rate limits, and parameter
  migration are designed.

V1 should support no-recovery plus optional offline recovery recipient first.
Losing all trusted device identities and recovery identities means losing access
to encrypted sync data.

The current CLI models this by storing trusted recipients with a role:
`device` for normal enrolled devices and `recovery` for an offline recovery
recipient. Both roles are public recipients only. The private device identity is
currently a local registry-state file with owner-only permissions as a
best-effort fallback; OS credential-store integration remains a later hardening
step and must not be implied by release claims until implemented and tested.

## Sync Format

V1 should add an encrypted sync schema alongside the existing plaintext schema:

```text
encrypted-sync/
  aippocampus-encrypted-sync-manifest.json
  recipients/
    <recipient-id>.json
  objects/
    <object-id>.age
```

The top-level manifest may stay minimally plaintext so clients can decide
whether they can attempt decryption. It is routing metadata, not trusted
security state, and should expose as little stable metadata as possible:

```json
{
  "kind": "aippocampus_encrypted_sync_bundle",
  "schema_version": 1,
  "encryption": {
    "format": "age",
    "manifest_object": "objects/<object-id>.age"
  }
}
```

The outer manifest must not include thread names, logical file names, local
paths, prompt text, vault id hash, manifest revision, recipient count, or update
timestamps. Those values are stable correlation handles and belong in the
encrypted inner manifest when needed.

The encrypted inner manifest is the only trusted manifest. It contains the
existing sync manifest fields plus:

- encrypted schema version
- vault id hash
- source device id
- manifest revision
- key epoch
- recipient set hash
- encrypted manifest object id
- outer manifest routing fields copied for comparison
- manifest hash, computed from a canonical inner-manifest representation
- parent manifest hash, required for every non-genesis revision
- plaintext sync schema version being wrapped
- object list with object ids, logical paths, object type, manifest hash,
  manifest revision, ciphertext hash, ciphertext size, plaintext hash, and
  plaintext size
- raw rollout inclusion flag

V1 should not place thread names, local workspace paths, prompt text, or logical
file names in plaintext object keys. V1 should use random object ids for every
push. HMAC-derived ids are a later option only after an application-level vault
secret exists.

Inner object records should be explicit enough to test:

```json
{
  "object_id": "random-base64url",
  "object_path": "objects/random-base64url.age",
  "logical_path": "registry/threads/thread-key/clean-source/messages.jsonl",
  "object_type": "clean_source_messages",
  "manifest_hash": "hex",
  "manifest_revision": 12,
  "ciphertext_sha256": "hex",
  "ciphertext_size": 1234,
  "plaintext_sha256": "hex",
  "plaintext_size": 987
}
```

The encrypted inner manifest is the authoritative binding between logical files
and encrypted objects. A decrypted object is accepted only when the object id,
object type, ciphertext hash, plaintext hash, vault id hash, key epoch, recipient
set hash, and manifest revision match the inner manifest. After decrypting the
inner manifest, the client compares its copied routing fields with the plaintext
outer manifest and rejects mismatches. This binding is required because a
generic file encryption wrapper does not by itself know AIppocampus logical
paths or sync semantics.

## Manifest Commit And Anti-Replay

Manifest-last writes reduce the chance that readers see half-written data, but
they are not a complete commit protocol. Encrypted sync needs local accepted-head
state.

Each client should store, per vault and backend target:

- accepted manifest hash
- accepted manifest revision
- accepted key epoch
- accepted parent hash
- last-seen outer manifest object id

The state can live under the local AIppocampus registry because it is local
sync bookkeeping, not shared sync content.

Rules:

- The first accepted manifest for a vault may be a genesis manifest with no
  parent. Every later manifest must include `parent_manifest_hash`.
- If the incoming manifest hash equals the local accepted head, pull is a no-op.
- If the incoming parent hash equals the local accepted head, pull may proceed
  after object validation.
- If the incoming revision is older than or equal to the local high-water mark
  and the hash differs, reject it as `stale_manifest`.
- If the incoming parent hash differs from the local accepted head, reject it as
  `divergent_head` or place it in a future conflict flow. Do not partially import
  plaintext files.
- Revision numbers are hints for humans and coarse ordering. The manifest hash
  and parent hash are the authority.

For local folders, the outer manifest should be written through a temporary file
and atomic replace. For object storage, encrypted objects and the encrypted
inner manifest object should be written under revision/object-specific keys,
then the outer pointer manifest should be written last. V1 cannot assume object
stores provide compare-and-swap; stale-parent and divergent-head checks are the
safety net for concurrent writers.

## Push Flow

1. Build a normal plaintext sync bundle in a temporary directory.
2. Validate the plaintext bundle with the existing repair logic.
3. Encrypt each bundle file into an encrypted object.
4. Build the encrypted inner manifest from the plaintext manifest.
5. Encrypt the inner manifest.
6. Write encrypted objects first, then the encrypted inner manifest object, then
   the outer encrypted-sync pointer manifest last.
7. Delete temporary plaintext bundle files.

For object storage, `aippocampus_runtime.sync.object_storage.cli` should upload encrypted objects and
write the outer manifest last, preserving the existing "manifest last" behavior
while relying on parent-hash validation for concurrent writers.

## Pull Flow

1. Read the outer manifest.
2. Confirm the client has a matching recipient or recovery path.
3. Decrypt and authenticate the inner manifest.
4. Reject unknown schema versions, unsafe logical paths, missing objects, hash
   mismatches, wrong vault ids, or stale revisions that conflict with local
   state.
5. Decrypt objects into a temporary plaintext sync bundle.
6. Run existing repair validation on the temporary plaintext bundle.
7. Import through the current pull path so conflict preservation remains
   unchanged.
8. Delete temporary plaintext files.

No decrypted file should be written into the shared sync folder or object-store
staging prefix. Temporary plaintext should live under a local temporary
directory with owner-only permissions, equivalent to `0700` on POSIX systems,
and should be cleaned up on normal and error exits. Status output and logs must
not print decrypted temporary file contents or secret-bearing paths. Deletion is
best-effort cleanup, not a forensic secure-delete promise.

## Status And Repair

`status` and `repair` should have three depths:

- **Outer-only:** validate outer manifest shape and encrypted inner manifest
  object presence. This does not decrypt and cannot report raw rollout inclusion,
  object count, thread names, or revision.
- **Inner-manifest decrypt:** decrypt only the encrypted inner manifest. This can
  report recipient match, raw rollout inclusion, manifest hash, replay status,
  and object count without decrypting all file objects.
- **Full decrypt repair:** decrypt every object into a temporary local bundle,
  verify ciphertext and plaintext hashes, then run current plaintext repair.

`status` should default to outer-only unless the caller opts into decrypting
status or the operation needs a pull preflight. `repair` should default to full
decrypt repair, with `--no-decrypt` available for outer-only checks.

Structured status should report:

- `encrypted: true`
- outer manifest exists or missing
- encrypted sync schema version
- recipient match: yes/no/unknown
- raw rollout included: yes/no/unknown
- replay status: current/stale/divergent/unknown
- key material location: local-only, never in sync directory

Wrong-key failures should be structured and non-noisy. They are not corruption.

## Release-Oriented Repair Boundary

Release notes and readiness docs should keep sync evidence in separate buckets:

- **Local simulation:** `smoke_cross_device_sync.py` models two device registries
  on one machine. It proves portable bundle locators, target-registry path
  repair, conflict preservation, cross-OS-shaped source path cleanup, and raw
  rollout opt-in boundaries. It does not prove a real second device.
- **Alternate runtime:** `smoke_alternate_runtime_sync.py` runs the same bundle
  through Docker and/or WSL when available. It proves runtime-local repair, not
  a managed cloud provider.
- **Physical second machine:** issue
  [#36](https://github.com/Sapientropic/AIppocampus/issues/36) records the
  Windows-to-MacBook smoke boundary. It proves one real second-device path, not
  a full client matrix.
- **Managed provider:** issue
  [#38](https://github.com/Sapientropic/AIppocampus/issues/38) records the
  Cloudflare R2 encrypted object-storage smoke boundary. It proves one managed
  R2 path, not every S3-compatible, GCS, cloud-folder, or enterprise storage
  provider.

Do not copy raw smoke JSON into public docs. Summaries may name the command,
the exercised surface, and aggregate pass/fail claims, but must omit local
paths, bucket names, credentials, raw rollouts, and registry exports.

For release-oriented repair behavior, keep these expectations stable:

- Run `status` before `repair` or `pull` when choosing a sync source.
- Treat `repair` failures as stop signs. Missing objects, manifest hash
  mismatches, unsafe paths, wrong recipient keys, and stale or divergent
  manifests must be resolved before import.
- Preserve local target files on conflict. Incoming conflicting files belong
  under `.sync-conflicts/` inside the target registry until a human or explicit
  repair flow decides what should win.
- Repair generated-artifact locators to the target registry on pull; never
  preserve source-device absolute paths as active target paths.
- Keep raw rollout sync opt-in. Plaintext sync excludes raw rollouts; raw
  rollout transfer requires explicit inclusion and, for normal product paths,
  encryption.
- Retry only the transport step that failed. A retry should not silently delete
  old plaintext sync data, local registries, conflict files, or uploaded
  encrypted objects outside the run-specific cleanup scope.

## UX And Commands

Initial CLI shape:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle push \
  --sync-dir <folder> \
  --encrypt \
  --recipient <age-recipient>

PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle pull \
  --sync-dir <folder> \
  --require-encrypted
```

Object storage should use the same flags:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.object_storage.cli push \
  --object-store-url <url> \
  --encrypt \
  --recipient <age-recipient>
```

Later UX can add:

- `aippocampus_keygen`
- `aippocampus_device_add`
- `aippocampus_device_list`
- `aippocampus_key_rotate`
- `sync status --require-encrypted`

Do not make encryption implicit based only on an environment variable. The user
should see in command output whether a push produced plaintext or encrypted
sync data.

The first implementation should use explicit mode flags:

- `push --encrypt`: write encrypted sync output.
- `push --recipient <age-recipient>`: add one recipient; repeatable.
- `push --recipient-file <path>`: read recipients from a local file.
- `pull --require-encrypted`: refuse plaintext sync input.
- `status --require-encrypted`: report plaintext input as refused, not merely
  unsupported.
- `repair --require-encrypted`: require encrypted input before decrypting and
  validating.
- `repair --no-decrypt`: verify only the outer encrypted manifest and encrypted
  inner manifest object presence.
- `--identity-file <path>`: local private identity for decrypting when OS key
  store lookup is unavailable.

The command layer must reject `AGE-SECRET-KEY...` values passed to
`--recipient`; that is private identity material, not a public recipient.
JSON output should include stable error codes and next-step messages for:
`age_missing`, `identity_missing`, `wrong_key`, `mixed_sync_dir`,
`mixed_object_prefix`, `plaintext_refused`, `raw_requires_encryption`,
`recipient_secret_rejected`, `stale_manifest`, `divergent_head`, and
`unsupported_encrypted_schema`.

## Restore And Recovery

The first recovery path should be plain and strict:

1. Generate or import a local identity on the new device.
2. Add that device's public recipient to encrypted sync from an already trusted
   device.
3. Push a fresh encrypted bundle for the expanded recipient set.
4. On the new device, run `status --require-encrypted` and confirm
   `recipient_match: yes`.
5. Pull only after the recipient match succeeds.

If the user has no remaining trusted device identity and no offline recovery
recipient, encrypted sync data is unrecoverable. `wrong_key` should say that the
client lacks a matching identity; it should not describe the bundle as corrupt.

Revocation is a future-access boundary, not retroactive erasure. After
`key revoke`, status should carry `reencryption_required` until a fresh
encrypted bundle is pushed for the remaining trusted recipients. Commands must
reject future pushes that explicitly include a revoked recipient, but older
ciphertexts remain readable by any device that already had the matching private
identity.

## Raw Rollout Policy

Raw rollout sync remains explicit:

- `--include-raw` is still required.
- `--include-raw` requires `--encrypt` for the normal local-folder and
  object-storage sync paths. There should be no normal product path for
  plaintext raw rollout sync.
- Command output should show `raw_rollout_included`.
- Status should avoid exposing raw rollout object names before decrypting.

This is a policy boundary, not only a technical flag.

## Compatibility

V1 should preserve plaintext sync for local trusted folders and public synthetic
demos, but object-storage docs should recommend encrypted sync once available.

Plaintext and encrypted sync data must not silently coexist in the same sync
directory or object prefix. Encrypted push should fail with a structured
`mixed_sync_dir` or `mixed_object_prefix` error if it detects an existing
plaintext manifest or managed plaintext object set. The safe default is a new
directory or new object prefix. A future `migrate-to-encrypted --dry-run` flow
can inventory old plaintext data and then perform explicit cleanup, but a normal
encrypted push must not imply that old plaintext copies were removed.

Clients should reject:

- encrypted bundles with unsupported schema versions
- plaintext pulls when the command explicitly requested encrypted sync
- raw rollout object imports from any unencrypted sync backend
- manifests whose logical paths would escape the target registry

## Test Matrix

Minimum tests before calling v1 ready:

- Encrypted local-folder push/pull round trip.
- Encrypted HTTP object-storage push/pull round trip.
- Pull with wrong recipient reports a structured wrong-key error.
- Encrypted push refuses to run in a sync directory or object prefix that still
  contains plaintext sync data.
- Tampered encrypted object is detected before import.
- Missing object is detected before import.
- Complete old-snapshot replay is rejected after a newer manifest was accepted.
- Parent mismatch or divergent heads are rejected before import.
- Outer manifest path traversal is rejected.
- Outer manifest leakage golden test confirms it contains no thread name,
  logical filename, local path, timestamp, revision, vault id hash, or recipient
  count.
- Inner manifest path traversal is rejected after decrypt.
- Object swap, old-object-with-new-manifest, and logical-path/object-id mismatch
  cases fail before import.
- Plaintext temporary files are not left in the sync directory.
- Raw rollout remains excluded by default.
- `--include-raw` plus encryption imports raw rollout only when explicit.
- `--include-raw` without encryption is rejected for local-folder and object
  storage sync.
- Outer manifest tampering is rejected after decrypting and comparing the inner
  manifest's copied routing fields.
- A decryptable bundle for another accepted vault is rejected unless the user
  explicitly enrolls or switches to that vault.
- Conflict preservation still writes `.sync-conflicts/`.
- macOS Keychain path is optional in tests and skipped when unavailable.
- Local stale-manifest state detects replay of an older manifest after a newer
  revision was already seen.
- Recipient private keys and recovery material are never copied into sync
  output.
- `--recipient` rejects private `AGE-SECRET-KEY...` identity material.
- Wrong-key, tamper, missing-object, and path-traversal failures leave no
  plaintext in the sync directory or object prefix.

## Implementation Phases

1. **Design and docs:** land this document, link it from docs index, and mark
   encrypted sync as the next Stage 3 hardening slice.
2. **Bundle-level encryption:** add encrypted push/pull/status/repair around
   `aippocampus_runtime.sync.bundle` using direct `age` recipient encryption and temporary
   plaintext bundles.
3. **Object-storage reuse:** make `aippocampus_runtime.sync.object_storage.cli` upload the encrypted
   object set without changing the transport model.
4. **Device key UX:** add recipient generation, device listing, and local key
   storage helpers.
5. **Replay and rotation hardening:** add manifest revision tracking, parent
   hashes, re-encryption after recipient changes, and recipient revocation
   tests.
6. **Object-level optimization:** if bundle-level encryption becomes too coarse,
   move from whole-file `age` wrapping to libsodium object encryption while
   preserving the same inner manifest semantics.

## Open Questions

The v1 open questions are now owned by
[`encrypted-sync-v2.md`](encrypted-sync-v2.md). Keep this v1 document as the
implemented contract; do not silently backport v2 claims here before runtime
changes and tests land.

- Plaintext sync remains available for local trusted folders and public
  synthetic demos. Object-storage plaintext becomes an explicit debug/
  compatibility path with warning and opt-in.
- Metadata padding stays deferred beyond the minimal outer-manifest boundary
  until real provider evidence justifies the cost and claim.
- Manifest hashes are integrity binding, not sender authentication. V2 starts
  with a named "trusted recipient can author bundles" model; signing is a
  follow-up before automated multi-writer trust.
