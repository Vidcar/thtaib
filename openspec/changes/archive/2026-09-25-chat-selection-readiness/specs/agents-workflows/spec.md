# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-024 - Keep agent role independent of conversation model

A conversation SHALL own its main model configuration, main agent selection, access choice, mode and capability groups. Choosing or editing the main agent SHALL change its instructions, named helpers and required capabilities for future turns without silently changing the conversation model or granting access. A helper MAY select a different model configuration; an unbound helper SHALL inherit the conversation model. A project SHALL contribute its folder and selected project knowledge without supplying model, agent, mode or access defaults. A model shown as explicitly selected in a new or saved Chat MUST be retained in the submitted conversation setup through agent and project changes. The backend SHALL resolve these owners once before dispatch and expose the same effective values and reasons to Chat.

#### Scenario: Main agent changes without model switch
- **WHEN** a person chooses a different main agent in an existing compatible chat
- **THEN** the model remains selected and no model is loaded solely because of the agent change.

#### Scenario: Project supplies context only
- **WHEN** a project chat selects a model, agent and access choice
- **THEN** the project folder and knowledge are available within that chat's authority while the model, agent and access come from the conversation and application preference.

#### Scenario: Model selected before agent

- **WHEN** a person chooses a model and then a main agent for a new chat
- **THEN** the displayed exact model remains in the submitted setup, just as when the agent is chosen first.
