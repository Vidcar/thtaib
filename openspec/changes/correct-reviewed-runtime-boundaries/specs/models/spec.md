## MODIFIED Requirements

### Requirement: MOD-007 - Pin and observe managed runtime honestly

Managed runtime installation SHALL use the supported pinned llama.cpp runtime and verify matching archives before reuse. NVIDIA absence on the supported Windows CUDA path SHALL be a clear error, not a silent CPU fallback. Runtime flags SHALL be produced through pin-aware settings mapping; there MUST be no raw command-string escape hatch.

Absent an explicit saved or requested parallel setting, managed inference SHALL default to one active native request so a full-context request cannot compete with other requests for the same unified KV pool. llama.cpp SHALL own request queueing. The resolved setting SHALL identify Workbench default provenance; explicit native Auto and positive parallel counts SHALL remain exact. Existing loaded snapshots SHALL retain their historical effective settings until normal coordinated reload.

#### Scenario: Runtime pin and settings preview

- WHEN startup controls are previewed and a managed server is started
- THEN invalid, retired, or unknown controls MUST fail before spawn
- AND requested launch settings MUST remain distinguishable from observed server context and generation defaults.

#### Scenario: Default native request queue

- **WHEN** a managed setup omits parallelism and several chats or helpers request inference
- **THEN** resolution and preview select one active slot with Workbench provenance, and the engine queues the other requests without reducing advertised per-request context or generation allowance
- **AND** explicit Auto or another positive count remains unchanged, while a previously loaded four-slot snapshot is not relabelled as one slot.
