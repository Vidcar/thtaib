## MODIFIED Requirements

### Requirement: ARCH-010 - Protect same-machine trust

Privileged `/v1` routes SHALL require the shared secret header. Missing tokens MUST return 401 and wrong tokens MUST return 403. `GET /health` MAY be public. CORS MUST NOT be treated as authorization, and unsupported remote backend access MUST NOT be enabled silently.

Desktop-granted backend authorization SHALL be restricted to the verified application requesting document/frame and owning WebContents at the exact loopback destination. Same-session untrusted content SHALL NOT inherit that authority. Electron main SHALL own validated HTTP(S) external-link opening and denial of untrusted windows/navigation, including redirects, while keeping sandboxing, context isolation and CSP intact.

#### Scenario: Privileged request authentication

- WHEN `/v1` is called without the header or with the wrong token
- THEN the backend MUST reject it with the corresponding authentication failure
- AND the renderer MUST NOT receive or store the shared secret.

#### Scenario: Desktop document replacement

- WHEN untrusted content attempts to open within or replace a trusted desktop document
- THEN navigation/window policy MUST deny it and backend credential injection MUST independently reject untrusted requesting frames
- AND an allowed window ID or null origin alone MUST NOT authorize backend access.
