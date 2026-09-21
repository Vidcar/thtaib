# state-recovery delta

## MODIFIED Requirements

### Requirement: STATE-005 - Version durable knowledge and enforce its write policy

Durable knowledge SHALL preserve user/agent/project scope identity, memory/skill/protected-instruction kind, append-only versions, provenance and reversible edits through new versions. Project/agent scope requires a real corresponding record; legacy unbound entries remain explicitly unbound. Writes SHALL name an expected base version and reject conflicts. Backend-assigned actor provenance MUST prevent agents impersonating human writers; protected instructions reject agent-origin writes.

Agent learning SHALL first be a reviewable proposal with content, destination scope and provenance shown; a proposal is not a saved memory. Automatic saving requires explicit permission for that scope, independent of ordinary tool/file grants or document supply. Scratch edits become durable only through an authorized successful commit. Context-capture collection, retention and redaction remain separate local diagnostic configuration. Referenced versions and historical/backup copies follow shared deletion/backup rules.

#### Scenario: Knowledge write policy

- **WHEN** knowledge is edited, reverted, concurrently updated or targeted by an agent-origin protected write
- **THEN** version history and base-version conflicts are enforced; forged actor/protected writes fail and diagnostic configuration applies.

#### Scenario: Propose and save

- **WHEN** an agent proposes a memory without automatic-save permission for the displayed scope
- **THEN** the user reviews the actual content/destination before a durable commit; ordinary file permission does not bypass this step.

#### Scenario: Scoped proposal review

- **WHEN** a memory proposal targets user, project or agent scope from the conversation
- **THEN** the review surface shows the proposed content, provenance and exact scope in plain language, with technical version details available on expansion.

### Requirement: STATE-006 - Retrieve through LangChain components, not a second knowledge store

Retrieval SHALL be opt-in, require an explicitly selected usable embedding deployment and use LangChain components over selected knowledge/document versions and allowlisted project text. Validate the actual embedding response, pooling/configuration and corpus; missing, unloaded or unusable dependencies and empty requested corpora fail actionably with no invented hits. In authorized live-tool retrieval runs, auto-present the existing shared `search_knowledge` tool without overriding tools-off. Direct project/document reading, memory and skills MUST remain usable without embeddings.

The derived per-run index is not a durable knowledge owner and SHALL be discarded with the run. Source updates/removal invalidate stale selections/indexes. Retrieved content SHALL carry original version/range attribution in scratch/captures, not be written as project output. Knowledge-only runs use normal memory/skill/protected-instruction loading and do not fail merely because retrieval is absent.

#### Scenario: Retrieval with and without embedder

- **WHEN** retrieval is explicitly selected with usable content/embeddings or with an invalid dependency
- **THEN** valid results retain actual source ranges in scratch; invalid requested retrieval fails without fabricated hits, while non-retrieval Chat remains usable.

## ADDED Requirements

### Requirement: STATE-012 - Keep canonical projects and supported file reversal distinct

Projects SHALL bind an authorized existing folder to stable canonical identity, permit browsing/defaults, and distinguish original storage from temporary/restored workspaces. Removing a project removes its active binding, not the source folder or historical session area. Project files, retained originals, derived documents/retrieval, framework history/offloads and materialized knowledge SHALL remain separate.

Supported file operations SHALL record successful outcome, run/tool identity and observed pre/post content for created/modified/renamed/deleted states and text diffs. Capture needed preimages before editing. Rename/delete require selected registered operations, current policy and matching approval/grant. Reversal SHALL be offered only with sufficient evidence and while current content still matches the recorded postimage; conflicts block overwrite. It is not undo for arbitrary shell commands, remote actions or entire runs, and must not require copying the whole project for every edit.

#### Scenario: Reverse after later edit

- **WHEN** a user requests reversal after another actor changed the recorded file
- **THEN** the content mismatch blocks reversal rather than overwriting the newer edit.

#### Scenario: Remove project

- **WHEN** a project binding is removed
- **THEN** source files and required historical identity survive; sessions are not moved to non-project.

### Requirement: STATE-013 - Retain complete versioned skill packages without executing imports

Skill import SHALL accept existing single-file skills and complete local directories/archives containing SKILL.md and safe relative scripts/references/templates/assets. Preserve manifests, file hashes/provenance and versions; reject invalid required frontmatter/resources, traversal, escaping links and Windows path/case collisions. Selected immutable resources SHALL materialize through official scoped skill discovery, not another registry.

Inspect, enable/disable, update and remove SHALL use normal knowledge version/retention rules; updates create versions and refresh derived state. Import MUST NOT execute scripts, install dependencies or grant tools. Transfer to an authorized host/isolated environment is a separate provenance-preserving operation: availability in a virtual backend does not establish host execution availability. Missing execution support remains visible.

#### Scenario: Package resources

- **WHEN** a valid skill archive includes referenced templates and scripts
- **THEN** all permitted resources remain versioned/discoverable, but nothing executes or receives permissions merely through import.

#### Scenario: Unsafe package

- **WHEN** an archive contains escaping paths or conflicting Windows names
- **THEN** validation rejects it before materialization outside the scoped package.

### Requirement: STATE-014 - Extract local documents with verifiable source ranges

Shared retained originals SHALL support local extraction of text/code, CSV, JSON, text-bearing PDF and DOCX with parser/version, status and source-labelled derived content. No hosted parser or native vision route is required. Malformed, encrypted, empty and unsupported inputs SHALL have truthful outcomes; scanned documents without implemented OCR MUST NOT be reported understood.

Users SHALL inspect extraction and open originals from actual source references. Preserve available PDF pages, DOCX paragraphs/headings and structured row/field ranges without invented coordinates; references identify source version and actual read/retrieved ranges. A filename is not proof of reading. Fitting content enters labelled current-user input, including tools-off; longer content uses authorized scoped read/search and context handling or a capacity outcome without silent truncation. Do not automatically index or promote session attachments to project/global knowledge. Derived data extends shared lineage/deletion/backup.

#### Scenario: Source-backed answer

- **WHEN** an answer uses extracted document content
- **THEN** its reference opens the retained source version and actual supported range, not an invented page or filename-only claim.

#### Scenario: Unsupported extraction

- **WHEN** a scanned/encrypted/malformed document cannot be extracted
- **THEN** the actual limitation is shown without claiming understanding or silently using a hosted service.
