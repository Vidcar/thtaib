## 1. Catalogue and status

- [x] 1.1 Chat list and project list are small, independent, and read-only on the list path
- [x] 1.2 The sidebar does not claim the catalogue is empty while a list is still loading, and it retries until the first success
- [x] 1.3 The lower-left dot and its hover show reading, model start, ready, or service unavailable
- [x] 1.4 Attention and a finished chat open do not load the token log or full run bodies

## 2. Token log and model

- [x] 2.1 A running reply keeps one current snapshot and its tokens; a saved turn drops token rows and older snapshots
- [x] 2.2 Existing finished chats are collapsed once and the database file is shrunk, without deleting those chats
- [x] 2.3 The preferred stopped managed model starts after the catalogue is requested

## 3. Check

- [x] 3.1 Desktop build and the affected backend tests pass
- [x] 3.2 Use the app: lists show quickly, a long chat opens, archive and delete still mean what they meant, and the database is no longer hundreds of megabytes
