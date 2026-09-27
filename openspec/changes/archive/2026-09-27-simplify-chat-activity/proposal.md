# Proposal

## Why

Chat can simultaneously show Thinking and Using tools because its transcript and composer consume different activity snapshots. The context hover panel also squeezes four token counts into a row that splits labels and numbers.

## What Changes

- Keep one live Chat status beside Stop, synchronized with the current owned run and its measurements.
- Use Generating for model output; retain supported preparation, tool, waiting, saving and stopping states without inferring thinking from retained reasoning text.
- Remove duplicate live transcript badges/progress while preserving Partial markers, reasoning, tools, approvals, failures and helper progress.
- Show all hover measurements in aligned rows, explain input subdivisions, and distinguish current from completed request speed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: API-017 compact status and measurements and API-018 independent Chat presentation.

## Impact

Desktop Chat projection subscription, shared message-feed presentation options, measurement layout and existing regressions. No backend, public wire contract, dependency or data migration changes.
