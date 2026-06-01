# Project Planning Automation

AIppocampus uses GitHub issues as executable work items and the GitHub Project
as a planning view. Automation may keep metadata fresh, but docs and real code
remain the source of truth.

## Project Triage

`tools/aippocampus/github/project_triage.py` runs during issue intake through
`.github/workflows/project-triage.yml`.

Use it for narrow, issue-local metadata:

- fill missing Project fields such as `Status`, `Track`, `Kind`, `Stage`,
  `Evidence`, `Priority`, and `Source`;
- assign an inferred open Milestone only when an issue has none;
- warn when a likely design, benchmark, semantic, or subconscious issue lacks a
  canonical `docs/...` or `skills/aippocampus/references/...` source pointer.

It should not rewrite human-owned Project metadata, reopen issues, or decide
product direction from keywords.

## Planning Audit

`tools/aippocampus/github/planning_audit.py` runs as the slower scheduled
roadmap hygiene pass through `.github/workflows/planning-audit.yml`.

Use it for cross-issue and docs drift:

- report open issues without Milestones and reuse the triage policy for
  high-confidence milestone suggestions;
- report design/research issues that lack source-doc pointers;
- safely repair exact unchecked checklist items when the referenced child issue
  is closed;
- report weak recently closed issue evidence without reopening anything;
- scan active docs, excluding `docs/archive/**`, for unresolved planning
  language that lacks an open owner issue.
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
