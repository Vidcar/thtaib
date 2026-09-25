# Proposal

## Why

Chat can display a selected model while omitting it from a new conversation, and readiness previews can fail with HTTP 500. Opening and replying also trigger redundant setup checks, while a completed turn can leave an obsolete active-turn warning and block the durable Queue action.

## What Changes

- Keep one explicit conversation model choice through New Chat, agent/project selection, saved-chat restoration, and submission; use the sole healthy running chat model only when no choice exists.
- Make choosing the exact healthy model configuration a no-op; load only a different or unloaded exact configuration.
- Normalize readiness preview input against dispatchable fields, preserve valid explicit clears, and report unsupported input without a server error.
- Separate active-turn occupancy from setup readiness so queued drafts work during a live turn and terminal transitions clear obsolete warnings.
- Show fetched chats promptly, avoid eager checks for every closed-picker choice, and remove redundant blocking previews from Send.
- Clarify the active submission versus durable Queue contract.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: Chat selection, hydration, readiness, Queue, and model-picker behavior.
- `agents-workflows`: Explicit conversation model ownership through agent changes and durable queue admission.
- `models`: Exact model selection and cold-load behavior in Chat.

## Impact

The FastAPI Chat readiness adapter and tests, Electron Chat panel and model picker, their focused checks, and these OpenSpec contracts change. No saved-data migration, new service, or model-weight change is required.
