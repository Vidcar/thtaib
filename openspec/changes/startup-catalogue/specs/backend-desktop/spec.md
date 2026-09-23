## MODIFIED Requirements

### Requirement: API-007 - Launch locally and keep desktop state honest

The Windows launcher SHALL reuse a healthy product backend or start it hidden, then open the built Electron desktop. The first screen SHALL request projects and chats independently. Each list SHALL be readable before either request finishes. A list that has not finished SHALL NOT be presented as empty. Failure to reach the service SHALL retry until the first success. Chat SHALL keep the composer visible while transcript and history scroll independently. Recent conversations SHALL appear first. New Chat SHOULD prefer a running chat deployment and MUST NOT apply unrelated saved profiles. Stopped deployments MUST NOT gain healthy labels from stale probes.

The lower-left status dot is the only startup status. Its hover is one short phrase for reading the catalogue, starting the model, ready, or the service being unavailable. The visible word stays "Local" while the service is up, including while the rail is collapsed down to the dot.

Opening a finished chat SHALL show its saved transcript and latest display snapshot. It MUST NOT scan that chat's token log. The chat list MUST NOT include transcripts, run bodies, or model-request logs.

#### Scenario: Desktop launch and model state

- WHEN the launcher opens the application and a stopped deployment has an old probe
- THEN the desktop MUST present current backend state
- AND catalogue loading MUST be explicit rather than shown as an empty catalogue
- AND projects MAY appear before chats

#### Scenario: Finished chat opens from the saved transcript

- WHEN a person opens a chat whose answer is already saved
- THEN the saved answer is shown
- AND the token log is not read to paint it
