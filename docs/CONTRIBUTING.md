# Contributing to Platform Standards

This document governs how the standards in this folder are changed — [naming_standards.md](naming_standards.md), [notebook_standards.md](notebook_standards.md), [lakehouse_standards.md](lakehouse_standards.md), and any future standards. It is the page the `CODEOWNERS` rule points to.

The standards themselves are enforced in CI. This document is about changing the standards, not following them — a different and more dangerous activity, because a bad change propagates to everyone.

## Core Principle

**Standards are code.** They live in the repo, they version with the repo, and they change through pull requests reviewed like any other code change. There is no separate "documentation process" — the same discipline that governs a notebook change governs a standards change.

A consequence worth stating plainly: practice cannot silently drift from the standard, because the standard is enforced by the validation script in CI. The only way practice and standard diverge is if someone changes the standard. That is what this document controls.

## Approval

The `/docs` folder is owned via `CODEOWNERS` by the platform owner. Standards changes require the owner's approval to merge. Anyone may *propose* a change; no one merges their own change to the standards unilaterally — including contractors and external consultants, whose house preferences are proposals, not defaults.

For a team this size, single-owner approval beats committee. It keeps the standards coherent and avoids the slow death of design-by-consensus.

## Changes Are Tiered by Cost

Not every change deserves the same friction. Match the ceremony to the stakes.

### Trivial — just merge

Typos, clearer wording, corrected examples, broken-link fixes. No ceremony. Approve and merge.

### Additive — fast approval

A new source token, a new gold subject area, a new standard column. These are mechanical: an enumeration grows, the validation regex regenerates, nothing existing breaks. Low stakes, quick yes. The bar is "does this fit the existing pattern?" — if yes, approve.

### Structural — expensive by design

Changing the pattern itself, renaming a medallion layer, altering the token count, changing the separator. These are slow on purpose.

**A structural change must include a migration plan in the PR.** Specifically:

- The script (or documented manual steps) that renames existing items to the new standard
- The blast radius: which notebooks, tables, MLVs, pipeline references, and semantic model bindings are affected
- A rollback path

This requirement is the brake. It slows structural churn to the rate at which someone is willing to do the migration work — which is exactly the rate that's healthy. If a change isn't worth writing a migration for, it isn't worth making.

## The Decision Log Is Binding

Each standards document ends with a decision log recording *why* choices were made. These exist to prevent relitigation.

**You may not reopen a logged decision without new information.**

- "I'd prefer `chargeback` over `cback`" — not new information. Preference is not a reason; the decision was made deliberately.
- "`cback` now collides with a token we need for a new source, here's the conflict" — new information. Reopen it.

This rule stops the team re-arguing settled choices every time someone new joins with different habits. The decision log is the record of arguments already had.

When a decision *is* changed, update the log: record the new decision and the new information that justified it. The log is append-aware, not overwritten — future readers should see that a decision changed and why.

## Exceptions Are a Signal

If people repeatedly want to deviate from a rule, the rule is probably wrong. Deviations are tracked in PR review, and a recurring one triggers a review of the standard itself — not a string of one-off exceptions.

A standard that accumulates special cases is decaying. The healthy response to repeated friction is to fix the rule, not to grant exceptions. The standards bend to reality; they do not collect footnotes.

## A Rule Earns Its Place

Do not add a rule for a situation the platform has not actually encountered. Speculative rules for hypothetical edge cases are cruft: they make the document harder to read and enforce for zero current benefit.

The test, same as the test for adding a new standards document at all: add the rule once you've hit the situation it governs — ideally more than once. Until then, the absence of a rule is not a gap; it is appropriate restraint.

## Cadence

A 30-minute review once a quarter: do the standards still describe what we actually do? Monthly is too frequent — usually nothing has changed. Annual lets drift accumulate until it is expensive to correct. Quarterly catches divergence while it is still cheap to fix, and is a natural moment to action any tracked exceptions.

## How to Make a Change

1. Branch from `main`.
2. Edit the relevant standards document.
3. If the change touches an enumeration the validation script reads, confirm the regenerated regex still passes against the existing repo (the CI naming-validation stage does this automatically).
4. If the change is structural, include the migration plan in the PR description.
5. Update the document's decision log if you are making or changing a decision.
6. Open a PR. The `CODEOWNERS` rule routes it to the platform owner.
7. On approval and merge, the published wiki updates automatically.

## The Minimal Version

If the tiering and cadence feel heavier than the team needs, the load-bearing core is just four things:

1. Changes go through a PR.
2. One named owner approves.
3. The decision log records the why.
4. Logged decisions are not reopened without new information.

Everything else in this document — the tiering, the migration-plan requirement, the quarterly review — is an enhancement to add when the team is large enough to need it. Start with the four. Grow the process only when a real problem demands it.

## Maintenance

This document governs changes to the other standards documents, and changes to *this* document follow the same rules it describes: a PR, owner approval, and a decision-log entry for anything non-trivial.
