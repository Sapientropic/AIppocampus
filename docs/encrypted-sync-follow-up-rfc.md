# Encrypted Sync Follow-Up RFC

Status: implemented as the device-key and plaintext migration slice after
encrypted-sync-v1 provider bring-up.

## Summary

Encrypted sync v1 now has local-folder, object-storage, real `age`, and
documented Cloudflare R2 readiness evidence. GCS XML HMAC signing support and
smoke history are not part of the current broader provider/client claim
boundary unless they are rerun, dated, and recorded in the readiness ledger.
The next slice should turn the working protocol into a usable multi-device
workflow: device-key UX and explicit plaintext-to-encrypted migration.

## Follow-Up Issue

Title: Add encrypted sync device-key UX and plaintext migration workflow

Problem:

- The encrypted sync protocol works, but users still need to manage `age`
  recipients, identities, and trusted devices manually.
- Plaintext sync prefixes/directories are intentionally rejected by encrypted
  push, but there is no guided migration path that inventories existing
  plaintext data and moves users to a clean encrypted target.
- Without a first-class flow, users can either leak old plaintext objects by
  mistake or lose access by misplacing identity material.

Implemented command shape:

1. Add device-key commands:
   - `key init`: create or register a local device identity.
   - `key recipient`: print the public recipient only.
   - `key list`: show trusted recipients and local identity availability.
   - `key trust`: add a recipient from an already trusted device.
   - `key revoke --dry-run`: report which re-encryption/migration is needed
     before removing a recipient.
2. Add migration commands:
   - `migrate-to-encrypted --dry-run`: inspect a plaintext local folder or
     object prefix, report plaintext manifests/objects, target encrypted prefix,
     estimated object count, and required recipients.
   - `migrate-to-encrypted`: write a new encrypted bundle to a fresh target
     prefix/directory.
   - `cleanup-plaintext --dry-run`: list old plaintext sync objects that would
     be removed only after encrypted repair/pull succeeds.
3. Keep safety defaults:
   - Never copy private identity material into sync output.
   - Never delete plaintext objects as a side effect of encrypted push.
   - Require a successful encrypted repair or pull before offering cleanup.
   - Keep raw rollout sync encrypted-only and explicit.

The concrete CLI entrypoint is `encrypted_sync_admin.py`; see
`docs/install-guide.md` for local-folder and object-storage examples. Cleanup
is scoped to manifest-managed plaintext files/objects, requires an explicit
verified-target acknowledgement after encrypted repair or pull, and does not
claim to erase unrelated provider objects.

Acceptance criteria:

- A second device can be enrolled using only public recipient exchange and an
  already trusted device.
- Wrong-key, missing-key, and revoked-recipient cases return structured errors.
- Migration dry-run reports plaintext exposure without uploading or deleting.
- Migration writes to a fresh encrypted target and refuses mixed plaintext /
  encrypted prefixes by default.
- Plaintext cleanup requires explicit confirmation and reports every object it
  will delete.
- Real-provider smoke remains green for every provider path explicitly claimed
  by the readiness ledger. Broader GCS XML HMAC, S3-compatible, cloud-folder,
  or long-running provider/client soak claims belong to issue #57 and require
  fresh dated evidence before they are claimed.

Non-goals for this follow-up:

- Automatic cloud-account provisioning.
- Social recovery or escrow.
- Transparent background sync daemon.
- Provider-specific lifecycle policies beyond documenting recommended cleanup
  settings.
