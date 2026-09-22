# Tasks: Complete projects, knowledge and external tools

Prerequisites: change 03 and `migrate-local-agent-interaction` must be implemented and verified first. Reuse the shared SDK message/tool/run presentation and application-owned configuration/selection controls; SDK integration does not satisfy packet features. The prerequisite proved and retained synchronous native streaming; this change owns the complete async driver/saver/middleware/resume/cancel/recovery transition. Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence; check tasks only after their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [x] 1.1 Complete folder-backed project identity/defaults and reusable versioned agent setups with composed instruction precedence and current dependency validation.
- [x] 1.2 Add verified changed-file views, supported pre/post text diffs, scoped rename/delete and conflict-aware reversal through existing tool/artifact boundaries.
- [x] 1.3 Verify existing official memory/skills loading and version/conflict/revert protections; complete missing real scope binding, proposal/review/automatic-save permissions and backend provenance without replacing the knowledge owner.
- [x] 1.4 Implement full skill directory/archive packages, safe resources, lifecycle controls and correct next-turn materialization/selection refresh.
- [x] 1.5 Verify the existing opt-in `agents/retrieval.py` and harness scratch path; add local extraction/source inspection for required formats and fitting/authorized long-document use, extending derived retrieval only where needed without mandatory indexing.
- [x] 1.6 Complete shared catalogue and connection/credential lifecycle, then integrate one real public web search/page reader and one real MCP tool path.
- [x] 1.7 Migrate the common harness/saver/middleware/resume/cancel/recovery path to compatible async ownership, including non-MCP Chat and Lab.
- [x] 1.8 Finish existing project, Knowledge and integration UI controls; reuse shared SDK-backed message/tool/run presentation and application-owned setup/connection/selection controls; extend shared retention/backup without creating replacement stores.
- [x] 1.9 Complete the shared everyday workspace presentation: Agents destination for reusable setups, scoped project/Knowledge controls, right-panel file previews/diffs/proposals/activity, Settings connection management and Library-backed retained files/outputs.

## 2. Verify

- [x] 2.1 Test fixed session areas, project aliases/removal, instruction precedence, empty selection, missing scope identity and missing setup dependencies.
- [x] 2.2 Test successful/denied rename/delete, saved grant matching, diff provenance, reversal after a conflicting edit and protected-instruction/forged-actor rejection.
- [x] 2.3 Test memory proposal versus committed save, scope-specific automatic permission, stale base versions, revert and next-turn knowledge/skill refresh on the same thread.
- [x] 2.4 Test complete skill resources, traversal/escaping links/Windows collisions, imported scripts not executing and deselected resources not remaining discoverable.
- [x] 2.5 Test required document formats, corrupt/encrypted/scanned-without-OCR cases, true source ranges, tools-off fitting documents, failed embeddings and stale indexes.
- [x] 2.6 Test no-MCP and MCP async continuity, saved branches/interrupts, session-dependent tools, cancellation/disconnect/restart and clean saver/client shutdown.
- [x] 2.7 Run a real local model through a documentation MCP tool and, separately, public web search plus an actual page read. Verify call/result identity, tool-error semantics, typed elicitation or explicit unsupported outcome and backend-only secrets.
- [ ] 2.8 On Windows, complete a project file task, document-backed answer, memory proposal, skill resource read and connection lifecycle in the existing UI.
- [ ] 2.9 Record technical verification separately from Dave's UX acceptance. Exercise the built Windows everyday workspace journey at full-window and half-screen sizes, with Windows display scaling, keyboard navigation, long content, one failure/recovery state and ordinary Chat after the async transition; leave UX acceptance pending until Dave accepts or explicitly defers review.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.

Implementation evidence (2026-09-22): canonical projects, immutable reusable setup versions, sparse future-turn selections and frozen queued instruction layers are integrated into Projects, Agents and Chat. Knowledge exposes real scopes, backend-owned provenance, exact-destination save policy, proposals, conflict-preserving editing, complete skill packages/resources and lifecycle dependency previews. File changes expose verified before/after text and conflict-aware reversal. Settings owns tested MCP/public-web connections and write-only OS credentials. Shared retained originals support local document/image extraction, version/range source inspection and Library previews. Existing application/checkpoint/knowledge/asset owners and backup remain authoritative.

Technical verification: focused project/Knowledge/setup/package checks, eight file-change regressions, six common async lifecycle regressions, twelve real-protocol connection regressions, three shared lifecycle-preview API regressions, backup/asset checks and the full desktop build passed. The desktop build includes actual-component navigation/queue/selection/conflict/removal tests and the Electron trust-boundary fixture. Real Gemma completed a documentation MCP search plus framework-scoped result read and, separately, public web search plus an actual page read; recorded run IDs and evidence are in `design.md`. Windows native checks passed project folder selection/create, image upload/viewer/model input, exact model-file deletion and the OS credential vault. These are bounded technical results, not the complete required Windows journey or Dave's UX acceptance.

Retrieval verification now includes actual same-thread original → updated → deselected search results and newly offloaded chunk bytes, proving old versions leave the next index while history survives. Eighteen retrieval/project tests pass using explicitly fake embeddings.

Remaining verification: tasks 2.8 and 2.9 stay open until the complete built Windows project/document/proposal/skill/connection journey and final full/half-screen review are exercised. Final sequential backend validation passed 612 default tests and 156 integration tests with no failures or reported skips, including the final retrieval/source-boundary/namespace fixes; the full desktop build and strict OpenSpec 16/16 pass. No Packet 04 UX acceptance or deferral has been recorded.

Final native follow-up: canonical project attachment submission and startup shell recovery were repaired with reproduced component regressions. Repeat the complete project CSV/document/file/proposal/skill journey on the final build before completing 2.8/2.9; final user acceptance remains pending.
