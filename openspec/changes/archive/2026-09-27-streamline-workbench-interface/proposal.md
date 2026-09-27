# Proposal

## Why

Everyday Chat controls, navigation and setup currently compete for space and spread related choices across several surfaces. The discovery session established a compact interface with clear ownership, minimal on-screen prose and safe preparation of the next message; the supplied mock and notes are inspiration, not a replacement product contract.

## What Changes

- Split navigation into a slim destination rail and independently collapsible project/chat list. Put Search and Notifications icons at the rail's top; retain existing launch, history, project and attention behaviour.
- Consolidate the composer row: `+`, access, active-only removable Plan pill, model and adjacent tuning icon, agent, context/speed, combined Send/Stop. Enter queues during active work; changes prepare future messages without changing accepted work.
- Give Chat one combined thinking/context editor with one Apply, remembering overrides per model in that chat. Permanent defaults and response/thinking-token limits stay in Models. Explicit idle selection loads immediately; restoration remains cold.
- **BREAKING contract change:** Agents own grouped and individual tool selection, knowledge defaults and an optional fixed model. Chat owns access, mode and additional context; neither the agent dropdown nor `+` contains tool toggles.
- **BREAKING contract change:** New submissions resolve the latest saved selected agent and knowledge versions, then freeze exact versions at admission. Running, queued and paused work retains its snapshot.
- Share mouse/keyboard context and skill pickers through `+`, `@` and `/`; slash additions apply to the next message only and never enable tools or grant access.
- Use small right-aligned user bubbles and unboxed assistant answers; retain named tools, collapsed reasoning/details, actionable errors/approvals and truthful composer activity.
- Replace Setup/Library/Actions dock pages with click-open Files/Browser/Helpers. Combine contextual files without duplicating storage; keep global Library and move chat/message actions to their owning menus.
- Guide agent creation and skill authoring, retain grouped editors and a native skill Source tab. Keep explanatory prose short across screens, with detail on demand.
- Add Find → Choose → Review/download with an advisory quant/KV/context hardware estimate. Carry chosen settings into the initial configuration; estimates never block save/download/load or silently reduce settings.

## Capabilities

### New Capabilities

None. Extend the existing owners.

### Modified Capabilities

- `backend-desktop`: navigation, composer, model tuning/staging, message presentation, panels, guided setup and concise copy.
- `architecture`: atomic saved-record resolution at Chat acceptance, immutable snapshots and separate live dispatch/resume checks.
- `agents-workflows`: agent/model/tool ownership, admission snapshots, latest saved knowledge and guided skill authoring.
- `environments-tools`: agent-owned group/tool selection with unchanged live access and connection authority.
- `models`: staged selection, guided import and advisory hardware estimates mapped to canonical saved configuration.

## Impact

Desktop owners include `WorkbenchSidebar`, `ChatPanel`, `ChatModelControls`, `AgentMessageFeed`, `ChatDock`, `BrowserRail`, `AgentSetupsPanel`, `SetupConfigurationEditor`, `KnowledgePanel`, `HuggingFaceImport` and `DeploymentsPanel`. Backend work extends setup resolution/admission, versioned agent/knowledge records, existing Hugging Face inspection and inference configuration/hardware boundaries; affected shared contracts require regeneration.

No new application, execution loop, file catalogue or configuration authority. Preserve native streaming, durable queue, permissions, model residency, publisher provenance and settings bags. Workflows/Lab and speech/image-engine delivery remain with their existing changes; initial catalogue recovery remains with `startup-catalogue`. Generated previews illustrate direction and are not built-product acceptance; the implemented surfaces require native validation.
