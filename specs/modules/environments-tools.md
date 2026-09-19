# Environments and tools

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Give agents real filesystem, shell, browser and graphical capability in declared environments, with the same permissions and approvals on every path an action can take.

## Boundaries and ownership

Application-managed environments and adapters provide the capabilities; LangChain exposes tools to Deep Agents; MCP standardises discovery and invocation through the LangChain MCP integration and the official MCP Python SDK. Neither MCP nor a working directory supplies isolation. The environment manager provisions workers, maps project storage and tears down; Compose manages container services; adapters own the jobs inside them. Source: [experience boundaries](../sources/README.md#experience-boundaries), [tool orchestration](../sources/README.md#agents-and-workflows), [infrastructure](../sources/README.md#application-infrastructure).

## Interfaces and contracts

Environment identity and location, access configuration, tool capability requirements and job invocation/result shapes are registry definitions ([registry](registry.md)). Each adapter declares reconnect, resume, restart, cancellation, snapshot support and external side effects. Connect/provision and start-job are different operations; a cancel request and a confirmed cancellation are different facts.

## Behaviour

- **Today.** The enabled catalogue is visibility tools (`echo`, `time_now`), Deep Agents filesystem tools bound to project storage, and the host-shell `execute` tool when a project (cwd) is bound. No browser, graphical, ComfyUI, MCP-Apps or interpreter path exists. Recorded-tool replay in the Lab attaches no live backend.
- **Intended.** Filesystem tools target project storage. Shell, browser and graphical tools require a connected worker in a declared environment that explains where it runs, which files it exposes, what it may install and what isolates it.
- **First worker environment: Windows host shell with approvals, on Deep Agents `permissions=` / `interrupt_on=` and `LocalShellBackend`; WSL and Docker later** (product owner decision, 2026-09-19). Commands run on the host through `LocalShellBackend(root_dir=project, virtual_mode=True, inherit_env=True)` **only when `execute` is presented**. A project-bound run that does not present `execute` keeps `FilesystemBackend` and must not run a host shell. `interrupt_on` is installed whenever that sandbox default is attached. `virtual_mode` does not restrict `execute`. There is no isolation and the run record / desktop say so. A home-directory cwd is never invented: `execute` is absent and `shell_requires_project` (400) if requested without a bound project. Auto-allow is a small read-only prefix list (`echo`, `dir`, `ls`, `pwd`, `whoami`, `hostname`, `ver`, `type`, `where`, `which`, `Get-*` list/read helpers, and `git status|log|diff|branch|show|rev-parse`) with no shell metacharacters; everything else pauses. Human approval uses Deep Agents `interrupt_on=` / LangGraph resume (`Command(resume={"decisions": [...]})`); the application does not invent a second approvals inbox ([OQ-011](../open-questions.md#oq-011)). `permissions=` are route-scoped deny rules on unused `/large_tool_results/denied/**` and `/conversation_history/denied/**` prefixes — Deep Agents 0.7.15 `FilesystemMiddleware` refuses project-wide `permissions=` when the composite default is a sandbox (`LocalShellBackend`). Chat and Agent-run share this policy (ENV-002 for the implemented paths). WSL, Linux, Docker and remote workers come later. Sources consulted 2026-09-19: [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends), [human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop), [permissions](https://docs.langchain.com/oss/python/deepagents/permissions); installed `deepagents==0.7.15` (`backends/local_shell.py`, `middleware/filesystem.py`).
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

Rows ENV-001…006 in [the catalogue](../catalog.json). ENV-001 and ENV-002 are `built` for the host-shell path (Chat and Agent-run); not `verified` until David-PC UAT. ENV-003…006 are unstarted. WSL/Docker are out of scope.

## Open questions

[OQ-003](../open-questions.md#oq-003) later environments and remaining host access (network, credentials, install rights); [OQ-004](../open-questions.md#oq-004) effect acknowledgement; [OQ-009](../open-questions.md#oq-009) MCP as default bus, interpreter and MCP Apps; [OQ-011](../open-questions.md#oq-011) durable Approvals inbox (the host-shell approval interrupt is the mechanism, not the inbox).
