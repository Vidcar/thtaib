# Proposal

## Why

Models and Chat label a managed start as Reload. The real reload route stops a managed record, restores a failed reconfigure, and starts that same record, and no screen calls it. A person cannot tell Load, chat setting changes, and recovery apart.

## What Changes

- Models Load and Load saved post the saved setup to managed start and ignore unsaved edits. The lifecycle button never says Reload.
- A separate Reload control appears when a managed deployment exists for the selected setup. It is the only control that posts `POST /v1/deployments/{id}/reload`.
- Load snapshot stays `POST /v1/deployments/{id}/start` on a stopped record.
- Chat, Lab, and Agent run apply that chat's startup overrides through one desktop helper. Idle tuning is labelled "Apply this chat's settings". Active work stays "Stage for next message" and does not start a model.
- Unused desktop deployment twins are removed: the old shared starter, prepare-without-start, profile update/rename/duplicate, and reconfigure.
- A desktop check binds each of those controls to the endpoint it claims to call.

## Capabilities

### New Capabilities

### Modified Capabilities

- `models`: MOD-043 names Load, Load saved, and Reload by the operation each one calls. MOD-037 names the chat apply control instead of Reload.
- `backend-desktop`: API-017 and API-054 name the idle chat control "Apply this chat's settings" and keep it on managed start with that chat's overrides.

## Impact

- Desktop Models editor, chat tuning, and the shared model client.
- Existing desktop checks that click a Reload label expecting managed start.
- No backend route change. llama.cpp and Deep Agents stay behind their current boundaries.
