# Spec Delta

## ADDED Requirements

### Requirement: API-055 - Show quiet live system-memory rings in the rail

The persistent 54px navigation rail SHALL show compact, fixed-geometry GPU-memory and system-RAM rings beneath Settings and above the separate service dot on every page. Labels and whole-number percentages SHALL remain readable. The rings SHALL have no hover menu, tooltip or click panel. Usage colour SHALL use the active theme's green through 50%, transition to warm amber at 80%, then to muted red at 95% and remain red above that. Missing readings SHALL appear as an empty grey ring with an em dash, never zero. A stale metric SHALL retain its last valid percentage and arc in grey independently of the other metric. Accessible descriptions SHALL distinguish current, stale and unavailable readings without announcing every update.

The authenticated read-only `GET /v1/system/resources` boundary SHALL expose reported GPU used/total/available memory, physical RAM total/available memory and separate GPU/RAM observation times and stale states. GPU percentages SHALL use reported used/total memory; RAM percentages SHALL use total minus available physical RAM. Multiple GPU capacities MUST NOT be combined; the compact GPU ring SHALL show the highest observed valid device percentage and name that device in its accessible description. Passive observation SHALL reuse the hardware observations available to Models without estimating, loading or reconfiguring a model, changing data, weakening authentication or blocking backend event processing.

The desktop SHALL observe every two seconds while visible, with at most one active request and a four-second request timeout. Hidden or unmounted observers SHALL cancel requests and polling; obsolete results SHALL NOT overwrite current readings. A reported failure or a successful reading older than ten seconds SHALL grey the affected metric immediately. Successful fresh readings SHALL restore its usage colour. Observation updates SHALL remain isolated from Chat rendering.

#### Scenario: Current readings across navigation
- **WHEN** current GPU and RAM readings are available while navigating pages or collapsing the chat list
- **THEN** both rings remain beneath Settings in the same 54px rail, with current percentages and theme colours, without menus or changes to the service dot.

#### Scenario: GPU fails while RAM continues
- **WHEN** GPU observation fails after a valid reading and RAM remains available
- **THEN** the GPU keeps its last percentage and arc in grey while RAM continues updating in its usage colour
- **AND** a later successful GPU observation restores its current colour.

#### Scenario: Missing or malformed observations
- **WHEN** no valid initial reading exists, a quantity is malformed, or GPU telemetry is unavailable
- **THEN** that metric remains unknown with an empty grey ring and em dash, and a valid independent RAM reading remains usable.

#### Scenario: Different NVIDIA devices
- **WHEN** several devices report different used-memory percentages
- **THEN** the GPU ring presents the highest observed valid device percentage with an accessible device identity and never presents their memory as one pool.

#### Scenario: Disposal and timeout
- **WHEN** the window is hidden, the component is removed, a request exceeds four seconds, or an obsolete response arrives after visibility changes
- **THEN** requests and polling are cancelled as appropriate, obsolete results cannot replace newer observations, and timeout/expired readings remain grey until recovery.

#### Scenario: Passive authenticated observation
- **WHEN** an authorized client requests resources with no model selected or loaded
- **THEN** hardware observations are returned without model estimation or loading
- **AND** missing or wrong desktop tokens remain rejected and Models retains its available-memory budget semantics.

#### Scenario: Scaled native presentation
- **WHEN** the built desktop is used in either theme, at high scaling or in a short window
- **THEN** Settings and destinations remain reachable, percentages including 100% fit their rings, and metric changes do not alter rail geometry or trigger transcript renders.
