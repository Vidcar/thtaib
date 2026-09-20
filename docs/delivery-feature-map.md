# Delivery next path

[The vision](../thtaib-vision.md) defines product intent; [module contracts](../specs/README.md) define acceptance; [the catalogue](../specs/catalog.json) owns status and evidence.

## Next path

1. **Repository cleanup (packet 01):** establish one current vision, concise engineering references and remove demonstrably unused scaffolding. Preserve real behavior and its regression coverage.
2. **Baseline repairs (packet 02):** address the separately scoped Models/Chat baseline defects before expanding features. Cleanup does not authorize those behavioral changes.
3. **Later product delivery:** build on dependable model configuration and Chat with capability evidence, project tools and durable memory, then Lab, Workflows and optional integrations. These remain intent, not extra tasks in the cleanup packet.

Keep model inventory, bundle validation, process ownership, permissions and the shared harness intact. Capability results must identify the exact setup; unknown is not incompatible and tiny-model smoke is plumbing, not capability evidence ([verification](../specs/verification.md)).

Workflows (existing **Agent run / Builder** terminology) retains the graph and shared-agent contracts in [WF-001/002](../specs/modules/agents-workflows.md#wf-001). Voice, MCP, plugins, media generation and future container integrations extend shared services; they are not prerequisites for the local model and Chat path. Remaining metadata migration follows [ADR-0005](../specs/decisions/ADR-0005-application-record-storage.md) and [OQ-017](../specs/open-questions.md#oq-017), without becoming a gate for that path.
