# Encrypted Sync V2 Decision Track

This note owns the encrypted sync v2 decisions from GitHub #306. It is a
contract and follow-up planner, not an implementation claim. The v1 runtime
contract in [`encrypted-sync-v1.md`](encrypted-sync-v1.md) remains unchanged
until a v2 implementation lands with tests and dated readiness evidence.

## Scope

V2 decides the recovery, conflict, revocation, key-provider, plaintext/debug,
manifest-authentication, metadata-padding, and partial-migration boundaries
that v1 deliberately left narrow.

V2 must not block #104. A post-migration live provider smoke can still run
against the current encrypted v1 path when a maintainer provides credentials,
an ephemeral prefix or bucket path, and cleanup permission.

## Non-Goals

- No hosted escrow, account service, or social recovery.
- No silent plaintext fallback when `age` or a key provider is unavailable.
- No claim that revoked devices lose access to historical ciphertext until a
  verified re-encryption workflow has rewritten the affected object set.
- No claim that manifest integrity hashes prove sender identity.
- No broad S3-compatible, GCS XML, cloud-folder, or long-duration provider
  support from this design note alone.

## Decision Table

| Area | V2 decision | Tradeoff | Non-goal / cannot-claim |
| --- | --- | --- | --- |
| passphrase recovery | Keep passphrase recovery unsupported for v2. Use an optional offline recovery kit as the explicit recovery UX, backed by a public `recovery` recipient and a private identity that never enters sync output. | Avoids weak unlock UX, rate-limit design, KDF parameter migration, and confusing "password reset" expectations. | No recovery from losing all trusted identities and all recovery-kit identities. |
| offline recovery kit | Support printable/exportable recovery-kit guidance before any passphrase path. Status should distinguish `recovery_recipient_configured`, `recovery_identity_available`, and `recovery_identity_missing`. | Gives users a recoverable path without custom crypto or hosted escrow. | A recovery recipient is not a cloud backup service and does not solve compromised-device revocation. |
| divergent_head | Model sync heads as a small head graph: `device_id`, `head_id`, `parent_heads`, and a per-device `logical_counter`. Single-parent advancement fast-forwards. Concurrent children of the same parent return `divergent_head`, preserve both heads under `.sync-conflicts/`, and require manual or adjudicated resolution. | Avoids pretending local file locks are a distributed object-store lock. | No automatic merge of private source, dream, activation, or strategy rows until provenance-specific conflict rules are implemented. |
| activation rows from conflict | Quarantine only activation, dream, semantic-trigger, and strategy-like rows whose provenance comes from the conflicting head. Keep unrelated local source-backed rows eligible. | Preserves safety without globally demoting all local runtime state after one sync conflict. | Conflict isolation is not source deletion and not distributed locking. |
| future-recipient revocation | Treat revocation as "removed from future recipients" until re-encryption completes. Status must say `historical ciphertext remains decryptable` when old objects were encrypted to the revoked recipient. | Honest security wording beats a comforting but false deletion claim. | No instant revocation, historical erasure, or remote device disablement. |
| required re-encryption | After a recipient change, status and repair should surface `reencryption_required`; pushes that explicitly include revoked recipients should fail. A future re-encryption workflow can clear the warning only after new ciphertext is verified. | Keeps v1 age-recipient simplicity while making the security boundary visible. | Do not report a recipient as fully removed from access before all relevant ciphertext is rewritten. |
| manifest signing | V2 starts with a named `trusted recipient can author bundles` model: a decrypting trusted identity can author an encrypted bundle. This is integrity-bound by inner-manifest hashes but is not sender authentication. Manifest signing becomes a required follow-up before automated multi-writer acceptance or remote-head trust beyond manual review. | Avoids implying that AEAD plus local replay state is a signature. | No sender-authentication claim until signing keys, trust roots, rotation, and tests exist. |
| metadata padding | Keep the outer manifest minimal. Defer padding beyond coarse bucketed object sizes until real provider evidence shows object count or size leakage is a top risk. | Padding can add cost, latency, and confusing partial guarantees. | No traffic-analysis resistance claim for object sizes, object counts, or upload cadence. |
| plaintext debug path | Retain plaintext sync only for local trusted folders, public synthetic demos, and an explicit plaintext debug path. Object-storage plaintext must carry a warning and explicit opt-in; raw rollout transfer remains encrypted-only. | Keeps migration/debug tooling usable without normalizing provider plaintext. | No normal product path for plaintext raw rollouts or silent mixed plaintext/encrypted targets. |
| key-provider | Add a local key-provider contract: `file`, `macos-keychain`, `windows-credential-manager`, and `linux-secret-service`. The active key-provider is reported without secret material. Configured providers fail closed when unavailable, locked, or wrong. | Improves OS-native secret storage while keeping scriptable file identities. | Keychain or credential-store support does not solve historical revocation. |
| vault-id recovery | Treat `vault-id` as a local continuity anchor. Support backup/export warnings and diagnostics for missing or corrupt vault-id, but do not silently regenerate a new vault id as the same vault. | Prevents accidental cross-vault import and makes local-state loss visible. | No automatic continuity recovery from a lost vault id without explicit operator action. |
| partial migration recovery | A failed or interrupted migration leaves plaintext source objects intact and preserves encrypted target objects for inspection. Cleanup is allowed only after dry-run review, verified encrypted repair or pull, and explicit confirmation. | Recovery is slower, but it prevents data loss and false cleanup safety. | No provider-console cleanup claim unless the provider path was actually checked. |

## Threat Model Additions

| Threat | V2 boundary | Required user-facing status |
| --- | --- | --- |
| storage provider | Provider can see object count, sizes, timing, and outer pointer metadata, but not decrypted registry/source contents. | `provider_metadata_leakage_not_fully_padded` when padding is not enabled. |
| network observer | Same metadata boundary as the storage provider unless the transport adds stronger protection. | `transport_metadata_out_of_scope`. |
| compromised object store | Tampering, deletion, replay, and divergent heads must be detected before import. | `repair_failed_stop_before_import`. |
| revoked device | Removed from future recipients only; old ciphertext remains readable until re-encryption. | `removed_from_future_recipients`, `historical_ciphertext_remains_decryptable`, `reencryption_required`. |
| compromised trusted device | A device with a valid private identity can decrypt and author bundles under the trusted-recipient model. | `trusted_device_compromise_out_of_scope_for_age_only`. |
| lost local identity | Pull fails with `wrong_key` or `identity_missing`; recovery works only when a recovery kit identity exists. | `no_matching_identity`, `recovery_identity_required`. |
| lost vault id | Local continuity cannot be proven; the operator must restore a backup or explicitly enroll/switch vaults. | `vault_id_missing_or_mismatch`. |
| stale/replayed manifest | Reject older or non-parent heads after a newer accepted head exists. | `stale_manifest` or `divergent_head`. |
| partial migration | Keep source plaintext and partially written encrypted target until verified recovery or explicit cleanup. | `partial_migration_preserved`, `manual_recovery_required`. |

## Verification And Smoke Plan

These are required tests or smoke plans before claiming the corresponding v2
behavior. They are not claimed by this design note.

| Plan | Required evidence |
| --- | --- |
| revoked-recipient status | Unit test showing `key revoke --dry-run` and status use `removed from future recipients` language and expose `reencryption_required`. |
| required re-encryption | Local encrypted-sync smoke where a recipient is revoked, old ciphertext remains flagged, then a re-encrypted bundle clears only the future-recipient warning. |
| wrong-key pull | Existing wrong-key pull tests remain required and should also assert the error says missing identity, not corruption. |
| stale/replayed manifest/head | Deterministic local-folder test for stale manifest, divergent head, and two-device concurrent children of the same parent head. |
| missing/corrupt vault-id | Unit test for missing, corrupt, and mismatched vault-id diagnostics before pull or repair. |
| age_missing | CLI/preflight test proving no plaintext fallback when the external `age` binary is unavailable. |
| partial migration recovery | Object-storage and local-folder migration smokes for encrypted push succeeds but verification fails, target partially written, cleanup attempted before verified pull, and mixed prefixes. |
| key-provider missing | Key-provider unit test showing configured `macos-keychain`, `windows-credential-manager`, or `linux-secret-service` providers fail closed when unavailable. |
| locked provider | Platform-gated smoke or fixture adapter showing locked OS store status is reported without falling back to file identities. |
| wrong identity | Key-provider and file-provider tests for wrong identity returning `wrong_key` without printing secret material. |
| export/backup warnings | CLI snapshot test that recovery kit, file identity, OS key-provider, and vault-id backup warnings are present and do not include private key material. |
| manifest signing | Future test for signed head metadata before any automated multi-writer trust claim. |
| metadata padding | Optional provider smoke comparing unpadded and padded object-size buckets before claiming traffic-analysis reduction. |

## Current Implementation Notes

As of 2026-06-05, the plaintext-to-encrypted migration helpers have a first
deterministic recovery diagnostic slice for local folders and the HTTP object
storage fixture. If an encrypted target write fails after leaving partial
encrypted artifacts, the migration result preserves the original failure,
adds `partial_migration_preserved`, and reports `migration_recovery` with
`plaintext_source_preserved=true`, `target_preserved_for_inspection=true`,
`cleanup_allowed=false`, and `manual_recovery_required=true`. This proves the
local deterministic contract only; it does not prove live-provider interruption
semantics or provider-console cleanup.

As of 2026-06-05, encrypted key administration also has a first key-provider
contract/status slice. The implemented provider is `file`. The reserved
provider names `macos-keychain`, `windows-credential-manager`, and
`linux-secret-service` can be configured and reported, but until real adapters
land they return `key_provider_unavailable`, `fallback_attempted=false`, and
`fallback_to_file_identity=false`. This is a fail-closed diagnostic contract,
not evidence that OS credential stores are integrated or unlocked. Public CLI
JSON may report these allowlisted provider enum values, including
`linux-secret-service`, but still omits identity paths, private keys, and
provider secret material.

## Provider Metadata Evidence

The dated #104 Cloudflare R2-compatible re-smoke in
[`public-readiness-verification.md`](../evidence/readiness/public-readiness-verification.md#2026-06-04-issue-104-post-migration-r2-provider-re-smoke)
is the current provider observation for this track. It verified encrypted
push/status/repair/pull, post-migration plaintext-to-encrypted flow, raw-rollout
exclusion, and cleanup of the uploaded test objects for one R2-compatible path.
The smoke also exposed the practical metadata boundary: operators and the
provider path can observe object counts and object sizes for the encrypted and
plaintext test prefixes even though synced registry/source contents stay
encrypted.

As of 2026-06-05, the real-provider encrypted sync smoke also emits a
`provider_metadata` evidence block with aggregate ciphertext byte sizes, coarse
size buckets, and path-shape counts. This makes future provider runs usable for
padding/cost review without publishing object keys, credentials, endpoint URLs,
or decrypted registry contents. The block is evidence input, not a padding
implementation claim.

Padding decision: keep metadata padding deferred. The current evidence does not
show that coarse object-size or object-count padding is worth the added cost,
latency, and partial-guarantee confusion. AIppocampus can claim encrypted
contents for the dated R2-compatible path, but it cannot claim traffic-analysis
resistance for object sizes, object counts, upload cadence, or unrelated
provider prefixes. Revisit padding only after a focused provider smoke records
unpadded versus padded bucket costs and a concrete user risk that outweighs the
operational cost.

## Follow-Up Implementation Issues

Split implementation only after this contract is accepted. Suggested child
issues:

- Implement head graph and `divergent_head` preservation for encrypted sync.
- Add provenance-scoped quarantine for activation rows from conflicting heads.
- Add revocation status wording and re-encryption-required diagnostics.
- Add the key-provider abstraction with `file`, `macos-keychain`,
  `windows-credential-manager`, and `linux-secret-service` providers.
- Add recovery-kit and vault-id backup diagnostics without passphrase recovery.
- Add manifest signing design and tests before multi-writer trust.
- Add partial migration recovery smokes for local-folder and object-storage
  paths.
- Evaluate metadata padding only after real provider evidence shows the cost
  and leakage tradeoff.

## Claim Boundary

Can claim after this note lands:

- #306 has a canonical encrypted sync v2 decision track.
- The design names the tradeoffs, non-goals, threat-model additions, and smoke
  plans for recovery, conflict, revocation, key providers, plaintext/debug
  compatibility, manifest signing, metadata padding, and migration recovery.

Cannot claim from this note alone:

- v2 runtime behavior is implemented.
- historical ciphertext access is revoked.
- sender authentication exists.
- Keychain or Credential Manager integration works.
- real-provider post-migration sync has passed.
