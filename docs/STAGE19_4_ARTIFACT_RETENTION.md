# Stage 19.4 Exact-Candidate Artifact Retention

This branch is operational archival tooling only. It does not change, replace, merge, sign, or publish the accepted Stage 19.4 engineering candidate.

## Frozen source candidate

- PR: `#32`
- source branch: `stage19-4-final-docs-package`
- exact source SHA: `933d637b42c0ad038cefc64970a4c9d08f230fcd`
- source workflow run: `32621922885`
- source artifact id: `9488752611`
- source artifact digest: `sha256:3a0af1169b6a016be9297f816e2f50bc0b8b131bcad01b29031553a69f688190`
- release label: `0.8.0-rc3`
- engineering state: `READY_FOR_FINAL_ACCEPTANCE`
- publication state: `FINAL_ACCEPTANCE_PENDING`

## Purpose

The original Actions artifact uses a seven-day retention period. The retention workflow downloads that already-produced artifact by exact workflow run and artifact identity, verifies the source SHA and cross-checks the portable and installer hashes against their existing Stage 19.4 evidence, then re-uploads the same candidate files as an archival copy with a longer retention request.

The workflow must not rebuild the executable, installer, or portable archive. A rebuilt binary would be a different candidate and cannot be substituted for the accepted exact-head artifact.

## Non-authorization boundary

This archival operation does not authorize merge, public release, production signing, provider-network UAT, private expert evidence, or final acceptance. The retained copy remains an unsigned engineering candidate pending the separately gated final-acceptance work.
