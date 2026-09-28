## ADDED Requirements

### Requirement: API-051 - Show applied values and specific default targets

Shared controls throughout the desktop SHALL make known backend-resolved values the main readout and their source secondary. Default-following options SHALL include the resolved value, and numeric controls and sliders SHALL visibly represent it without manufacturing a requested override. Reset actions SHALL name their verified target and expose its value on hover or focus. Following a saved configuration and selecting the underlying model default SHALL remain distinct when they have different semantics. Unknown, unsupported and unbounded values SHALL use truthful labels; Automatic SHALL describe only an actual automatic engine mode. Redundant inherited badges and prose SHALL be removed while internal default-following semantics remain unchanged.

#### Scenario: A following control updates with its default
- **WHEN** a default-following control is displayed and its saved default changes
- **THEN** the control reflects the new resolved value without having pinned the earlier value
- **AND** an explicitly selected value remains explicit.

#### Scenario: Different reset targets
- **WHEN** a saved configuration default differs from the model template default
- **THEN** both available actions name their target and its known value, and each preserves its existing resolver meaning.

### Requirement: API-052 - Keep saved-record editing calm and recoverable

Models, Agents and Knowledge SHALL use searchable catalogue/detail editing, with an accessible selector when a side catalogue cannot fit. Shared headings, fields, actions, disclosures and states SHALL follow existing theme, spacing and density controls. Navigation within the open app SHALL preserve unsaved drafts; restoring saved values SHALL clear dirty state. Agent rows SHALL identify role, model assignment and actionable missing dependencies. Helper selections SHALL remain visible and removable when missing. Creation Review SHALL summarize the entire draft, including helpers and requirements, and Back or failed Save SHALL retain it. Knowledge creation SHALL occupy the editor pane, preserve lossless Guided/Source/resources/scopes, and distinguish display names from native skill identity. Policy/capture controls SHALL be compact and independent failures SHALL not block editing. Agent/browser/record actions SHALL use recognizable consistent icons.

#### Scenario: Navigate with an unsaved draft
- **WHEN** a person edits a saved record, visits Chat, then returns to its editor
- **THEN** the unsaved draft remains available, and reverting it to saved values clears its changed indicator.

#### Scenario: Repair a deleted helper
- **WHEN** a saved agent selects a helper that is no longer available
- **THEN** that selection remains visible with a corrective Remove action, and creation Review includes selected helpers and their requirements.

### Requirement: API-053 - Keep file browsing scoped and reusable in Chat

Library SHALL retain its table/detail preview, save-copy, deletion and selection-dependent bulk controls. All files, Project and Chat filters SHALL work using existing retained-file authority and recognizable source names; unavailable sources and previews SHALL be explicit. Image detail previews SHALL use available space. Library SHALL NOT offer Use in Chat or global reuse handoff; Chat attachment/context/Files reuse SHALL remain available. Chat Files SHALL retain authorized uploads and reused copies after responses, provide concise provenance/capture time and loading/empty states, and preserve response-specific filters beside their answers. Pickers SHALL keep highlighted choices visible, restore focus, handle filtered reopening and no matches. Broken agents SHALL offer Review in Agents. Access popovers SHALL use the agreed compact presentation.

#### Scenario: Scope the retained catalogue
- **WHEN** a person selects a Project or Chat Library filter
- **THEN** the query uses that one selected scope, origin labels remain recognizable, and selected records retain preview/save/delete authority.

#### Scenario: Files after a response
- **WHEN** an uploaded or reused file has no run owner and a response finishes
- **THEN** it remains available in Chat Files while individual answer sections retain their own response filters.

## MODIFIED Requirements

### Requirement: API-042 - Use one control grammar across settings

Every settings form in the desktop SHALL use one row grammar: the label, hover/focus help and a short provenance line (value, source and state, omitting unknown parts) on the left, the control on the right, and an optional hint underneath. Binary settings SHALL use a switch, two to five options a segmented choice, ordered numbers a slider with exact entry, long lists a select, and destructive confirmations a dialog. Default-following values SHALL appear as their resolved value in the control or a named default choice, with a reset action naming its verified target and exposing its known value on hover/focus; displaying the value MUST NOT create an override. Following a saved configuration and using the model's own default SHALL remain distinguishable when their resolver meanings differ. Unknown values SHALL remain explicit, and generic Inherited or Reset to inherited wording SHALL be replaced. Cards and controls SHALL take radius, padding, height and colour from the existing appearance tokens, so compact and comfortable densities and light and dark themes apply everywhere without a second appearance system.

#### Scenario: Edit an inherited model setting

- **WHEN** a person opens a model's settings, Defaults, or the chat model menu
- **THEN** each setting shows its effective value and where it came from beside the control
- **AND** following or resetting to the named default clears only that layer's value while preserving the target's distinct resolver meaning.

#### Scenario: Narrow window and comfortable density

- **WHEN** the window is about 360 px wide or density is comfortable, in light or dark
- **THEN** rows stack the control under the label without horizontal scrolling
- **AND** section actions stay on one line.

### Requirement: API-023 - Keep one dock beside the conversation

Chat SHALL use one right-hand dock with exactly Files, Browser and Helpers pages. It starts closed; one header control opens/closes it and retains its open choice, page and bounded width across chat navigation. All pages SHALL share one remembered preferred width, seeded from the existing Files preference, with common resize/reset behaviour; browser resolution SHALL remain separate. A smaller window SHALL clamp displayed width without overwriting the preference, and the resize handle SHALL reflect displayed width. A splitter SHALL resize it while preserving a readable conversation column and reading position. Choosing a page replaces the current page rather than adding another card. Opening SHALL require a person choosing its toggle, page or a file/helper link; new browser/helper/file activity SHALL only update a compact indicator. Files SHALL combine project files, chat uploads/generated outputs and authorized reusable saved copies with clear origins; global Library SHALL remain accessible for bulk catalogue work. Setup and Actions/history pages SHALL be removed, with setup controls in their owning composer or destination and chat/message actions under API-018. Opening adds a side column, closing returns width, and narrow layouts SHALL collapse secondary columns before compromising ordinary chat use. The dock MUST NOT cover the transcript/composer, move above the composer or hide the conversation to grow. Resize/collapse/reopen SHALL retain content and run state and follow the application theme. Per-conversation filters, expanded folders, previews, helper selection and reading position SHALL survive tab changes and closing. Hidden Browser views SHALL release frame subscriptions while retaining the session. The idle Browser connection label SHALL describe its actual state and its download shortcut SHALL read Show in Files. Each page SHALL use one outer scroll owner, with separate tree/editor/transcript scrolling only when needed.

#### Scenario: Open, resize, and close
- **WHEN** a person opens the rail to Files, drags the splitter, switches to Helpers and Browser, and then closes the rail
- **THEN** the transcript narrows and widens with the same dock width, only one page is showing, and closing restores the conversation width
- **AND** the answer text is never covered and reopening retains view state.

#### Scenario: Narrow window
- **WHEN** the conversation column is about half a screen wide and the rail is open
- **THEN** an open dock stays beside the transcript/composer while usable, or closes before crowding them
- **AND** reopening retains its page, width preference and content without covering the answer, and widening restores the preferred width.

#### Scenario: Activity without automatic opening
- **WHEN** a browser session starts, a helper works or a generated file appears while the dock is closed
- **THEN** a compact indicator updates and the dock stays closed until a person chooses to open it.

#### Scenario: Contextual file origins
- **WHEN** Files lists a live project file, a chat upload and a reusable retained copy
- **THEN** each retains its existing identity, authority and origin, and preview/reuse does not create a second file catalogue.

#### Scenario: Hidden browser viewing
- **WHEN** a person changes from Browser to Files or closes the dock
- **THEN** live frame subscriptions stop, the browser session remains available, and selecting Browser reconnects to that session.
