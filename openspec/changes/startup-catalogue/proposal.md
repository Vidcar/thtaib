## Why

After the window opens, projects and chats stay missing for a long time, and opening a long chat is slower still. The lists wait on full runs and a token log that is kept after the answer is already saved. The screen can also say the catalogue is empty while that work is still running.

## What changes

- The first screen reads a small project list and a small chat list, independently, and does not show an empty catalogue while either is still loading.
- The existing lower-left dot is the only status. Its hover says, in one short phrase, whether the app is reading chats, starting the model, ready, or unable to reach the service.
- After those lists are requested, the preferred stopped managed chat model is warmed through the existing start path. One model. The lists do not wait for it.
- A finished saved turn keeps its transcript, its latest display snapshot, and its execution checkpoint. It does not keep token rows or earlier snapshots. A turn that is still running keeps its tokens.
- Archive and removing a project still only hide. Deleting a chat still removes that chat's log.
- Opening a finished chat uses the saved transcript and snapshot. It does not scan the token log.

## Capabilities

### Modified capabilities

- `backend-desktop`: first-screen catalogue, the status dot, and opening a finished chat.
- `models`: warm one preferred managed model after the catalogue is requested, without blocking it.
- `state-recovery`: drop token rows once a turn is saved.

## Impact

Desktop sidebar, chat open, attention, and the application database token log. Scratch chats and projects stay unless the person deletes them. The existing finished token log is collapsed once and the database file is shrunk.
