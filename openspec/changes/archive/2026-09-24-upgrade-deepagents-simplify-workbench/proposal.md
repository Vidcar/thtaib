# Proposal

## Why

Workbench currently compensates for older Deep Agents behavior with local middleware and product features that add failure paths and obscure framework ownership. Deep Agents 0.7.18 supplies the needed skill reload and tool safeguards; this change adopts them and removes the user-selected features that are not working reliably.

## What Changes

- Upgrade the pinned Deep Agents dependency from 0.7.15 to 0.7.18 and verify the 0.7.16–0.7.18 fixes at the integration boundary.
- **BREAKING**: Keep memory fixed for a conversation and load changed skills on the next user turn through native middleware state. Require a valid native `SKILL.md` for skill creation, editing, and import; retire freeform skill conversion.
- **BREAKING**: Remove Workbench's extra structured-output repair turn. Invalid output fails with its validation reason and cannot trigger another effectful tool call.
- Use Deep Agents' native model-aware summarization defaults and remove Workbench's early compaction threshold; retain only the narrow input-budget adjustment that prevents a second output-space reservation.
- **BREAKING**: Retire Approve for me, custom `rename_file` and `delete_file`, file-change capture and reverse, the Changes page, and Steer. Keep Ask and Full access, explicit grants, native file tools, ordinary Stop, and queued follow-ups.
- Route typed `ask_user` answers through the ordered LangChain human-in-the-loop `respond` decision alongside tool approvals; retain backend validation and interruption identity.
- **BREAKING**: Clean-reset the authorized existing local chats, projects, settings, and related app records without migration or compatibility shims. Retain downloaded weights, staging/cache, and runtimes and register a fresh working model setup.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agents-workflows`: fixed conversation memory, native skill reload, Ask/Full access, ordered question and approval resume, and queue without Steer.
- `architecture`: remove the diff editor and change-record ownership requirement while keeping file viewing, execution, and access boundaries.
- `backend-desktop`: remove retired controls and the Changes page while preserving Chat, Files, and activity presentation.
- `environments-tools`: remove permissive read-only shell parsing and custom file mutation tools; use native tool safeguards.
- `models`: fail clearly on invalid structured results without a local repair turn.
- `state-recovery`: require native skill packages and remove file-change images and single-file reverse.

## Impact

The backend agent/interaction, Knowledge, and project-file boundaries; desktop Chat, setup, Settings, and dock; Deep Agents dependency and tests; current OpenSpec contracts and the overlapping active product-contract change; versioned developer references. The completed `rewrite-loaded-boundaries` change is historical and its overlapping decisions are superseded here.
