# Proposal

## Why

Chat always links to an unexplained empty permissions list, and its help icon occupies a separate row. Its model picker repeats long weight filenames beside settings and relies on small expand arrows, obscuring the useful model/configuration hierarchy.

## What Changes

- Show the Chat Saved permissions shortcut only when remembered approvals exist, refreshing that fact when the menu opens.
- Put the help icon beside the Access heading and shorten its explanation.
- Explain saving from an Ask-mode approval card, exact-input matching, and revocation in Settings without promising approval pauses under Full access.
- Present compact model names with quantization and clearly indented configuration choices, without repeated weight filenames or small expand arrows. Keep full source identity available in search and tooltips.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: Clear permission controls, an actionable permissions empty state, and a compact Chat model hierarchy.

## Impact

Desktop Chat, its model picker and Settings presentation using existing grant and model APIs. Approval enforcement, grant storage, model selection/loading and request contracts remain unchanged.
