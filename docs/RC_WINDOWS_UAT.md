# Law-Rag 0.8.0-rc1 — Windows User Acceptance Checklist

This checklist is for a normal Windows 10/11 desktop test of the **portable RC ZIP**, not the developer repository.

Use fictional/public documents first. Do not use a private real contract merely to test installation/launch behavior.

## Test record

```text
Tester:
Windows version:
RC ZIP filename:
RC ZIP SHA-256:
Test date:
Result: PASS / FAIL / PASS WITH NOTES
Notes:
```

## 1. Download/extract boundary

- [ ] Verify the ZIP filename is `Law-Rag-0.8.0-rc1-windows-x64.zip`.
- [ ] Compare its SHA-256 with `SHA256SUMS.txt` / `RC-MANIFEST.json`.
- [ ] Extract the ZIP into a normal writable user folder such as Documents/Desktop/test folder.
- [ ] Confirm extraction produces a `Law-Rag` folder containing `Law-Rag.exe` and `README-WINDOWS.md`.
- [ ] Do not copy API keys or private contracts into the application folder for this basic test.

Expected: no installer, administrator permission, Node.js or Python installation is required.

## 2. First launch

- [ ] Double-click `Law-Rag.exe`.
- [ ] Confirm a local console window opens without an immediate crash.
- [ ] Confirm the default browser opens the Law-Rag workstation at `127.0.0.1`.
- [ ] Confirm the page is the production UI, not a Vite development page/error.
- [ ] Confirm no DeepSeek/Kimi key is required merely to open the workstation.

Expected: the base application starts locally and does not expose a non-loopback server.

## 3. Native-text PDF path

Use a fictional/public native-text PDF.

- [ ] Upload the PDF.
- [ ] Confirm the document appears as a local job.
- [ ] Confirm page count/route information is visible.
- [ ] Open the workspace/source-page view.
- [ ] Confirm a PDF page renders correctly.
- [ ] Generate canonical contract structure where the fixture is suitable.
- [ ] Run deterministic audit rules where the fixture is suitable.
- [ ] Inspect available Legal Evidence/retrieval results.

Expected: native PDF extraction and PDFium page rendering work without PaddleOCR.

## 4. Optional OCR / semantic behavior

On the base RC, do **not** install PaddleOCR or BGE first.

- [ ] Run `Law-Rag.exe --diagnose`.
- [ ] Confirm missing OCR is shown as an optional/unavailable capability rather than a base-app crash.
- [ ] Confirm missing semantic/BGE is shown as optional and Exact + lexical/BM25 remain available.
- [ ] Try a scanned/image-only document only if you want to verify the explicit OCR-unavailable path.

Expected: the base RC explains the limitation and preserves supported fallback behavior.

## 5. Public legal/retrieval store

- [ ] Confirm legal knowledge/retrieval surfaces load without rebuilding databases manually.
- [ ] Confirm the UI still states the bundled corpus is a `CURATED_EXCERPT`.
- [ ] Confirm a no-hit result is not presented as proof that no relevant law exists.

Expected: bundled public legal/retrieval assets are usable offline for the covered seed.

## 6. Provider boundary — optional

Only perform this section if intentionally testing real external model calls with synthetic/public content.

- [ ] Confirm the base RC works before any provider key is configured.
- [ ] Configure `DEEPSEEK_API_KEY` / `MOONSHOT_API_KEY` using the documented local environment method.
- [ ] Confirm provider stages are explicit actions rather than automatic navigation calls.
- [ ] Confirm no API key value appears in diagnostics/output.

Expected: external transmission occurs only when the corresponding audit/review stage is intentionally run.

## 7. Persistence/restart

- [ ] Close Law-Rag.
- [ ] Relaunch it from the same extracted folder.
- [ ] Confirm previously created local jobs remain available where expected.
- [ ] Confirm the bundled public legal/retrieval databases remain healthy.
- [ ] Confirm `runtime/` contains local user data and was created only after use.

Expected: portable-folder persistence is understandable and does not modify the bundled public assets.

## 8. Controlled failure diagnostics

- [ ] While Law-Rag is closed, run `Law-Rag.exe --diagnose --json`.
- [ ] Confirm the output contains states/actions but no contract body, API key values or Authorization headers.
- [ ] Optionally occupy port 8000 and confirm Law-Rag refuses to start a second conflicting server instead of silently switching behavior.

Expected: failure is explicit; no destructive auto-repair occurs.

## 9. Portable usability decision input

Record friction, if any:

```text
Was ZIP extraction understandable? YES / NO
Was finding Law-Rag.exe understandable? YES / NO
Did a writable folder cause confusion? YES / NO
Was a desktop shortcut materially necessary? YES / NO
Was uninstall/removal unclear? YES / NO
Did Windows security/reputation warnings block realistic use? YES / NO
Would an installer solve a concrete observed issue? YES / NO
Observed issue:
```

This section is the evidence for the Stage 11E installer decision. An installer should not be added only because it looks more conventional.
