# Community Channel Launch Criteria

Checked date: 2026-06-02.

This page defines when AIppocampus is ready for a public community channel and
which channel should open first. It is a launch gate, not a channel
announcement.

## Current Decision

Do not open a Discord or Slack yet.

Use GitHub Discussions as the first general community surface when the launch
gates below are met. Discussions are already enabled on the repository, and the
current categories are the default GitHub set: Announcements, General, Ideas,
Polls, Q&A, and Show and tell. The dedicated Evidence & Field Reports category
still needs maintainer setup; until then, field reports use Show and tell with
the `[Field Report]` prefix as documented in
[`../../evidence/community-field-reports.md`](../../evidence/community-field-reports.md).

This choice keeps community work close to issues, PRs, source links, moderation
history, and the project's existing private-data boundary. Discord or Slack can
be reconsidered after the first public release and after a maintainer can name a
real-time moderation budget.

## Launch Gates

All P0 gates must pass before README or release notes link a general community
channel. A maintainer may waive a gate only by recording the waiver, reason,
date, and follow-up issue.

| Gate | Priority | Status now | Owner |
| --- | --- | --- | --- |
| Quick Start and 10-minute public path pass from a fresh clone. | P0 | Required before launch. | `README.md`, `docs/guides/ten-minute-public-path.md`, release checklist. |
| `SECURITY.md`, `CODE_OF_CONDUCT.md`, and `CONTRIBUTING.md` are present and linked from the channel starter post. | P0 | Present; public launch pass must verify the links. | Repository root docs. |
| First release tag or explicit pre-release launch decision exists. | P0 | Not yet claimed. | `docs/guides/setup/release-checklist.md`. |
| Public privacy scan and release checks are current for the launch commit. | P0 | Must be rerun before launch. | `docs/guides/community/privacy-security-checklist.md`. |
| Security reports have a private route and are excluded from community chat. | P0 | Defined in `SECURITY.md`; pin in channel rules before launch. | Maintainer. |
| Discussion categories and starter posts exist for Q&A, ideas, and field reports. | P0 | Default categories exist; dedicated field-report category is pending. | Maintainer. |
| Maintainer response budget is named. | P0 | Pending. Suggested starting ceiling: two scheduled review windows per week and no real-time support promise. | Maintainer. |
| Channel rules state that chat is not canonical project truth. | P0 | Pending starter post. | Maintainer. |
| Community field reports remain separate from official evidence until curated. | P2 | Defined in `docs/evidence/community-field-reports.md`. | Evidence docs. |
| Moderation and escalation rules are copied into the channel starter post. | P2 | Pending. | Maintainer. |

## Channel Matrix

| Channel | Decision | Best use | Privacy / permission boundary | Failure mode |
| --- | --- | --- | --- | --- |
| GitHub Discussions | Chosen first channel once gates pass. | Q&A, ideas, field reports, early adopter notes, broad design discussion. | Public by default; no raw rollouts, registry exports, local paths, credentials, or private conversation text. | Discussions can become stale pseudo-docs; link back to canonical docs/issues when a decision matters. |
| GitHub Issues | Keep as implementation tracker. | Bugs, focused feature slices, verified gaps, planned work. | Same public-data rules as Discussions; private evidence should be described by shape or turned into a sanitized fixture. | Issues can become planning noise if every idea is filed before triage. |
| Private security reporting | Required security route. | Vulnerabilities, secret exposure, private-memory leakage, unsafe sync/plugin behavior. | Do not use public Discussions, issues, Discord, or Slack for secrets or private memory artifacts. | Public reports can leak exactly the sensitive material the report is about. |
| Discord | Not now. Reconsider after release and maintainer budget. | Real-time community presence, office hours, informal support. | Requires active moderation, anti-spam handling, private-data reminders, and clear no-SLA language. | Fragments project truth and creates an implied real-time support promise. |
| Slack | Not now. Reconsider only for a specific partner/community need. | Focused cohort or contributor workspace. | Invitation and retention settings must be explicit; not a safe default for open-source support. | Private-by-feel chat can still collect sensitive memory data and become unauditable. |
| Email / maintainer profile contact | Fallback only. | Private reach-out when GitHub private vulnerability reporting is unavailable. | Do not publish private memory bundles unless explicitly requested through a safe route. | Hard to triage publicly and easy to lose project context. |

## Moderation And Privacy Policy

Community participation follows [`../../../CODE_OF_CONDUCT.md`](../../../CODE_OF_CONDUCT.md).
Maintainers may edit or remove posts, close threads, restrict participation, or
block contributors when needed to protect people, private data, and project
truth.

Do not post:

- API keys, bearer tokens, cookies, connection strings, SSH keys, age private
  identities, or recovery material;
- raw Codex rollouts, registry exports, sync bundles, vault exports, clean-source
  bundles, or `.aippocampus/` output;
- local absolute paths that identify a private machine, user, client, or
  organization;
- screenshots or logs with private conversation text unless they are carefully
  redacted and the remaining material is safe to publish;
- urgent security reports that belong in the private security route.

If a bug needs private evidence, describe the evidence shape and provide a
synthetic fixture, hash-only trace, or redacted minimal reproduction. If a
community report changes what the project can honestly claim, promote it
through the benchmark evidence map, readiness snapshot, or dated verification
ledger rather than treating the Discussion as the source of truth.

## Starter Post Checklist

Before linking the channel publicly, pin a starter post that includes:

- what belongs in Discussions versus issues, PRs, and private security reports;
- the private-data redaction list above;
- the no-SLA maintainer response budget;
- links to `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, `docs/evidence/community-field-reports.md`, and
  `docs/evidence/benchmark-evidence-map.md`;
- a statement that project decisions should be reflected back into issues,
  PRs, or docs when they become durable.

## README Link Policy

Do not add a general community-channel link to `README.md` until the chosen
channel is live, pinned, moderated, and covered by the launch gates above. Until
then, README may link the public evidence and field-report surface, but should
not imply a broader support community or real-time help path.
