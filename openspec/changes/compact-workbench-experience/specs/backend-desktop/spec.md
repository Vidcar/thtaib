## ADDED Requirements

### Requirement: API-021 - Compact consistent desktop surfaces

All existing desktop destinations SHALL use a shared compact visual language with readable small typography, restrained headings, consistent icon actions and contextual help available by hover and keyboard focus. Primary task controls, current settings, errors and permissions SHALL remain directly discoverable. Navigation and Chat inspectors SHALL support bounded resizing, collapse and expansion without losing content or execution state. Disclosure controls MUST NOT use chevrons or triangle arrows, and repeated product branding and generic notification headings MUST NOT consume working space.

#### Scenario: Resize and navigate
- **WHEN** the user resizes, collapses or reopens navigation and moves among Chat, Models, Library, Knowledge, Workflows, Lab, Attention and Settings
- **THEN** controls remain usable, selected states and focus are visible, and long content scrolls without hiding the composer or forcing horizontal page overflow.

#### Scenario: Optional explanations
- **WHEN** an explanation is useful but not required to act
- **THEN** concise contextual help exposes it on hover or focus while the main surface prioritizes the task and actual values.

### Requirement: API-022 - Ordered meaningful conversation activity

Chat and agent transcripts SHALL display supplied reasoning before its corresponding answer. Tool activity SHALL identify actual tool names and meaningful input summaries, expose real inputs, outputs and errors, join live and retained records by call identity, and preserve chronological placement without duplication. Individual expansion SHALL remain usable during streaming and changing detailed-stream preference.

#### Scenario: Streaming tool completion
- **WHEN** a named tool call streams, returns a result and is hydrated from retained history
- **THEN** one matching activity shows its actual output or error in its original location, and reasoning precedes the answer rather than appearing below it.

#### Scenario: Live tool without answer text
- **WHEN** live tool activity exists before any answer message
- **THEN** that activity remains visible with an honest pending, running, completed or error state.
