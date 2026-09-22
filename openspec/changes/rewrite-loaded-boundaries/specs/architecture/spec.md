# Spec Delta

## MODIFIED Requirements

### Requirement: ARCH-002 - One owner for execution

The application SHALL use llama.cpp for supported inference, Deep Agents for each agent loop, LangGraph for runtime checkpoints and outer workflows, and LangChain for model, message, tool and frontend interaction interfaces. Generic frontend message assembly, tool-call presentation state, subscriptions, interrupt projections and scoped selectors SHALL use compatible upstream interaction libraries. The application MUST own model installation/loading/settings, effective configuration, project/session identity, permissions, resource admission, durable application records, confirmed outcomes, retained files and local evaluation. Frontend projections MUST NOT become execution, authorization, scheduling or checkpoint authority. The application MUST NOT implement a second model/tool loop or workflow runtime.

The diff editor, the text editor, and the file-tree widget SHALL be loaded presentation libraries. They are not execution engines. The application owns the dock and the records those views read. It MUST NOT implement its own diff algorithm, syntax highlighter, file-tree widget, agent loop, checkpointer, or MCP host.

#### Scenario: Execution owner trace

- WHEN a model call, tool execution, and workflow step are traced
- THEN each MUST reach its designated upstream owner
- AND a second application-written agent loop MUST be rejected.

#### Scenario: Multiple observers

- WHEN multiple frontend selectors or subscriptions observe one thread
- THEN they MUST observe the same backend-owned run without another graph invocation
- AND their loading or disconnected state MUST NOT establish a durable run outcome.

#### Scenario: Review uses the loaded editor

- **WHEN** a person reviews a recorded project-file change
- **THEN** the diff view is the loaded editor showing the stored before and after text
- **AND** opening that view MUST NOT call the model or write a second diff engine.
