# agents-workflows delta

## MODIFIED Requirements

### Requirement: WF-001 - Keep configuration links out of execution sequencing

Configuration links SHALL supply model/profile, tools, skills/memory, environment, access and execution policy to their owning node through explicit inheritance/overrides. Resolve actual records and policy per node, not one flattened global setup. A basic agent node SHALL also accept a reusable setup, supported explicit selections or documented shared defaults without separate nodes for every aspect. Preserve omitted versus explicitly empty tools and shared instruction/protection/context rules.

Workflow links SHALL define execution sequencing and actual typed data/artifact bindings; only they compile into executable flow. Backend validation SHALL check source/target role, stable port/direction, supported aspect/cardinality and required input/output paths, identifying the offending node/link/port. Diagnose disconnected requested executable nodes instead of omitting them. Inspectors SHALL show selected versions and inherited/overridden/effective values; later setup edits do not rewrite prior evidence.

#### Scenario: Mixed definition compile

- **WHEN** a definition mixes configuration and workflow links for several agents
- **THEN** configuration changes only the intended owner and never becomes an executable step or global flattened setup.

#### Scenario: Basic agent configuration

- **WHEN** an agent node selects a reusable setup with tools explicitly empty
- **THEN** it needs no configuration-node scaffolding and the executed node remains tools-off.

### Requirement: WF-002 - Make delegation and cycle ownership explicit

Workflow agent steps SHALL invoke the shared configured Deep Agents as named nested graphs with declared mapped inputs/outputs and await actual results. Native subagents remain child invocations of their owning step with intended model/tools/knowledge/access and no escalation. Each workflow run SHALL have a fresh root thread, compatible inherited checkpointing and separate invocation-private state/scratch. Only mapped inputs enter an agent and validated outputs return; private messages/loading caches do not silently merge into sibling state. Resume retains the root and invocation resources.

Exactly one owner, either outer LangGraph workflow or its agent step, SHALL control each review cycle. Do not duplicate an outer loop inside the harness. Planning/delegation/declared cycles must correspond to implemented upstream integrations, not assumptions or background run IDs reported as outputs.

#### Scenario: Review loop ownership

- **WHEN** an outer review loop contains a delegating agent step
- **THEN** the run hierarchy identifies one cycle owner and native children stay attributable without duplicating the cycle.

#### Scenario: Await nested result

- **WHEN** an agent node invokes the shared harness
- **THEN** downstream inputs receive its actual validated result only after completion, without leaking sibling private state.

## ADDED Requirements

### Requirement: WF-003 - Freeze portable definitions and public run inputs

The product SHALL save versioned serialisable workflows and compile registered implemented node kinds into actual executable LangGraph graphs. Definitions retain stable nodes/ports, mappings, supported declarative conditions and pattern configuration, with layout/viewport separate. An ordered metadata list or drawn edge is not execution; imported definitions cannot evaluate arbitrary code.

Each workflow SHALL declare a public typed input interface with labels, required/default values and authorised file/project references. Run forms validate inputs without node editing. Freeze workflow/subworkflow revisions, actual inputs/artifact versions and effective configuration for each run; draft/default edits cannot mutate active/paused execution. Older definitions receive explicit migration/validation outcomes.

Create/open/save/rename/duplicate/import/export/dependency-aware removal SHALL retain interfaces, layout, bindings and dependency references without credential values or executable code. Validate missing models/setups/profiles/integrations/revisions without auto-installation, substitution or grants. Shared retention/manual backups protect referenced history/assets. Save/import/restore MUST NOT start workflows or activate triggers; scheduling remains optional future work.

#### Scenario: Portable import

- **WHEN** a workflow is imported with unresolved dependencies
- **THEN** functional mappings/layout survive and missing dependencies are reported without installation, grants, execution or trigger activation.

#### Scenario: Run inputs and later edit

- **WHEN** a workflow starts and its draft/defaults are edited
- **THEN** the run retains its validated inputs and exact frozen revisions while the editor changes only future work.

### Requirement: WF-004 - Validate real typed handovers and structured agent results

Executable bindings SHALL identify actual source/target values and supported schemas, validated at runtime rather than by matching type names alone. Text/data, retained uploads/extracted documents, verified artifacts and permitted mutable project references SHALL retain provenance/access. Revalidate mutable references at use; immutable handovers retain snapshot/version identity. Missing required output is distinct from valid empty data and blocks dependent work unless explicit recovery handles it. Unknown schemas/capabilities stay unknown; known incompatibility is rejected.

Schema-output agent nodes SHALL use the shared selected schema and supported native/tool formatting strategy, forwarding only validated structured results. Ordinary text remains supported. No competing parser/agent or hidden formatting tool may bypass tools-off. JSON-looking answer text is not structured success, and schema validity alone is not semantic correctness or grounding.

#### Scenario: Missing versus empty

- **WHEN** a source node produces no required value or a schema-permitted empty value
- **THEN** runtime mapping blocks the missing value and accepts the legitimate empty value without inventing output.

#### Scenario: Structured agent handover

- **WHEN** an agent node declares an output schema
- **THEN** only the shared validated structured result reaches downstream ports under the node's actual tool policy.

### Requirement: WF-005 - Execute sequences and region-scoped branch joins

Sequence edges SHALL advance only after required outputs complete and validate. Exclusive conditions SHALL select declared targets with defined invalid/missing handling; unselected alternatives are skipped, not successful. Undeclared conditions or disconnected mandatory paths fail clearly.

Parallel branches SHALL retain per-invocation results and use explicit deterministic merge rules; conflicting writes fail rather than last-arrival-wins. A join SHALL activate once for the required completed branches of its intended activation/region, handling unequal path lengths and conditionally unselected alternatives. It must neither wait for an unselected path nor rerun because results arrive at different times. Missing/failed required values prevent normal join success.

#### Scenario: Exclusive branch

- **WHEN** a condition selects one alternative
- **THEN** only that route executes and unselected nodes are marked skipped.

#### Scenario: Unequal parallel paths

- **WHEN** required branches have different lengths and one alternative is not selected
- **THEN** the scoped join fires once after its required selected results, not early, repeatedly or after waiting forever for the excluded branch.

### Requirement: WF-006 - Keep authored approvals and typed input as distinct gates

An authored approval node SHALL present its own identified approve/reject decision and explicit routes. It remains independent of agent-tool approvals and MUST NOT be bypassed by session or Always allow tool grants. Resume addresses the exact root/node/invocation/interrupt identity and authored outcome.

User-input nodes SHALL request supported text, choice or authorised file/project values through shared typed interruption, validate schema/access and route values to the same node across restart. Questions are not tool-approval decisions and cannot confer unrelated access or credentials. Parallel authored approvals, tool decisions and input requests remain distinguishable.

#### Scenario: Standing tool grant

- **WHEN** a workflow reaches an explicit approval node while matching Always allow grants exist for tools
- **THEN** the authored gate still requires its own decision and follows its declared route.

#### Scenario: Typed input after restart

- **WHEN** a workflow resumes a file or choice question
- **THEN** the exact pending node receives schema/access-validated values rather than a generic approval response.

### Requirement: WF-007 - Execute registered data operations and shared direct integrations

The required deterministic catalogue SHALL include typed field selection and text formatting with explicit mappings. These nodes invoke no model and evaluate no arbitrary saved expression/code; validation errors remain attributable failures.

Direct integration nodes SHALL represent explicit user-authored operations on selected shared tools/connections with visible effects and declared policy. Revalidate at dispatch/resume, await actual adapter results and validate output mappings. Use the same approvals, cancellation and external-effect reconciliation as agent tools. A deliberately authored node has its own policy; no hidden node or neighbouring agent text grants authority or bypasses that agent's tools-off selection.

#### Scenario: Deterministic mapping

- **WHEN** a field-selection or formatting node receives invalid data
- **THEN** it fails with an attributable schema/mapping error without executing a model or arbitrary code.

#### Scenario: Direct action

- **WHEN** a saved integration node dispatches a mutating operation
- **THEN** current shared policy and real adapter completion govern its outputs, not adjacency to an agent node.

### Requirement: WF-008 - Execute declared loops and pinned reusable workflows

Loops SHALL declare carried state, condition, back-edge and exit with identified iterations and defined zero/one/multiple-iteration behaviour. Reject undeclared cycles; carried values must not depend on a child remembering a previous invocation. Report framework recursion safeguards as technical superstep limits, distinct from user loop iterations and optional budgets; add no arbitrary task/token cap.

Reusable-workflow nodes SHALL resolve a specific saved revision, validate its public interface and execute as nested graphs with separate invocation state and inherited recovery. Repeated calls and independent roots cannot accidentally share private messages/mutable state. Missing revisions and recursive references fail unless a supported explicit recursion contract exists. Frozen runs never follow future edits.

#### Scenario: Loop boundaries

- **WHEN** a declared loop exits immediately, after one iteration or after several
- **THEN** each case has correct carried outputs and distinct iteration evidence without relying on hidden child memory.

#### Scenario: Repeated reusable node

- **WHEN** the same saved workflow revision is called twice
- **THEN** each invocation has private state and frozen interfaces while sharing the proper root recovery owner.

### Requirement: WF-009 - Preserve independent outcomes and compatible exact recovery

Unhandled node failure SHALL block dependent missing outputs while useful independent branches may finish. Explicit recovery receives typed failures, not fabricated values. A required failed branch/join/output prevents normal overall success unless the authored recovery handles it; do not blanket-retry mutating integrations or entire agent steps.

Records/events SHALL identify root execution and each node/subworkflow/agent invocation, definition revision, node path, iteration and attempt. A canvas node ID is not sufficient repeated-invocation identity; multi-model workflows have actual per-invocation deployments rather than one fictitious model. Resume restores the saved root/definition/inputs/setup and revalidates restrictions. Incompatible compiler/node changes produce explicit recovery failure, not new semantics applied silently.

Resume exact pending interrupt IDs using distinct supported payloads for authored decisions, typed inputs, ordered tool approvals and MCP elicitation. Reject stale/duplicate decisions; preserve interruption control flow and make replayed wrappers safe. External effects require supported idempotency or reconciliation; uncertain outcomes block silent duplication. Checkpoints are neither exactly-once execution nor rollback.

#### Scenario: Independent branch survives

- **WHEN** one branch fails while another can still produce useful output
- **THEN** independent evidence survives, but missing required results prevent unqualified success.

#### Scenario: Compatible restart

- **WHEN** a paused repeated-node invocation resumes after backend restart
- **THEN** the same root/revision/iteration and exact interrupt are restored, or incompatibility is reported without applying new semantics.

#### Scenario: Unknown external effect

- **WHEN** a crash occurs after dispatch but before local acknowledgement
- **THEN** recovery reconciles or preserves uncertainty instead of replaying the mutating node.

### Requirement: WF-010 - Share admission and cancel only owned workflow work

All workflow model calls, nested children and direct operations SHALL reuse shared resource/project/lifecycle controls and Lab exclusion. Waiting on tools/children/humans must not hold inference permits needed by dependencies. Coordinate canonical project aliases/full conflicting edits; use safe handover or actionable waits for startup/residency conflicts, not silent replacement. Ordinary Chat and Workflows may coexist under verified admission outside Lab; unrelated workflows cannot start during a Lab batch.

Cancellation SHALL prevent further dispatch, remove queued owned work and propagate to active owned operations/handover. Retain partial validated outputs and unknown external effects without stopping unrelated sessions or claiming rollback. Restart reconciles orphaned invocation activity; shared restoration uses saved configuration/result identity without resubmission.

#### Scenario: Lab and workflow admission

- **WHEN** ordinary workflow work is requested during an exclusive Lab batch
- **THEN** shared admission blocks it with the Lab reason even when submitted outside the canvas.

#### Scenario: Cancel during external action

- **WHEN** a root is cancelled after some nodes finish and another effect is unresolved
- **THEN** owned dispatch stops, completed outputs survive and external uncertainty remains without harming unrelated work.

### Requirement: WF-011 - Make the canvas and inspectors reflect executable evidence

The existing Workflows surface SHALL provide create/open/save/run, public input form, setup/node/input/output inspectors, mapping controls and actionable validation focus. React Flow SHALL show labelled distinct configuration and execution/data ports with stable handle IDs persisted in edges. Immediate feedback reflects but does not replace backend validation. Preserve old Agent run history; non-executable placeholders and unimplemented media nodes cannot appear runnable.

Editor undo/redo, duplication with fresh node IDs, keyboard navigation, labelled controls and explicit unsaved handling or indicated autosave SHALL work. Undo changes drafts only, not executed effects. Import/export preserves functional mappings as well as appearance.

Shared events/snapshots SHALL show actual root/invocation starts, waits, approvals, results, skips, failures and cancellations, including each loop iteration. Nested activity is not invented authored canvas nodes; configuration bindings are not running tasks. Inspect actual mapped values/provenance/schema errors under privacy controls. Stream exhaustion, job IDs or assistant text do not prove success. Reopening restores consistent evidence without duplicate/cross-run events.

#### Scenario: Edit and reopen

- **WHEN** a user edits, duplicates, saves and reopens a workflow
- **THEN** functional bindings and stable ports survive, new nodes have fresh IDs, and editor undo does not claim to reverse effects.

#### Scenario: Inspect executed loop

- **WHEN** a workflow loops and delegates while configuration links remain attached
- **THEN** the UI shows actual iteration/nested evidence and mapped values, not running configuration nodes or fabricated canvas steps.
