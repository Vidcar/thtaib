## MODIFIED Requirements

### Requirement: API-008 - Preserve terminal Chat hydration

The desktop SHALL reconcile upstream incremental projections and the persisted readable conversation by stable identity. Completed replies SHALL remain visible after final hydration. Optimistic user input, completed messages and tool results MUST NOT duplicate or disappear. Thread switches SHALL dispose the old observation and MUST NOT apply late frames or hydration to the new selection. Readable archive history MUST NOT be shortened to match compacted execution context.

The selected conversation and transport binding SHALL remain coherent during registration. Every selection-sensitive asynchronous result SHALL check selection generation and identity, including hydration, cancellation, creation, registration, command acknowledgement and errors. Pending input/configuration SHALL belong to its originating conversation/thread and draft identity. Acknowledgement SHALL clear only the submitted draft. Navigation SHALL neither retarget nor repeat an accepted command and SHALL NOT cancel backend execution.

#### Scenario: Final reply remains visible

- WHEN a real desktop Chat turn completes
- THEN its reply MUST have appeared incrementally before completion and MUST remain visible without reopening
- AND reopening MUST restore the saved transcript, selected/applied setup and project binding.

#### Scenario: Late old-thread completion

- WHEN the user selects a fresh conversation while the prior run continues
- THEN old-thread frames and completed hydration MUST NOT contaminate the new conversation
- AND the prior run MUST remain observable when revisited.

#### Scenario: Deferred hydration and cancellation across navigation

- WHEN A's terminal hydration or cancellation resolves after selecting B or New, including navigating away and back to A
- THEN the old result MUST NOT change current selection, draft, error state or transport
- AND revisiting A MUST show its own durable outcome.

#### Scenario: Atomic registration and submission ownership

- WHEN B's conversation fetch completes while registration is pending and A emits another frame
- THEN no rendered binding MUST combine B with A's transport or run
- AND deferred create/register/submit completion MUST NOT send input or configuration to a newer selection, duplicate an accepted run or clear newer draft text.

### Requirement: API-009 - Keep desktop shared secret out of renderer

The backend SHALL create the same-machine shared secret under product state on first use. Electron main SHALL inject the token for loopback backend requests. The sandboxed renderer SHALL use context isolation, no Node integration, and MUST NOT hold the shared secret. The backend SHALL bind loopback only.

Token injection SHALL require the exact backend destination and a verified trusted application document/frame belonging to its owning WebContents. WebContents identity alone or an opaque null origin SHALL NOT establish trust. Missing, destroyed, navigated or untrusted frames SHALL fail closed. Electron main SHALL deny untrusted windows and document navigation, including redirects, and resolve and validate deliberate external links before opening HTTP(S) targets in the system browser. File and custom schemes SHALL NOT gain external execution authority; relative, fragment and protocol-relative links SHALL be handled explicitly without prefix-based trust decisions.

#### Scenario: Renderer request

- WHEN the renderer initiates a privileged backend request
- THEN Electron main MUST add the shared-secret header
- AND the renderer MUST NOT expose or store that secret.

#### Scenario: External Markdown navigation

- WHEN a user activates an HTTP(S), relative or protocol-relative Markdown link
- THEN main-process URL validation MUST control any system-browser opening
- AND no untrusted in-app window or redirected document MUST inherit desktop privileges.

#### Scenario: Same-session untrusted requests

- WHEN an untrusted window/frame or a replacement document in a formerly trusted window requests the backend
- THEN the receiver MUST NOT receive the application-granted token, regardless of CORS response visibility
- AND genuine development and packaged application command, state/history, subscription and cancellation requests MUST retain authenticated access.
