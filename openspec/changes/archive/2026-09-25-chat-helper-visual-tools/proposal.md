# Proposal

## Why

Chat currently hides helper delegation, delays helper discovery, and does not reliably show live or reopened child output in the helper rail. Browser-enabled turns can also fail before inference because request redaction treats a nested tool-schema dictionary as a media type. Browser and Windows controls are split between two surfaces, obscuring the effective selection and recovery actions.

## What Changes

- Show each named helper request in the parent conversation and its live, scoped transcript in the existing expandable rail, including waiting, failure, and reopened states.
- Use the existing rail toggle as the single helper entry point and show live helper activity there.
- Repair model-request redaction for browser tool schemas and preflight browser-worker/session availability before a browser-enabled turn.
- Put Browser and Windows selection, installation, grants, and session recovery together in the composer capability menu; remove the duplicate visual-testing controls from Setup.
- Make the displayed next-turn tool selection agree with dispatch, including when Browser or Windows is turned off.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: Chat delegation visibility, helper rail behavior, and the location and readiness of visual capability controls.
- `agents-workflows`: Durable, correctly scoped helper activity and transcript ownership.
- `environments-tools`: Browser and Windows capability preflight and truthful effective selection.

## Impact

The existing backend agent observer, Chat readiness path, request capture, and Electron Chat renderer change. Existing interaction events, tool names, session/grant APIs, and authorization boundaries remain the integration points; no new service or agent runtime is introduced.
