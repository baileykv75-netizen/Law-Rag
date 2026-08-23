# Stage 19.4 Superseding Exact-Candidate Retention

This operational branch preserves the superseding Stage 19.4 engineering candidate produced after the packaged-guide and actual-portable-ZIP smoke hardening.

It does not rebuild, sign, merge, publish, or relabel the candidate.

## Current candidate

- PR: `#32`
- source branch: `stage19-4-final-docs-package`
- exact source SHA: `8c05ddd91712d5d9cdbdafe90e77cc9de03b8593`
- source workflow run: `32629468653`
- source artifact id: `9490922586`
- source artifact digest: `sha256:a8794a18113fabbfaf1ac56f09b74640048f59967ba41611afbac3bd7d98cbc3`
- release label: `0.8.0-rc3`
- engineering state: `READY_FOR_FINAL_ACCEPTANCE`
- publication state: `FINAL_ACCEPTANCE_PENDING`

The earlier exact candidate `933d637b42c0ad038cefc64970a4c9d08f230fcd` remains valid historical engineering evidence but is superseded by this candidate because Stage 19.4 now validates the actual packaged RC3 portable artifact and uses a signing-state-neutral packaged Windows guide.

## Retention rule

The retention workflow downloads the already-produced artifact by exact workflow run and artifact identity. It must not rebuild the Windows bundle, portable archive, or installer.

Before archival upload it recomputes and cross-checks the portable and installer SHA-256 values against the Stage 19.4 final package evidence, RC manifest, installer evidence and `SHA256SUMS.txt`, and verifies that the candidate remains unsigned/non-published with external evidence still outside Stage 19.4.

The retained artifact is an archival copy only and is not a new release candidate.

## Non-authorization boundary

This operation does not authorize:

- merge;
- production Authenticode signing;
- public release or update publication;
- paid/network DeepSeek or Kimi execution;
- private expert evidence;
- Stage 19 Final Acceptance completion.
