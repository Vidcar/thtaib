## ADDED Requirements

### Requirement: Capture-free routine run observation
Existing run list/detail routes SHALL accept `view=operational` and return typed capture-free operational responses under existing authentication and identity rules. The desktop SHALL use this view for routine observation. Existing diagnostic reads SHALL remain available. No observation SHALL create or dispatch execution.

#### Scenario: Operational detail and list
- **WHEN** routine desktop observation requests operational run detail or lists
- **THEN** captures SHALL be absent while lifecycle, hierarchy, configuration, approvals and recovery information remain truthful.

### Requirement: Long tool runs retain timely native output
Plan and Work SHALL retain their current permissions and native ordering, actual tool results, cancellation, approvals and uncertain-effect recovery. A continuously mounted Chat SHALL keep successive turns, helper/tool transitions and refresh-equivalent content responsive with Browser viewing and attention polling active. Status SHALL reflect the actual phase rather than disguise delivery delay.

#### Scenario: Sustained real-model workload
- **WHEN** three uninterrupted real-model turns make at least 30 combined Browser/filesystem calls while the Browser rail and attention polling remain active, plus a Plan run uses repeated investigation tools
- **THEN** no growing event/render backlog SHALL develop
- **AND** model-stream completion SHALL follow provider completion within 2 seconds and local status/event delivery SHALL have p95 below 250 ms.
