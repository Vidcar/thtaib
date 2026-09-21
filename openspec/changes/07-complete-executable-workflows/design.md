# Design: Complete executable visual Workflows

## Technical Approach

Extend `agents/definition_compiler.py`, existing agent-run services and the React Flow surface; do not create another product or make an ordered metadata list count as execution. Persist serialisable application definitions and compile supported nodes/edges into a real LangGraph StateGraph. Registry definitions remain the common source for types, validation, controls and execution. Layout is editor metadata, not executable authority.

Resolve configuration per owning node with the shared setup resolver. A normal agent node can select a reusable agent setup without seven compulsory configuration nodes. Preserve distinct configuration links and execution/data bindings, explicit empty tools, protected instructions and actual deployment context. Freeze definition/subworkflow revisions and inputs for each run.

Await configured Deep Agents as nested graphs with inherited root recovery, invocation-private state/scratch and explicitly mapped inputs/outputs. Use the shared structured-output contract where a schema is requested. Do not flatten child messages into workflow state or return an application job ID as node output. Direct integrations await the same adapters and permissions as agent tools.

Compile conditional routing, region-scoped parallel joins, deterministic reducers and explicit loop state using supported LangGraph mechanisms. Verify unequal branches and conditional exclusions: a generic graph-wide deferred node is not proof of a correct local join. Reject ambiguous merges/undeclared cycles rather than introducing arbitrary evaluator code. Reusable workflow nodes pin revisions and reject recursive references without a supported recursion contract.

## Recovery and delivery

Persist root and invocation identity, including node path/iteration/attempt; use public checkpoint/interrupt APIs and exact typed resume. Side effects need adapter idempotency or reconciliation, not an exactly-once claim from checkpoints. Shared admission/project coordination, Lab exclusion, cancellation and residency apply to every node path. Preserve useful independent branches on failure while blocking missing dependent outputs.

React Flow edits the same serialisable definitions and layout; only backend validation/compilation and LangGraph execute the frozen workflow graph. Use the verified shared SDK observation boundary to present scoped run/node/tool state, not to author graph logic, validate execution authority or replace LangGraph. Existing Agent run history remains accessible; the intended area name is Workflows without a broad code/data rename. Media nodes become runnable only when change 08 supplies verified adapters. No schedule/trigger activation is implied by save, import or restore.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
