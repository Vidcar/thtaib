# Proposal

## Why

Agent browser access currently opens Edge on the person's desktop. Chrome should stay in the background while the same live browser is visible and usable inside Chat, including human sign-in and resolution changes.

## What Changes

- Run actual Chrome with a separate persistent profile per chat and complete owned-process cleanup.
- Show the agent's active page in a Browser rail with navigation, tabs, resolution, lifecycle and manual controls.
- Pause the complete task and its helpers during takeover; inspect changed page state before returning to agent work.
- Add upstream visual interaction and confined uploads, and retain downloads through the existing Library.
- Extend authenticated browser status/action/event contracts and lifecycle recovery without exposing browser credentials or unrestricted code.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environments-tools`: owned persistent Chrome, live viewing, typed control, files and effective browser authority.
- `backend-desktop`: interactive Browser rail and truthful viewport/session presentation.
- `agents-workflows`: coordinated browser takeover and fresh-state continuation across helpers.
- `state-recovery`: profile persistence, deletion and backup quiescence with truthful worker-loss recovery.

## Impact

The existing browser worker/service, Chat rail, execution control, retained assets, chat deletion and backup boundaries change. The official Playwright MCP server and LangChain adapter remain the agent integration. Browser API/shared contracts extend; the worker gains the official MCP SDK transport with pinned dependencies. Windows-first, installed Chrome, no ordinary browser-profile access, and no downloads during agent dispatch.
