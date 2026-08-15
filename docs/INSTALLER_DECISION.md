# Installer Decision — Stage 11E

## Current state

```text
Decision: PENDING_MANUAL_UAT
Default recommendation: PORTABLE_ZIP_SUFFICIENT
Installer implementation: NOT STARTED
```

The automated evidence currently favors a portable ZIP for the first personal-use release:

- clean Windows runner builds the exact locked PyInstaller `onedir` bundle;
- `Law-Rag.exe` starts without end-user Python/Node;
- production React + FastAPI run from one local loopback process;
- diagnostics, native PDF upload and packaged PDFium rendering pass;
- final RC ZIP is independently extracted and smoke-tested;
- user/private runtime data is kept outside the shipped archive;
- no registry/service/PATH/file-association behavior is currently required by the application architecture.

Those facts show an installer is **not technically necessary** for the base RC.

## Why the decision is not final yet

Stage 11E intentionally requires one normal-user Windows acceptance pass outside GitHub Actions. Automated runners cannot reliably answer whether the portable workflow is confusing to a real user.

The remaining evidence comes from `docs/RC_WINDOWS_UAT.md`, especially:

```text
ZIP extraction understandable?
Law-Rag.exe easy to find?
writable-folder requirement confusing?
shortcut materially necessary?
uninstall/removal unclear?
Windows reputation/security warnings blocking use?
```

## Decision rule

After manual UAT, choose exactly one:

### `PORTABLE_ZIP_SUFFICIENT`

Use when the user can reliably:

1. extract the ZIP;
2. run `Law-Rag.exe` from a writable folder;
3. understand that `runtime/` contains local portable data;
4. remove/move the application without unexpected system state;
5. use diagnostics without administrator/setup steps.

Under this outcome, do **not** add MSI/Inno/NSIS merely for appearance. A portable ZIP is the first release format.

### `INSTALLER_JUSTIFIED`

Use only when manual testing demonstrates a concrete recurring problem an installer would solve, for example:

- users repeatedly place the bundle in an unwritable location;
- shortcut/uninstall handling materially improves the target workflow;
- optional component installation needs one controlled path;
- future update/distribution requirements cannot be handled acceptably by portable replacement.

If selected, Stage 11E must first document the exact installer responsibilities and prohibited system mutations before choosing MSI/Inno/NSIS.

## Explicit non-reasons

The following are not sufficient reasons to add an installer:

- “Windows software usually has one”;
- “one-click install looks more professional”;
- hiding the inspectable onedir layout;
- converting the app into a single opaque executable;
- avoiding documentation of runtime/data paths.

## Publication boundary

The installer decision is separate from publication. Even if `PORTABLE_ZIP_SUFFICIENT` is selected, creating a public GitHub Release/tag remains an explicit owner action rather than an automatic CI side effect.
