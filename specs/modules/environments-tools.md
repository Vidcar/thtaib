# Environments and tools

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Give agents real filesystem, shell, browser and graphical capability in declared environments, with the same permissions and approvals on every path an action can take.

## Boundaries and ownership

Application-managed environments and adapters provide the capabilities; LangChain exposes tools to Deep Agents; MCP standardises discovery and invocation through the LangChain MCP integration and the official MCP Python SDK. Neither MCP nor a working directory supplies isolation. The environment manager provisions workers, maps project storage and tears down; Compose manages container services; adapters own the jobs inside them. Source: [experience boundaries](../sources/README.md#experience-boundaries), [tool orchestration](../sources/README.md#agents-and-workflows), [infrastructure](../sources/README.md#application-infrastructure).

## Interfaces and contracts

Environment identity and location, access configuration, tool capability requirements and job invocation/result shapes are registry definitions ([registry](registry.md)). Each adapter declares reconnect, resume, restart, cancellation, snapshot support and external side effects. Connect/provision and start-job are different operations; a cancel request and a confirmed cancellation are different facts.

## Behaviour

- **Today.** The enabled catalogue is visibility tools (`echo`, `time_now`) and Deep Agents filesystem tools bound to project storage. No shell, browser, graphical, ComfyUI, MCP-Apps or interpreter path exists. Recorded-tool replay in the Lab attaches no live backend.
- **Intended.** Filesystem tools target project storage. Shell, browser and graphical tools require a connected worker in a declared environment that explains where it runs, which files it exposes, what it may install and what isolates it.
- **First worker environment: Windows host shell with approvals** (product owner decision, 2026-09-19). Commands run on David's machine through Deep Agents `LocalShellBackend`; access rules use Deep Agents `permissions=` and human approval uses `interrupt_on=`, not a parallel application mechanism. The surface shows what is auto-allowed, what paused for approval and what was denied, and records each decision on the run. The host shell provides no isolation and the surface says so. WSL, Docker and remote workers come later as further declared environments under the same policy model.
- **Policy.** Autonomy and access are independent. The selected permissions and approval rules are enforced in tools and workers for direct agent tools, workflow adapters, interpreter calls and interactive panels alike; no path gains rights by bypassing the visible Chat.
- **Recovery.** Adapters record unresolved side effects and never replay work with an unknown outcome. Snapshot support is declared, never assumed.

## Requirements

<a id="env-001"></a>
### ENV-001: Execute against the declared real environment

Filesystem tools target project storage. Shell, browser and graphical tools require connected workers. Explain execution location, exposed files, installation rights and isolation. A working directory is not a security boundary.

**Acceptance:** Edit a real project file, run a command and inspect a working result in the declared environment. Check that displayed paths/access correspond to the actual worker, not conversation-state files.

<a id="env-002"></a>
### ENV-002: Preserve policy across every invocation path

Separate autonomy from access. Enforce the selected permissions and approval rules in tools/workers for direct agent tools, workflow adapters, interpreter calls and interactive panels. No path obtains extra rights merely because it bypasses the visible chat interaction.

**Acceptance:** Attempt the same permitted and prohibited action through each implemented invocation path. Confirm equivalent policy outcomes, approvals and child-run records.

<a id="env-003"></a>
### ENV-003: Declare recoverability and cancellation truthfully

Adapters declare reconnect, resume, restart and cancellation behaviour. Record unresolved side effects and do not silently replay work with an unknown outcome. Snapshot support is explicit, not assumed.

**Acceptance:** Interrupt a real external job around its side-effect boundary, reconnect and cancel. Verify confirmed, failed and unknown outcomes are distinguished and no blind replay occurs.

<a id="env-004"></a>
### ENV-004: Reuse the creative job adapter

The ComfyUI adapter submits jobs, tracks progress and retrieves artifacts. The same adapter serves agent tools and LangGraph nodes rather than implementing two different job-control paths.

**Acceptance:** Invoke a representative creative job through both entry points and compare job ownership, progress, cancellation policy and artifact references.

<a id="env-005"></a>
### ENV-005: Host interactive tools without desktop privilege bypass

MCP Apps requires application host support, sandboxed rendering and permission-controlled tool messaging. Panels inherit run context and approvals; ordinary MCP connectivity is insufficient. Preserve standard tool results when an interactive interface is unavailable.

**Acceptance:** Exercise a panel's allowed/denied tool actions and unavailable-UI fallback. Verify the panel cannot directly obtain privileged desktop access.

<a id="env-006"></a>
### ENV-006: Keep interpreter orchestration separate from project shell

Treat the beta Deep Agents interpreter integration as a separate optional tool-orchestration capability. Each underlying tool call retains permissions, approvals, cancellation and child-run logging. Bulk code execution is not permission to bypass those controls.

**Acceptance:** Run a small tool-composition program with mixed allowed/denied operations and cancellation. Verify individual calls remain attributable and project shell policy is unchanged.

## Status and evidence

Rows ENV-001…006 in [the catalogue](../catalog.json). Only filesystem tools exist; ENV-002…006 are unstarted.

## Open questions

[OQ-003](../open-questions.md#oq-003) host-shell approval flow, path and command validation, and later environments; [OQ-004](../open-questions.md#oq-004) effect acknowledgement; [OQ-009](../open-questions.md#oq-009) MCP as default bus, interpreter and MCP Apps; [OQ-011](../open-questions.md#oq-011) durable Approvals inbox (the host-shell approval interrupt is the mechanism, not the inbox).
