# Environments and tools

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Give agents real filesystem, shell, browser and graphical capability in declared environments, with the same permissions and approvals on every path an action can take.

## Boundaries and ownership

Application-managed environments and adapters provide the capabilities; LangChain exposes tools to Deep Agents. MCP standardises discovery and invocation through official `langchain.mcp.MCPAdapter` (`langchain[mcp]`, FastMCP underneath). The application does not remake an MCP host and does not speak the protocol itself. Neither MCP nor a working directory supplies isolation. The environment manager provisions workers, maps project storage and tears down; Compose manages container services; adapters own the jobs inside them. Source: [experience boundaries](../sources/README.md#experience-boundaries), [tool orchestration](../sources/README.md#agents-and-workflows), [infrastructure](../sources/README.md#application-infrastructure).

## Interfaces and contracts

Environment identity and location, access configuration, tool capability requirements and job invocation/result shapes are registry definitions ([registry](registry.md)). MCP server records are application-owned (JSON under `state\mcp-servers\` until [OQ-017](../open-questions.md#oq-017) converges storage): slug, transport (`stdio` command/args or `http` URL), pin, enabled flag, secret refs, tool allow/deny, approval class, session policy. They are not the unimplemented integration registry and not a second tool bus. Each adapter declares reconnect, resume, restart, cancellation, snapshot support and external side effects. Connect/provision and start-job are different operations; a cancel request and a confirmed cancellation are different facts. Secrets are never stored in the server JSON.

## Behaviour

- **Today.** The enabled catalogue is visibility tools (`echo`, `time_now`), Deep Agents filesystem tools bound to project storage, and the host-shell `execute` tool when a project (cwd) is bound. No MCP client, MCP server record, browser, graphical, ComfyUI, MCP-Apps or interpreter path exists. Recorded-tool replay in the Lab attaches no live backend.
- **Intended.** Filesystem tools target project storage. Shell and later isolated browser/graphical tools require a connected worker in a declared environment that explains where it runs, which files it exposes, what it may install and what isolates it. Chat browser access in this slice is the Playwright MCP product server ([ENV-007](#env-007)), not that isolated worker.
- **MCP expansion (specified, not implemented).** MCP is an optional extra tool source, not the default bus ([OQ-009](../open-questions.md#oq-009)). A run that names `mcp_server_ids` resolves application server records, opens official `MCPAdapter`, calls `list_tools()`, namespaces tools as `{slug}_{tool}`, and passes them into the existing `create_deep_agent(tools=)` list. Omit the field and no adapter starts. Core Chat must still run ([ARCH-007](../architecture.md#arch-007)). First product servers: `browser` (pinned `@playwright/mcp` over stdio, session held for the run, isolated profile and outputs under product data / harness scratch) and `github` (official remote `https://api.githubcopilot.com/mcp/` with a PAT bearer). Adding a third server is a new record on the same path. `interrupt_on` composes with host-shell: MCP annotations `read_only_hint` / `destructive_hint` plus the record's approval class. Elicitation resumes with `Command(resume={"responses": …})`, distinct from host-shell `{"decisions": …}`. Project is not required for `browser` or `github`. Fail closed on missing record, connect/`list_tools` failure, missing stdio runtime, missing secret, or a name collision with a first-class tool. Recorded-tool attaches no live MCP. MCP Apps remain [ENV-005](#env-005). Sources consulted 2026-09-20: [LangChain MCP](https://docs.langchain.com/oss/python/langchain/mcp), [connections](https://docs.langchain.com/oss/python/langchain/mcp/connections), [tools](https://docs.langchain.com/oss/python/langchain/mcp/tools), [auth](https://docs.langchain.com/oss/python/langchain/mcp/auth); pinned `langchain==1.4.2`; [Playwright MCP](https://github.com/microsoft/playwright-mcp); [GitHub MCP Server](https://github.com/github/github-mcp-server).
- **First worker environment: Windows host shell with approvals, on Deep Agents `permissions=` / `interrupt_on=` and `LocalShellBackend`; WSL and Docker later** (product owner decision, 2026-09-19). Commands run on the host through `LocalShellBackend(root_dir=project, virtual_mode=True, inherit_env=True)` **only when `execute` is presented**. A project-bound run that does not present `execute` keeps `FilesystemBackend` and must not run a host shell. `interrupt_on` is installed whenever that sandbox default is attached. `virtual_mode` does not restrict `execute`. There is no isolation and the run record / desktop say so. A home-directory cwd is never invented: `execute` is absent and `shell_requires_project` (400) if requested without a bound project. Auto-allow is a small read-only prefix list (`echo`, `dir`, `ls`, `pwd`, `whoami`, `hostname`, `ver`, `type`, `where`, `which`, `Get-*` list/read helpers, and `git status|log|diff|branch|show|rev-parse`) with no shell metacharacters; everything else pauses. Human approval uses Deep Agents `interrupt_on=` / LangGraph resume (`Command(resume={"decisions": [...]})`); the application does not invent a second approvals inbox ([OQ-011](../open-questions.md#oq-011)). `permissions=` are route-scoped deny rules on unused `/large_tool_results/denied/**`, `/conversation_history/denied/**` and `/retrieved/denied/**` prefixes — Deep Agents 0.7.15 `FilesystemMiddleware` refuses project-wide `permissions=` when the composite default is a sandbox (`LocalShellBackend`). Chat and Agent-run share this policy (ENV-002 for the implemented paths). WSL, Linux, Docker and remote workers come later. Sources consulted 2026-09-19: [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends), [human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop), [permissions](https://docs.langchain.com/oss/python/deepagents/permissions); installed `deepagents==0.7.15` (`backends/local_shell.py`, `middleware/filesystem.py`).
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

<a id="env-007"></a>
### ENV-007: Expand tools through registered MCP servers

Discover and invoke tools from application-registered MCP servers through official `langchain.mcp.MCPAdapter`. Do not remake an MCP host and do not replace the first-class tool bus. Selected ≠ connected ≠ tools applied. Disabled or omitted servers leave core Chat running. A third server uses the same record and adapter path. First product servers are `browser` (official Playwright MCP) and `github` (official GitHub remote MCP). MCP is not isolation; host-shell remains the first worker. Interactive MCP Apps are [ENV-005](#env-005), not this requirement.

**Acceptance:** Enable a registered server, start Chat, and confirm discovered tools arrive through `MCPAdapter.list_tools` into `create_deep_agent`. Omit or disable servers and confirm core Chat still runs. Exercise a browser navigate/snapshot and a GitHub read; a write or destructive MCP call pauses on the existing interrupt path. A missing runtime or secret fails closed. Register a third server record and confirm it uses the same path. Recorded-tool attaches no live MCP.

## Status and evidence

Rows ENV-001…007 in [the catalogue](../catalog.json). ENV-001 and ENV-002 are `built` for the host-shell path (Chat and Agent-run). David-PC UAT on 2026-09-19 covered Chat HTTP approve, deny, and `shell_requires_project` at `8887f9f` ([evidence](../evidence/2026-09-19-david-pc-host-shell.md)); not `verified` — acceptance still lacks other invocation paths, Electron, and the durable Approvals inbox ([OQ-011](../open-questions.md#oq-011)). ENV-003…006 are unstarted. ENV-007 is specified (`planned`); no code, no tests, no evidence. WSL/Docker are out of scope.

## Open questions

[OQ-003](../open-questions.md#oq-003) later environments and remaining host access (network, credentials, install rights); browser-via-MCP does not close the isolated browser worker; [OQ-004](../open-questions.md#oq-004) effect acknowledgement; [OQ-009](../open-questions.md#oq-009) remaining optional integrations (interpreter, MCP Apps, rubric, voice) after the MCP bus question was settled; [OQ-011](../open-questions.md#oq-011) durable Approvals inbox (the host-shell and MCP approval interrupts are the mechanism, not the inbox).
