# Tasks

## 1. Native image path

- [x] 1.1 Bound project image reads through native `read_file`, correct its description, and verify image/oversize/text-only focused tests.
- [x] 1.2 Record and use separate user-image and tool-image capability evidence; verify a real vision model sees a known tool screenshot and model requests preserve tool identity/settings.

## 2. Owned test workers

- [x] 2.1 Package a pinned optional Playwright MCP runtime and expose browser session status, reset and close; verify missing-runtime and across-turn lifecycle tests.
- [x] 2.2 Register a fixed browser tool set through the official MCP adapter with controlled screenshot output; verify local navigation, interaction and denied unsafe tools.
- [x] 2.3 Add an owned project preview process with health, logs and stop; verify start, cancellation, expiry and restart behavior.
- [x] 2.4 Add a pinned optional WinApp CLI worker with Off, Selected and All windows scopes; verify handle/process revalidation and Windows fixture capture and interaction.

## 3. Shared authority and presentation

- [x] 3.1 Extend effective Chat setup, tool catalogue, authenticated session controls and helper inheritance; verify Ask/Full/Plan behavior and exact grants.
- [x] 3.2 Retain browser and window captures in the existing asset store and expose a read-only native `read_file` path in both Chat variants; verify provenance, access, deletion and no base64 event replay.
- [x] 3.3 Add compact browser/window controls, status and capture preview/Open in Chat and Library; verify keyboard, pointer and narrow-width use and generated-contract freshness.

## 4. End-to-end delivery

- [x] 4.1 Run isolated real-browser, real-Windows and real-vision fixture checks; record confirmed behavior and any unavailable prerequisite in the handover.
- [x] 4.2 Run backend default/integration, desktop build, contract freshness, OpenSpec validation and diff checks; fix failures, update handover and deliver the validated change.
