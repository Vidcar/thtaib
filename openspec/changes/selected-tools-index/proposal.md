# Proposal

## Why

A local model sees how to call `find_tools`, but not which tools this turn accepted or what those call names are called on screen. Agent instructions are being used as a typed command list, which is the wrong place for that index.

## What Changes

- Generate a short capability index at admission from the accepted tools. Each item is the call name and the screen label, grouped by the catalogue group. Do not store the index on the agent, and do not copy parameter manuals into it.
- Show that same index on the Inputs preview of the next message when the model would receive it. Leave the legacy path, where there is no input policy, unchanged.
- Keep agent instructions as the job. Keep the Deep Agents profile prompt empty for this model. Keep Workbench core as the short operating text, with no tool names. Keep saved model setup prompts empty.
- Update starter drafts so they do not auto-select the nine repository-development skills. Add a General draft. Leave Permission check and saved agents untouched. Leave the Trusted project builder's Full-access suggestion as it is.

## Capabilities

### New Capabilities

### Modified Capabilities

- `agents-workflows`: The next message carries a generated capability index of accepted call names and screen labels. Agent instructions stay the job. Starter drafts do not select the repository-development skills.

## Impact

- Backend admission, helper prompts, and the Inputs preview. No new tool authority, no change to when-needed bootstrap, pins, or automatic `find_tools`, `read_reference`, or `task`.
- Starter template drafts only. No desktop label changes. No live product data.
- `align-reviewed-behavior` and `consolidate-product-contract` stay as they are.
