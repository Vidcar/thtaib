# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-023 - Generate an image through a configured ComfyUI

Image generation SHALL call a ComfyUI address the person saved, using a workflow they already created there. The app MUST NOT ship ComfyUI or install its custom nodes. The composer SHALL offer Make an image only when an address is saved. Choosing it asks for the prompt, shows progress, and places the finished image in the reply and in the library. Failure names the address and the reason, and it does not invent an image. Text-only Chat hides the control when no address is saved.

A later image feature uses this same saved address. This contract does not include it, and it does not forbid it.

#### Scenario: Make an image

- **WHEN** a person has saved a ComfyUI address and asks for an image from the composer
- **THEN** progress is visible and the returned image appears in the reply
- **AND** the message is not sent to the language model as a substitute for the image.

#### Scenario: No ComfyUI configured

- **WHEN** no ComfyUI address is saved
- **THEN** the composer does not show a broken image action
- **AND** ordinary text chat is unchanged.

### Requirement: ENV-024 - Dictate and speak through a configured speech endpoint

Dictation and spoken replies SHALL use one OpenAI-compatible speech endpoint the person configures with an address, a model, and a voice. The app MUST NOT ship Whisper, Kokoro, Piper, or a voice model. Example local plugs are whisper.cpp or faster-whisper for dictation, Kokoro for a small natural voice, and Piper when the machine has no spare graphics processor. They are examples, not the only choices.

The settings screen SHALL say when the address is not on this machine. A cloud address is allowed only when the person saved it, and the screen says it is not local. The app MUST NOT send audio to an address the person did not save.

Dictation listens, then inserts editable text into the composer. It MUST NOT send the message. Spoken reply is a button on a finished answer and plays only that answer. Voice cloning, always-on listening, and a phone-call style conversation are not in this contract. A later version of those features uses this same endpoint. The contract does not forbid them.

#### Scenario: Dictate without sending

- **WHEN** a person dictates a sentence
- **THEN** the text lands in the composer for editing
- **AND** the conversation does not gain a user message until they send it.

#### Scenario: Speak one answer

- **WHEN** a person chooses Speak on a finished answer
- **THEN** that answer is spoken through the saved endpoint and voice
- **AND** other answers are not spoken on their own.

#### Scenario: Remote endpoint is labelled

- **WHEN** the saved speech address is not on this machine
- **THEN** the settings screen says it is not local before the person uses it.

### Requirement: ENV-025 - Search the public web through one configured integration

The product SHALL offer one configured public web search and one public page reader. Search snippets and fetched page text stay distinct, and each keeps its address, title, and the time it was read. A documentation connection does not count as this search. When no search is configured, Chat still works offline and the tool is absent rather than failing closed after the model has called it. Secrets for the search stay in the backend.

The activity line for a search uses the same one-line pattern as other tools: the query, not a dump of the page.

#### Scenario: Search then open a page

- **WHEN** web search is configured and the agent searches and then reads one result
- **THEN** the snippet and the page text are separate retained results
- **AND** Chat without that configuration never offers the search tool.

### Requirement: ENV-026 - Keep connection secrets in the backend

Tool connections, including MCP, web search, ComfyUI, and speech, SHALL be one list in Settings. Each row shows the name, the kind, and whether it is ready. The address and options are editable. A secret can be replaced and cleared. It is never shown again after it is saved. Removing a connection asks for confirmation and does not delete chats that used it. A connection that fails to start shows the reason on the row and leaves Chat usable.

#### Scenario: Save a speech secret

- **WHEN** a person saves a speech endpoint with a secret and reopens Settings
- **THEN** the secret field is blank or marked as saved
- **AND** the secret is not present in the desktop's rendered page.
