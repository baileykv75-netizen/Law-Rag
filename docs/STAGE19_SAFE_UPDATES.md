# Stage 19.3 — Safe Update Trust and Verification

## Scope

Stage 19.3 adds a fail-closed update-candidate verification boundary on top of the Stage 19.1 installer and Stage 19.2 Authenticode publication semantics.

It does **not** silently auto-install updates, generate or fabricate a production release certificate, weaken Stage 19.2 signing requirements, run DeepSeek/Kimi network UAT, or use private expert evidence.

## Trust model

A Windows update candidate is eligible only when all of the following are true:

1. the update manifest has the expected schema, application ID and target;
2. the candidate version is strictly newer than the installed/current version;
3. the artifact URL is HTTPS and contains no embedded credentials;
4. the downloaded installer filename, byte length and SHA-256 exactly match the manifest;
5. the manifest names an explicitly configured trusted release-signer certificate thumbprint;
6. the downloaded installer has a `Valid` Windows Authenticode signature;
7. the installer signer thumbprint exactly matches both the manifest signer and the locally configured trusted signer;
8. the manifest itself has a detached CMS signature from the same explicitly trusted release signer;
9. the detached CMS signature validates over the exact manifest bytes.

Any failure is terminal for that candidate. Stage 19.3 does not fall back to an unsigned installer, a different signer, HTTP, a same/older version, or hash-mismatched bytes.

## Manifest

The Stage 19.3 update manifest is intentionally small and release-oriented:

```json
{
  "schema_version": "1.0.0",
  "application_id": "law-rag",
  "target": "windows-x64",
  "version": "0.8.0-rc3",
  "published_at": "2026-08-22T00:00:00Z",
  "source_commit_sha": "0123456789abcdef0123456789abcdef01234567",
  "artifact": {
    "filename": "Law-Rag-0.8.0-rc3-windows-x64-setup.exe",
    "url": "https://example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe",
    "sha256": "...",
    "size_bytes": 123456,
    "authenticode_signer_thumbprint": "..."
  }
}
```

The release process may publish the manifest and detached `.p7s` signature beside the installer. A candidate must be verified before any installer is considered eligible to launch.

## Version semantics

Stage 19.3 accepts SemVer-style versions with an optional prerelease suffix, including the existing `0.8.0-rc2` line. A candidate must compare strictly newer than the current version. Build metadata does not make a version newer by itself.

```text
0.8.0-rc2 -> 0.8.0-rc3   ALLOW after all trust checks
0.8.0-rc2 -> 0.8.0       ALLOW after all trust checks
0.8.0     -> 0.8.0        REFUSE
0.8.0     -> 0.7.9        REFUSE
```

## CI validation boundary

Normal CI has no production release certificate. Stage 19.3 therefore uses an ephemeral CI-only self-signed code-signing certificate to prove the positive cryptographic path end-to-end. The certificate exists only inside the disposable Windows runner, is never committed, and is never represented as the Law-Rag production release signer.

The Windows workflow must prove at least:

- exact-head checkout;
- inherited Stage 19.1 installer build and lifecycle;
- inherited Stage 19.2 unsigned publication refusal;
- positive Stage 19.3 verification using an ephemeral trusted CI signer;
- rejection of manifest tampering;
- rejection of installer/hash tampering;
- rejection of signer mismatch;
- rejection of same/older versions;
- rejection of insecure/non-HTTPS URLs;
- no provider network UAT and no private expert evidence.

## Non-goals

Stage 19.3 does not yet:

- poll a remote update service in the background;
- download without an explicit update action;
- silently execute an installer;
- replace the Stage 19.1 installer lifecycle;
- define final public release channels or publication URLs;
- claim that CI artifacts are production-signed or publishable.

Those publication/release decisions remain later Stage 19/final-acceptance work.
