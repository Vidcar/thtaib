# Spec Delta

## ADDED Requirements

### Requirement: ENV-027 - Test web pages in an owned browser

Work-mode Chat with or without a project SHALL offer an optional, separately authorized browser through the registered tool integration. The browser SHALL use an isolated conversation session, expose page structure and bounded screenshots, and keep its state across turns until reset, close, expiry or worker loss. It SHALL permit local development URLs without changing the public page reader's private-address policy. The application SHALL report the browser's actual destination, access and session loss; it MUST NOT expose unrestricted worker code, page-defined tools, arbitrary capture paths or the person's ordinary browser profile through this capability. A project-bound preview process SHALL have owned start, health, logs and stop behavior under the existing shell approval policy.

#### Scenario: Test a local page over several turns
- **WHEN** an authorized project Chat starts a preview and opens its local URL, then continues in another turn
- **THEN** the same browser session can inspect, interact and capture the page while the preview owner and destination remain visible.

#### Scenario: Browser worker is absent or lost
- **WHEN** the optional worker is unavailable or its process exits
- **THEN** ordinary Chat remains usable, the session reports unavailable or lost, and no browser action is silently replayed.

### Requirement: ENV-028 - Control only the configured Windows window scope

Work-mode Chat SHALL offer optional Windows window tools with Off, Selected window and All windows access. Selected window SHALL bind calls to an explicitly chosen live window and revalidate its identity. All windows SHALL require an explicit revocable conversation grant. Inspection, interaction and window or element capture SHALL pass through typed tools and the existing approval policy; raw worker command execution MUST NOT become agent authority. Unavailable, elevated or stale targets SHALL fail visibly.

#### Scenario: Selected window remains narrow
- **WHEN** a selected-window Chat requests inspection or input against a different or recycled window handle
- **THEN** the worker refuses the call without interacting with that window.

#### Scenario: Broader access is deliberate
- **WHEN** the person enables All windows for one conversation
- **THEN** its agent can list and target open windows until revocation or restart, while other conversations keep their own narrower access.
