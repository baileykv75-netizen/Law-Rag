# Stage 19.4 Superseding Exact-Candidate Retention

This operational branch preserves the superseding Stage 19.4 engineering candidate produced after the packaged-guide and actual-portable-ZIP smoke hardening.

It does not rebuild, sign, merge, publish, or relabel the candidate.

## Current candidate

- PR: `#32`
- source branch: `stage19-4-final-docs-package`
- exact source SHA: `8c05ddd91712d5d9cdbdafe90e77cc9de03b8593`
- source workflow run: `32629468653`
- source artifact id: `9490770536`
- source artifact digest: `sha256:3baa68daf4ed2bdd7e644b19965c45a2234f39e84fadb0fbaf2d92a9de53b728`
- portable SHA-256: `9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796`
- installer SHA-256: `cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8`
- release label: `0.8.0-rc3`
- engineering state: `READY_FOR_FINAL_ACCEPTANCE`
- publication state: `FINAL_ACCEPTANCE_PENDING`

The source artifact identity above is the authoritative metadata returned by the workflow-run artifact API and independently printed by `actions/download-artifact@v4`. An earlier provisional retention run used stale connector metadata constants; it verified the candidate files successfully but is not accepted as the archival freeze because its preservation JSON recorded the wrong source artifact ID/digest.

The earlier exact candidate `933d637b42c0ad038cefc64970a4c9d08f230fcd` remains valid historical engineering evidence but is superseded by this candidate because Stage 19.4 now validates the actual packaged RC3 portable artifact and uses a signing-state-neutral packaged Windows guide.

## Retention rule

The retention workflow first queries GitHub Actions for the exact source run/artifact metadata and fails closed unless the artifact ID, digest and head SHA match the values above. It then downloads that already-produced artifact by exact workflow run and artifact identity. It must not rebuild the Windows bundle, portable archive, or installer.

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
