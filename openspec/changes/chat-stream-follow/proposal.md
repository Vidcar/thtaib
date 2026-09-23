# Proposal

## Why

Chat falls behind the model while a reply is still being written. Each token redraws the whole answer, the window animates toward text that has already moved on, and each speed update recopies the transcript on the way to the screen. The gap grows with the answer. The person should see new tokens as they arrive and still be able to scroll back through all of them.

## What Changes

- While a reply is running, the transcript and any open reasoning or tool body follow the newest line immediately, until the person scrolls away.
- Finished text is left alone. Only the open tail of a streaming answer or reasoning block is redrawn.
- A speed update updates the readout only. It does not rebuild the transcript, move the scroll position, or wait on a replay of the tokens so far.
- An expanded tool or reasoning body shows the full text. Scrolling reaches every line. The live view no longer cuts the text down to the latest 4,000 characters.
- Opening a chat, reconnecting, and approvals stay as they are. Copy, Regenerate, and Branch still wait until the answer is finished.

## Capabilities

### New Capabilities

### Modified Capabilities

- `backend-desktop`: API-018 and API-026. Live answers, reasoning, and tool bodies stay fully readable and follow the newest line without a character cap. Speed updates stay off the text path. Motion preferences and the existing answer actions stay.

## Impact

- Desktop chat transcript, reasoning panel, and tool rows in `apps/desktop`.
- Backend interaction stream in `apps/backend`: measurement frames and token persistence on the live path.
- No new protocol, no second assembler, and no change to execution, permissions, or checkpoints.
