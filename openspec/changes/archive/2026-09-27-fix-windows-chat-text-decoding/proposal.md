# Proposal

## Why

Windows agent Chat aborts when native grep decodes UTF-8 ripgrep output as cp1252. The exact reported error was reproduced without a model against a valid UTF-8 file; enabling Python UTF-8 mode returned all four matches.

## What Changes

- Start the Windows backend in UTF-8 mode through both supported entrypoints and the desktop shortcut.
- Preserve the existing Windows host-command output encoding independently of backend UTF-8 mode.
- Return decoding failures from native grep/read_file as attributable, recoverable tool errors rather than aborting Chat.
- Verify native Unicode searches, startup/lifecycle, sibling settlement and retained recovery results.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environments-tools`: ENV-020 requires exact Unicode native search results on Windows across project and framework routes.
- `backend-desktop`: API-026 requires read/search decoding errors to retain call identity and allow correction without weakening other recovery guarantees.

## Impact

Backend startup, Windows launcher, host shell decoder and existing tool-error integration. No model settings, dependency upgrades, installed-package edits, public API or schema changes. Existing files and chats remain intact and failed turns are not replayed automatically.
