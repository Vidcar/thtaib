# Decision context

Retained rationale for decisions smaller than an ADR. Current behavior belongs in [module contracts](../README.md), status and evidence in [the catalogue](../catalog.json), and working rules in [AGENTS.md](../../AGENTS.md). Git history preserves the implementation diary and superseded process instructions.

## 2026-09-20 — Integration choices

David requested Chat-first memory durability and optional MCP integration. Pinned-stack research selected the existing framework mechanisms rather than additional execution or storage owners:

- **Memory and skills:** official Deep Agents `memory=` / `skills=` replace prompt-body concatenation. Knowledge remains the durable owner; memory write-through avoids turning harness scratch or `StoreBackend` into a second store. The policy is in [STATE-005](../modules/state-recovery.md#state-005), harness integration in [AGT-004](../modules/agents-workflows.md#agt-004), and version-specific findings in [upstream references](../sources/upstream.md). Implementation and live evidence are distinct.
- **Retrieval:** David accepted v1 RAG only if supported LangChain components deliver it with little custom code. A per-run derived index and retrieve-and-offload avoid a persistent vector-store service or another inference stack ([STATE-006](../modules/state-recovery.md#state-006)). [David-PC retrieval evidence](../evidence/2026-09-20-david-pc-retrieval.md) records the actual live scope and limitations.
- **MCP:** official `langchain.mcp.MCPAdapter` on the pinned LangChain version extends the same harness and approval mechanism. Browser and GitHub are the first requested server records; they do not create isolation or an MCP Apps host. [ENV-007](../modules/environments-tools.md#env-007) owns the contract; [adapter research](../sources/upstream.md#langchain-mcp) preserves upstream source links and pin-specific findings.

## 2026-09-19 — Execution and state boundaries

- **Project-free Chat and harness scratch:** [PR #85](https://github.com/Vidcar/thtaib/pull/85) addressed David's request for Chat without a project. CompositeBackend routing preserves `/` as the user's project path while keeping framework internals under product data. The alternative upstream `/workspace/` remount would change existing file paths; [agents and workflows](../modules/agents-workflows.md#behaviour) retains that rationale and the routing contract.
- **First worker:** David chose the Windows host shell with framework approvals before isolated WSL/Docker workers. `LocalShellBackend` attaches only when shell execution is presented; a cwd is not isolation. [Environments and tools](../modules/environments-tools.md#behaviour) owns policy and framework limitations. [Host-shell UAT](../evidence/2026-09-19-david-pc-host-shell.md) records HTTP approval/denial and the remaining Electron/cancellation evidence gaps.
- **Tiny-model smoke:** [PR #82](https://github.com/Vidcar/thtaib/pull/82) added a real runtime path to distinguish plumbing evidence from model capability. Current tiers and required checks are in [commands](../commands.md), with verification rules in [verification](../verification.md). Historical CI instructions here do not govern branch protection.

Architectural choices for [shared contract generation](ADR-0002-contract-authoring.md), [legacy Builder chrome](ADR-0003-builder-v1-chrome.md), [specification adoption](ADR-0004-slim-specification-pack.md) and [application record storage](ADR-0005-application-record-storage.md) retain their rationale in their ADRs. Closed defects and regression links remain in [deviations](../deviations.md).
