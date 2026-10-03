## MODIFIED Requirements

### Requirement: ENV-030 - Use one owned Chrome context for agents and browser viewing

Selected Browser access SHALL run actual Chrome without a visible operating-system browser window, with a dedicated persistent profile per conversation. Agent tools and the interactive Chat view SHALL use the same pages, tabs and viewport. Start and first browser actions SHALL launch it; close and expiry SHALL stop the owned process tree while retaining sign-ins. Reset SHALL clear the confirmed stopped profile after confirmation. Chrome availability SHALL be checked separately from worker installation. Structural and visual interaction, scrolling, dragging, page dialogs, permitted uploads and retained downloads SHALL use the existing access/effect rules. Unrestricted code, page-defined tools and the ordinary browser profile MUST NOT be exposed.

#### Scenario: Start and resize Chrome
- **WHEN** an authorized agent opens a page and changes its viewport
- **THEN** the live rail shows that same Chrome page and its actual dimensions without opening a desktop browser window
- **AND** rail resizing only changes display scale.

#### Scenario: Browser files remain scoped
- **WHEN** an agent uploads a project file or selected attachment and downloads a page file
- **THEN** the upload is resolved under current file authority and the completed download is retained with source attribution in the existing Library
- **AND** unrelated host files and arbitrary output destinations are refused.

#### Scenario: Page identity changes
- **WHEN** a popup opens, duplicate addresses exist, or a session is reset
- **THEN** the view follows the selected stable page identity and stale input/frames cannot target a different page.

#### Scenario: Lost worker
- **WHEN** the worker fails during an action
- **THEN** its live session is reported lost, the action outcome is preserved without replay, and retained sign-ins are distinct from the lost pages.

#### Scenario: First navigation with concurrent viewing
- **WHEN** the first authorized browser action launches Chrome while the live view or status monitor observes its startup
- **THEN** observation waits for coherent initialized page state and the action continues in the same owned context
- **AND** partially initialized state MUST NOT establish browser loss or cause a healthy browser to be terminated.

#### Scenario: Recover a lost browser without clearing sign-ins
- **WHEN** a lost session is closed and a fresh session is started
- **THEN** the existing Close/start path retains the conversation profile and recovery guidance identifies it distinctly from Reset
- **AND** neither recovery path automatically repeats completed or uncertain actions.

#### Scenario: Background live-view failure
- **WHEN** background frame capture fails while a foreground browser action succeeds
- **THEN** the live-view error remains observable without changing that action's successful result
- **AND** actual foreground action failures, directly requested frame failures and genuine worker loss retain their existing error and recovery boundaries.
