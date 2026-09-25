# Spec Delta

## MODIFIED Requirements

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's explicit Ask or Full access choice. An application preference SHALL seed new conversations and SHALL default to Ask on a fresh installation; project and agent definitions SHALL NOT override access. A chat's explicit choice SHALL survive unrelated preference changes and MUST NOT leak from the previously viewed chat. Access labels SHALL show Ask or Full access in full and explain that running and already queued messages keep their selected policy. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The conversation SHALL visibly expose separate main-model and main-agent selectors beside the composer, supported reasoning effort or Thinking off, a removable Plan pill, compact attachments, capability groups and access. One model picker row SHALL represent one installed model; its named configurations SHALL be secondary choices. Changing an agent SHALL NOT silently change the main model. The shield selects Ask or Full access for later messages in that chat and does not turn tools on or off. The `+` menu SHALL expose optional capability groups and attachments without a list of individual tool toggles; project files remain available in project chats, while shell, browser and Windows control require explicit conversation choices. The setup rail SHALL start closed and MUST NOT take height from the transcript while closed. Changes SHALL affect future submissions without rewriting active turns or queued intended configuration. Unsupported, overridden or unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

Compact status elements SHALL expose current context fill and generation speed in tok/s, with capacity, counting/measurement basis and relevant interval available on expansion. Observed measurements, labelled estimates and unavailable values SHALL remain distinguishable. Stream chunks MUST NOT be counted as tokens; absent usage MUST NOT appear as zero. Context changes/compaction and current versus completed-turn measurements SHALL remain attributable rather than silently showing stale values as current.

Context details SHALL open on pointer hover and keyboard focus, with touch access and Escape dismissal. Prefer model-reported request input/output counts over preflight estimates once available. Supported llama.cpp timing streams SHALL supply live generation speed with bounded updates and no shared-slot polling; measurements SHALL reset at each model-call boundary and retain their current/completed/interrupted status. Compact settings SHALL avoid redundant default-value cards while preserving actionable failures, meaningful choices and accessible explanations.

Opening the application or restoring a chat SHALL NOT warm its selected model. Sending with an unloaded installed managed model SHALL load the selected setup through the existing manager and admission path, show waiting/loading/readiness, then submit once ready. Failure SHALL preserve input and offer recovery. A passive status probe MUST NOT cause loading. Active-work protections and connected-endpoint ownership MUST NOT be bypassed and models/settings MUST NOT be silently substituted.

#### Scenario: Unsupported reasoning and unavailable telemetry
- **WHEN** the selected model lacks a supported thinking-off control or supplies no usable token measurement
- **THEN** the control/measurement explicitly reflects that limitation rather than claiming thinking is off or showing an invented tok/s value.

#### Scenario: Cold launch and first Send
- **WHEN** Workbench opens a chat whose selected model is unloaded, then the person submits a draft
- **THEN** launch remains cold, Send shows loading and submits once that exact configuration is ready, while failure preserves the draft and cannot duplicate accepted work.

#### Scenario: Start from Chat with a resource conflict or failure
- **WHEN** a submitted draft needs an unloaded model while another request holds the only slot or loading fails
- **THEN** Chat shows waiting or the failure with a corrective action, preserves the draft and cannot duplicate accepted work.

#### Scenario: Setup stays off the transcript
- **WHEN** a person opens the conversation rail to Setup
- **THEN** setup sits in that rail and the transcript remains readable beside or above it.

#### Scenario: Inherited access follows its named source
- **WHEN** the application preference changes after a chat explicitly selected Ask
- **THEN** that chat remains Ask while a new chat takes the current application preference, and Chat names the preference source when no explicit choice exists.

### Requirement: API-028 - Switch the selected model without interrupting work

Choosing a model or named configuration SHALL start loading that exact managed selection without a second confirmation. A selection remains pending until readiness is observed; a failed load SHALL retain the previous chat binding and draft with an actionable reason. When the loaded-model limit is reached, a busy model request SHALL finish before capacity changes, and the new selection SHALL show waiting then loading. The chat and its compatible history remain open. Known-incompatible choices SHALL be disabled with reasons; Workbench SHALL NOT create a new chat as a side effect of a setting change. An explicit stop, unload or destructive configuration change SHALL retain its own reviewed protection.

#### Scenario: Swap during a quiet chat
- **WHEN** a person chooses a different installed model while the previous model is idle
- **THEN** the selected model loads under the configured limit without asking for another confirmation and the conversation stays open.

#### Scenario: Swap while work is running
- **WHEN** one slot is occupied by an in-flight request and a different model is chosen
- **THEN** that request continues, the new selection shows waiting, and loading begins when capacity is safe.

#### Scenario: Apply a named model variant in Chat
- **WHEN** a person chooses a named configuration with different launch settings
- **THEN** Workbench loads those exact settings before binding the same chat, retaining its draft and history on failure.

#### Scenario: Failed selection
- **WHEN** the requested model cannot become ready
- **THEN** the previous conversation binding and draft remain and the failed attempt is visible.

## RENAMED Requirements

- FROM: `### Requirement: API-028 - Confirm before swapping the loaded model`
- TO: `### Requirement: API-028 - Switch the selected model without interrupting work`

## ADDED Requirements

### Requirement: API-036 - Keep helper work and capability readiness visible

Named helper progress SHALL appear in an expandable side rail, with the parent answer in the main conversation. Approvals and typed questions SHALL remain actionable from the conversation. Chat SHALL show whether each enabled capability is ready, needs a live grant, is unavailable or is known incompatible before dispatch. A selected-window capability SHALL require a current window choice and All windows SHALL require that conversation's live grant. A missing grant SHALL offer regrant instead of dispatching a turn that predictably fails with an access conflict. Unfinished Lab and Workflows SHALL be absent from the primary navigation while their existing routes, records and Attention recovery remain reachable.

#### Scenario: Reopen a chat after window grant expires
- **WHEN** a chat with Windows control enabled is reopened after its live grant is gone
- **THEN** Chat shows the missing grant and a route to grant it before a Windows-capable turn can start.

#### Scenario: Helper activity is separate
- **WHEN** a named helper works and returns a result
- **THEN** its activity is expandable in the rail while the parent's final answer remains in the conversation.
