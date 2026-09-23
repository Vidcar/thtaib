## Context

Health is ready in seconds. The window then asks for every chat together with every project, and each chat list loads full runs. Finished chats also keep every token in `interaction_events` (about 743 MB across the current scratch chats). Opening one of those chats can read that log. The lower-left dot turns green when the service answers, which is before the lists or the model are ready.

## Goals

- Projects and chats appear from small reads, without an empty-state lie.
- One dot, one hover phrase.
- Warm one managed model after the lists are requested.
- A saved answer does not keep its token log. Live turns still do.

## Non-goals

- Deleting chats or projects as part of the product change. Validation may use the scratch data.
- Changing archive or remove-project into deletion.
- Warming more than one model, or starting a connected endpoint.
- A new status panel.

## Decisions

- The chat list used by the sidebar omits transcripts, run bodies, and request logs. Opening one chat still reads that chat. A finished chat does not load its run body.
- Attention reads run status. It loads a run body only for a live or failed run.
- Startup catch-up, token collapse, and the database shrink start after the first catalogue request, not before health.
- Token rows stay until the answer is saved, because a live subscriber follows their sequence. When the answer is saved, those rows and older snapshots are deleted. The latest snapshot and the checkpoint remain. Deleting a snapshot while the reply is still running would leave a gap in that sequence.
- The desktop warms a model only in the real app, through the existing deployment start.

## Risks

- Collapsing the existing log locks the database once after the lists have loaded. The lists themselves do not scan that log.
- A test that expected every token to remain after a short finished turn is updated to the saved snapshot.
