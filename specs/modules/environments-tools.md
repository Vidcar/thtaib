# Environments and tools

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Application-managed environments and adapters provide real filesystem, shell, browser and graphical capabilities. LangChain exposes tools to Deep Agents; MCP standardises discovery/invocation. Use the source's LangChain MCP integration and official MCP Python SDK for enabled tools and application-owned servers. Neither MCP nor a working folder supplies isolation. Source: [user control boundaries](../sources/README.md#experience-boundaries), [tool orchestration](../sources/README.md#agents-and-workflows), and [application infrastructure](../sources/README.md#application-infrastructure).

## Public contracts and collaboration

Define environment identity/location, access configuration, tool capability requirements and job invocation/result information through the registry. The environment manager provisions workers, maps project storage and tears down resources. Compose manages container services; adapters own jobs within them. Model inference retains the model manager/runtime ownership defined in [models](models.md); the source does not fix its physical placement relative to workers.

Windows, WSL, Linux, Docker and remote workers are supported execution choices in the vision, not a claim that every adapter or isolation feature has been implemented on each. Declare and test actual support.

## Lifecycle and failure

Each adapter declares reconnect, resume, restart, cancellation, snapshot support and external side effects. Connect/provision and start-job are different operations. A cancellation request and confirmed cancellation are different facts. Resolve precise worker protocols and authority before host shell execution; see the open questions below.

## Requirements and acceptance checks

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

Treat the source's beta Deep Agents interpreter integration as a separate optional tool-orchestration capability. Each underlying tool call retains permissions, approvals, cancellation and child-run logging. Bulk code execution is not permission to bypass those controls.

**Acceptance:** Run a small tool-composition program with mixed allowed/denied operations and cancellation. Verify individual calls remain attributable and project shell policy is unchanged.

## Unresolved details

[OQ-003](../open-questions.md#oq-003) blocks real worker access until provisioning, isolation, identities and permissions are defined; it is also the tool sandbox-isolation question, and MCP is not isolation. [OQ-004](../open-questions.md#oq-004) covers effect acknowledgement/recovery. [OQ-009](../open-questions.md#oq-009) covers optional interpreter and interactive-host details and whether MCP is the default tool bus or optional.

Current harness tools are visibility-only (`echo`, `time_now`) under [AGT-005](agents-workflows.md#agt-005). Deep Agents filesystem tools that target project storage for Chat are [STATE-002](state-recovery.md#state-002) and are in flight on [Issue #22](https://github.com/Vidcar/thtaib/issues/22). That is not a worker-isolation decision and does not reopen this module as a second sandbox owner. ComfyUI, MCP Apps and interpreter orchestration remain unimplemented.
