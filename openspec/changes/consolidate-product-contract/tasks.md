# Tasks

The approved `polish-workbench-surfaces` delivery now owns the overlapping everyday workspace, named helpers and existing-surface repair below. Their original checkboxes remain unchecked until verified there; this is not a completion claim. The new Lab suite, visual workflow canvas and media integrations remain outside that delivery.

## 1. Everyday workspace

- [ ] 1.1 Build the compact destination treatment from API-027 and verify Chat, Lab, Workflows, and Settings share type, focus, and help on hover without horizontal scrolling.
- [ ] 1.2 Archive a conversation so it leaves the active list immediately, and delete a chat so project files remain. Verify both with a focused state test and the sidebar.
- [ ] 1.3 Import a skill package without executing its script, and extract a text PDF while reporting an encrypted PDF as unread. Verify the import and extraction tests.
- [ ] 1.4 Add the Settings connection list, public web search, and backend-only secrets from ENV-025 and ENV-026. Verify a secret is not rendered after save and Chat still sends with no web connection.

## 2. Lab screens

- [ ] 2.1 Add the Measurements screen: probed context, editable sizes and depths, llama-bench prefill and decode, a loaded chart, overlay, and confirmed delete. Verify a missing runner shows an empty chart with a reason and a smoke run is not labelled as performance.
- [ ] 2.2 Add the Memory screen with editable depths defaulting to 0, 25, 50, 75, and 100 percent, and one pass or fail row per depth. Verify the expected needle text is the score.
- [ ] 2.3 Add the Challenges screen with one direct tool card, one indirect tool card, and a known-answer reasoning card. Verify a new versioned card does not rewrite an older result.
- [ ] 2.4 Enforce the Lab reservation with a named confirmation and a banner on Chat. Verify a busy chat blocks the start and a new send does not start a second model run.

## 3. Helpers, models, and workflows

- [ ] 3.1 Add the Helpers section and offer only named agents, with the general-purpose helper still disabled. Verify an empty list offers no helper tool and a named helper cannot exceed the conversation's permissions.
- [ ] 3.2 Confirm before a model swap, keep the conversation, and show helper or workflow activity by name. Verify unload does not happen before confirmation and an approval card stays the approval control.
- [ ] 3.3 Build the Workflows canvas on React Flow with the named steps, inspector, visible invalid steps, and refusal of imported arbitrary code. Verify a grader step runs only when placed.

## 4. Media plugs

- [ ] 4.1 Call a saved ComfyUI address for one existing workflow and hide the action when no address is saved. Verify progress and the image land in the reply, and text chat is unchanged without an address.
- [ ] 4.2 Call a saved OpenAI-compatible speech endpoint for dictation and for Speak on one answer. Verify dictation does not send, a non-local address is labelled, and no audio goes to an unsaved address.

## 5. Checks

- [ ] 5.1 Run `openspec validate --all` from the repository root. Verify it passes after the old plan folders are gone.
- [ ] 5.2 Run the focused backend tests for Lab reservation, skill import, chat deletion, and connections, and the desktop build from `apps/desktop`. Verify they pass.
