# Stage 19.4 — Final RC3 Documentation and Package Engineering

## Scope

Stage 19.4 closes the **provider-free engineering** portion of Stage 19 by assembling one coherent Windows RC3 candidate identity across the portable ZIP, per-user installer, release documentation, and exact-head package evidence.

It does not create or import a production release certificate, publish a GitHub Release, choose a final public update URL, execute paid DeepSeek/Kimi UAT, consume private expert evidence, or claim that the candidate is production-ready.

## Candidate identity

Stage 19.4 uses one explicit release label:

```text
0.8.0-rc3
```

The two candidate distribution forms are:

```text
Law-Rag-0.8.0-rc3-windows-x64.zip
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

Historical Stage 19.1/portable-RC defaults remain replayable. Stage 19.4 passes the RC3 identity explicitly to the existing packaging/build tools instead of silently rewriting historical stage semantics.

## Distribution and data ownership

Portable mode keeps the historical one-folder behavior and stores its default runtime beside the extracted application unless `LAW_RAG_RUNTIME_DIR` is explicitly set.

Installed mode is per-user and separates application binaries from user runtime:

```text
application: %LOCALAPPDATA%\Programs\Law-Rag
runtime:     %LOCALAPPDATA%\Law-Rag\runtime
```

Reinstall and uninstall must preserve the user runtime. Uninstall owns the application/shortcuts, not the local audit history or contract data.

## Package evidence

The Stage 19.4 Windows workflow must prove on the exact PR head:

- the frozen Windows onedir bundle still passes inherited Stage 18 packaged boundaries;
- the RC3 portable ZIP is deterministic, privacy-scanned, and bound to an exact `RC-MANIFEST.json` / `SHA256SUMS.txt`;
- the RC3 installer is built from the same exact head;
- install, reinstall, and uninstall preserve the Stage 19.1 data-ownership semantics;
- the Stage 19.2 publication gate truthfully refuses the unsigned RC3 engineering candidate;
- final package evidence binds portable and installer hashes to the same source commit;
- provider network UAT and private expert evidence remain false.

Stage 19.4 therefore ends in:

```text
engineering_state = READY_FOR_FINAL_ACCEPTANCE
publication_state = FINAL_ACCEPTANCE_PENDING
```

`READY_FOR_FINAL_ACCEPTANCE` is not equivalent to `PUBLISHABLE`.

## Safe-update relationship

Stage 19.3 already proves the fail-closed update trust chain: exact manifest bytes, detached CMS, trusted signer agreement, Authenticode validity, SHA-256/size, HTTPS, and strictly newer version semantics.

Stage 19.4 does not add background polling, unattended download, or silent installation. Final channel/URL/publication decisions remain explicit final-acceptance work.

## Final acceptance still required

The following gates intentionally remain outside normal CI and outside Stage 19.4:

1. real production release signer / publishable Authenticode acceptance;
2. final release channel and publication URL decision;
3. private expert evidence;
4. explicit paid/network DeepSeek + Kimi `ISSUE_V1` UAT;
5. Stage 16 `--require-complete-evidence` closure;
6. final packaged Windows acceptance smoke on the candidate intended for distribution.

No missing gate may be fabricated, inferred from synthetic CI, or relabeled as complete.
