# Deployment policy

Effective September 26, 2026, by explicit user instruction: **do not retain
rollback artifacts.** This is the current deployment policy for this repository.
It supersedes older instructions requiring deployment backups, rollback archives,
old fallback runtimes or rollback-space reservations, even when those instructions
appear in an earlier reviewed handoff or private deployment procedure.

## Recovery and storage

- Recover software by rebuilding the required committed Git revision and using
  the corresponding official client assets. Record exact source and artifact
  identities so the intended build is reproducible and verifiable.
- Do not create or retain copies, archives, old installed hosts or old client
  runtimes for deployment rollback. Do not make such copies or their disk-space
  requirements a prerequisite for an update.
- Account for the actual working space needed to build, stage and install the
  current update. Do not add a rollback allowance or keep an obsolete deployment
  solely as a fallback. Independently used active client copies are not fallback
  copies and remain subject to the requested update scope.
- Preserve settings, saved recipe preferences, jobs, historical journals and
  other user data in place. Verify their preservation. Rebuilding software does
  not replace or authorize deleting these records, and interrupted requests must
  not be replayed merely because software was reinstalled.

## Validation remains required

Verify the exact client, source, package and installed identities. Keep readiness
blocked during an incomplete or failed update; repair or rebuild the intended
version before declaring it usable. Retain concise validation evidence needed to
explain the result, without retaining binary fallback copies under that label.

This policy concerns deployment artifact retention. It does not remove tests of
native hook rollback, transaction recovery, cleanup after failed operations, or
other runtime correctness checks. Those test semantics are not permission to
create deployment backups.

Historical documents may retain their factual account of earlier deployments.
Their backup/rollback requirements are superseded by this policy. Current entry
points and update instructions must link here and must not repeat those obsolete
requirements as active work.
