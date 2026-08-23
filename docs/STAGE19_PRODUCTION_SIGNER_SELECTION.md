# Stage 19 Production Signer Selection

## Purpose

Stage 19 Final Acceptance is already frozen around one security invariant:

- the production `Law-Rag.exe` must be Authenticode-signed;
- the installer must be Authenticode-signed by the same signer;
- the update manifest must carry a detached CMS signature from that same signer identity;
- all of those identities are verified against one explicitly selected thumbprint.

This document selects a signer **interface shape** without purchasing a service, creating an account, publishing a release, running provider UAT, or touching the frozen RC3 candidate.

Frozen engineering candidate source SHA:

```text
8c05ddd91712d5d9cdbdafe90e77cc9de03b8593
```

The exact candidate remains unchanged and unsigned until a production signer passes the capability preflight.

## Required signer interface

The current implementation intentionally uses standard Windows cryptographic interfaces:

```text
Cert:\CurrentUser\My\<thumbprint>
```

For the selected certificate, Windows must expose:

1. a code-signing certificate with the Code Signing EKU `1.3.6.1.5.5.7.3.3`;
2. an available private key through the Windows certificate/key provider;
3. Authenticode signing capability;
4. generic X.509 private-key signing capability usable by `.NET SignedCms.ComputeSignature`;
5. one stable signer identity that can be matched across EXE, installer and detached CMS evidence.

The private key does **not** need to be exportable. Hardware token, local HSM or cloud-backed CNG/KSP implementations are acceptable if they expose the required operations through Windows.

## Screened approaches

### 1. Disposable/self-signed certificate

Rejected for production.

It remains useful only for CI semantics. Windows does not broadly trust a self-signed publisher certificate, so it cannot represent the final public signer.

### 2. SignPath Foundation open-source signing

Potentially useful for Authenticode, but not selected as the immediate Stage 19 route.

Reasons:

- SignPath Foundation requires qualifying projects to use an OSI-approved open-source license and to publish a code-signing policy. Law-Rag currently has no root `LICENSE` file on the frozen line.
- SignPath's public artifact-configuration documentation marks generic detached CMS creation (`create-cms-signature`) as an Advanced Code Signing feature. The free Open Source Code Signing edition therefore cannot be assumed to satisfy Law-Rag's same-signer detached-CMS invariant.
- SignPath Foundation also requires origin verification from a trusted build system and project/release eligibility review.

Do not weaken or silently replace the Stage 19 CMS trust chain merely to fit a free signing service.

Official references:

- https://signpath.org/terms.html
- https://docs.signpath.io/artifact-configuration/reference
- https://docs.signpath.io/trusted-build-systems/github

### 3. Microsoft Azure Artifact Signing

Not selected for the current frozen implementation.

Azure Artifact Signing is a strong managed Authenticode option, but the documented production integration signs through SignTool/Artifact Signing client integrations rather than placing a conventional production private key in `Cert:\CurrentUser\My` for arbitrary local CMS operations. Adopting it would require a separately reviewed redesign of the current detached-CMS signing path.

Public Trust geography/identity eligibility must also be satisfied by the actual applicant; do not infer eligibility from repository location or CI location.

Official references:

- https://learn.microsoft.com/azure/artifact-signing/quickstart
- https://learn.microsoft.com/azure/artifact-signing/how-to-signing-integrations

### 4. CA-issued IV/OV certificate exposed through Windows CNG/KSP

**Selected interface shape.**

This is the least disruptive route because it matches the already-validated Stage 19 design instead of changing the design after the RC3 engineering candidate was frozen.

A compliant physical token/HSM is acceptable. A cloud signing service is also acceptable only if its Windows adapter exposes the certificate and private-key operations through the Windows certificate store/CNG provider.

## Leading individual-developer candidate: SSL.com IV + eSigner CKA

This is the current first candidate to evaluate, not a purchase authorization or endorsement guarantee.

Why it is structurally promising:

- SSL.com offers Individual Validated code-signing certificates for applicants without a registered business entity.
- eSigner CKA is documented as a Windows CNG/KSP adapter that loads the code-signing certificate into the Windows certificate store and allows signing operations through the cloud-held private key.
- SSL.com documents GitHub Actions/CI usage that selects the certificate from `Cert:\CurrentUser\My` by thumbprint.
- This shape is much closer to Law-Rag's existing Authenticode + `.NET SignedCms` implementation than a SignTool-only remote-signing integration.

Current public list pricing observed during this engineering review:

```text
IV code-signing certificate: USD 129/year
OV code-signing certificate: USD 129/year
eSigner Tier 1:             USD 15/month, 240 signings
```

Pricing and applicant validation can change. Verify the checkout/validation terms before any purchase.

Official references:

- https://www.ssl.com/products/software-integrity/code-signing/iv/
- https://www.ssl.com/products/software-integrity/code-signing/ov/
- https://www.ssl.com/products/software-integrity/signing-service/
- https://www.ssl.com/how-to/how-to-integrate-esigner-cka-with-ci-cd-tools-for-automated-code-signing/

## Mandatory preflight before touching RC3

Even if a provider says its adapter is CNG/KSP-compatible, Stage 19 will not trust that claim by assumption.

Run:

```powershell
./release/test-stage19-production-signer-capability.ps1 `
  -SignerThumbprint '<PRODUCTION_SIGNER_THUMBPRINT>' `
  -OutputPath '<WORK>/evidence/STAGE19-PRODUCTION-SIGNER-PREFLIGHT.json' `
  -RequireTrustedAuthenticode
```

The probe signs only disposable temporary files. It must prove:

```text
candidate_touched = false
production_candidate_signing_executed = false
authenticode_probe.signer_matches_requested = true
detached_cms_probe.compute_succeeded = true
detached_cms_probe.signature_only_valid = true
detached_cms_probe.signer_matches_requested = true
signer_interface_capable = true
preflight_state = SIGNING_INTERFACE_CAPABLE
```

Only after this succeeds may the operator sign the exact frozen `Law-Rag.exe`.

If the production provider's Windows adapter cannot complete the detached CMS probe, stop. Do not sign the RC3 candidate and do not alter Final Acceptance evidence to hide the incompatibility.

## Purchase and account boundary

No repository workflow in this branch:

- buys a certificate or subscription;
- creates an SSL.com/Azure/SignPath account;
- stores a production password, TOTP seed or private key;
- submits a real signing transaction;
- signs the RC3 candidate;
- publishes anything.

Production credentials must never be committed to Git. Any later CI integration must use repository/environment secrets and must not print passwords, TOTP material, recovery material or private keys to logs.

## Current decision

```text
architecture_change_required = false
preferred_signer_interface    = CA-issued IV/OV via Windows CNG/KSP
first_provider_to_preflight   = SSL.com IV/OV + eSigner CKA
candidate_signing_state       = NOT_STARTED
final_acceptance_state        = FINAL_ACCEPTANCE_PENDING
```

The next external action is obtaining/configuring a real production signer. The next cryptographic action after configuration is the disposable capability preflight, **not** signing `Law-Rag.exe` immediately.
