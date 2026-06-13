# Project Planning Automation

Role: implementation map.

AIppocampus uses GitHub issues as executable work items and the GitHub Project
as a planning view. Automation may keep metadata fresh, but docs and real code
remain the source of truth.

## Project Triage

`tools/aippocampus/github/project_triage.py` runs during issue intake through
`.github/workflows/project-triage.yml`.

GitHub Actions should use the explicit `AIPPOCAMPUS_PROJECTS_TOKEN` secret. For
local maintainer runs, the tool also accepts `GH_TOKEN` or the authenticated
GitHub CLI keyring through `gh auth token`; this keeps local audits usable
without copying a plaintext token into the shell environment.

Use it for narrow, issue-local metadata:

- fill missing Project fields such as `Status`, `Track`, `Kind`, `Stage`,
  `Evidence`, `Priority`, and `Source`;
- assign an inferred open Milestone only when an issue has none;
- warn when a likely design, benchmark, semantic, or subconscious issue lacks a
  canonical `docs/...` or `skills/aippocampus/references/...` source pointer.

Milestone inference should cover the current open roadmap buckets, including
public readiness/distribution, benchmark evidence, ambient recall warmth,
cognitive runtime continuity, sync/scale infrastructure, security/privacy, and
architecture debt. Specific parents and benchmark/source-evidence routes should
win over broad privacy or runtime keywords so the automation does not move work
out of its owning track just because an issue mentions safety boundaries.

It should not rewrite human-owned Project metadata, reopen issues, or decide
product direction from keywords.

## Planning Audit

`tools/aippocampus/github/planning_audit.py` runs as the slower scheduled
roadmap hygiene pass through `.github/workflows/planning-audit.yml`.

It uses the same token lookup as project triage: explicit CI secret first, then
`GH_TOKEN`, then local `gh auth token` for maintainer workstations.

Use it for cross-issue and docs drift:

- report open issues without Milestones and reuse the triage policy for
  high-confidence milestone suggestions;
- report design/research issues that lack source-doc pointers;
- safely repair exact unchecked checklist items when the referenced child issue
  is closed;
- report weak recently closed issue evidence without reopening anything;
  closing PR references, exact verification comments, duplicate/not-planned
  rationale, and transferred follow-up owners count as evidence, but vague
  "done enough" comments do not;
- scan active docs, excluding `docs/archive/**`, for unresolved planning
  language that lacks an open owner issue;
- report GitHub Discussions that have no issue/doc refs, stale docs links, or
  several linked issues but no compact implementation-map comment.

Default scheduled runs are dry-run reports. Manual repair mode applies only the
safe repairs above: missing high-confidence Milestones and exact closed-child
checklist updates. It may also add at most one short implementation-map comment
to a Discussion when the linked issues are exact matches and no map comment
already exists. Everything else stays in `needs_human_review`.

## Boundary

Planning automation is a clerk, not a product judge. It can surface drift and
perform tiny mechanical repairs, but it must not create large batches of issues
from research prose, overwrite human-set Milestones, duplicate docs into issue
bodies, or treat planning metadata as source-backed evidence. Discussions are
narrative/context surfaces; issues remain the executable work queue.
