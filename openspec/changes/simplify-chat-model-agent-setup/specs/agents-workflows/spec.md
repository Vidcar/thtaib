# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-021 - Keep delegated work within the conversation authority

Only explicitly selected frozen named agent versions SHALL be available as helpers. Each helper SHALL have isolated context, intersected parent authority, observable named activity and correctly owned approvals, cancellation and durable child identity. No recursive or general-purpose delegation SHALL be added by this selection. Calls sharing a managed model SHALL be serialized within a parent run initially; separate conversations and distinct loaded models MAY progress concurrently within actual server capacity. An alternate-model helper MAY hand off a single loaded-model slot after the parent's current model call completes, and the parent SHALL reload its exact model before continuing. The handoff MUST NOT widen authority, interrupt an in-flight model call or report a stopped parent as ready. Explicit tool-call budgets SHALL be enforced atomically across root and child calls, while unset budgets remain unset.

#### Scenario: Frozen helper and shared budget
- **WHEN** saved helper settings change after queueing and several helper calls compete for the last allowed tool call
- **THEN** the queued version and intersected authority are used and the explicit budget is not exceeded.

#### Scenario: Alternate model with one slot
- **WHEN** a parent delegates to a helper using a different installed model while the loaded-model limit is one
- **THEN** helper and parent calls run in sequence with visible loading or waiting and each uses its selected configuration.

#### Scenario: Stop child work
- **WHEN** a conversation is stopped while a helper is generating or awaiting approval
- **THEN** new dispatch stops, owned cancellation is confirmed before terminal cancellation, and partial/uncertain outcomes remain truthful.

## ADDED Requirements

### Requirement: AGT-024 - Keep agent role independent of conversation model

A conversation SHALL own its main model configuration, main agent selection, access choice, mode and capability groups. Choosing or editing the main agent SHALL change its instructions, named helpers and required capabilities for future turns without silently changing the conversation model or granting access. A helper MAY select a different model configuration; an unbound helper SHALL inherit the conversation model. A project SHALL contribute its folder and selected project knowledge without supplying model, agent, mode or access defaults. The backend SHALL resolve these owners once before dispatch and expose the same effective values and reasons to Chat.

#### Scenario: Main agent changes without model switch
- **WHEN** a person chooses a different main agent in an existing compatible chat
- **THEN** the model remains selected and no model is loaded solely because of the agent change.

#### Scenario: Project supplies context only
- **WHEN** a project chat selects a model, agent and access choice
- **THEN** the project folder and knowledge are available within that chat's authority while the model, agent and access come from the conversation and application preference.
