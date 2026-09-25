# Tasks

## 1. Contract and backend readiness

- [x] 1.1 Record the Chat, agent-model and managed-model behavior in OpenSpec deltas; verify `openspec validate chat-selection-readiness --strict`.
- [x] 1.2 Normalize Chat readiness overrides without losing supported explicit clears, report unsupported values as client errors, and reuse resolved setup; verify focused backend cases for the former 500 and read-only behavior.

## 2. Model selection and picker

- [x] 2.1 Keep the exact Chat model in new-chat, agent/project and saved-chat setup; choose only a sole healthy running fallback; verify both selection orders, multiple-running behavior and restoration regressions.
- [x] 2.2 Prefer the current named model configuration, make exact healthy reselection a no-op, and check alternatives on demand with unknown errors labelled honestly; verify picker regressions and no same-model start call.
- [x] 2.3 Defer picker-only option and thinking previews until open; verify opening a chat no longer sends all-profile readiness requests.

## 3. Chat lifecycle and latency

- [x] 3.1 Route active-turn Queue to backend queue admission and remove redundant blocking Send preview while keeping known current blockers visible; verify queue, cold model loading and draft-preservation regressions.
- [x] 3.2 Scope readiness to conversation, candidate and run lifecycle so terminal/switch races cannot retain an active warning; verify controlled late-response regressions.
- [x] 3.3 Render fetched saved content while registration and setup resolution settle concurrently, retaining selection-generation guards; verify rapid switching and interaction binding regressions.

## 4. Delivery

- [x] 4.1 Run backend default and integration suites, desktop build, applicable contract check, OpenSpec validation and diff check; fix any failures.
- [x] 4.2 Exercise the built Windows app with an isolated test chat, measure opening and Send admission, and verify exact healthy reselection does not request loading.
- [x] 4.3 Archive the completed OpenSpec change, refresh handover, and deliver the validated Git change; verify clean intended diff and local app readiness.
