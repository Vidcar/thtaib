# Current handover

Updated 2026-10-03. Rebuild plan review is active; application implementation has not started. Dave requests ticket-by-ticket scope/decision review, treating tests and proposals as unverified. GitHub issues remain the planning source.

Read AGENTS, Project README, all pending issue appendices/relationships, owners/callers/tests and locks against clean main `77385a0`. Initial findings for every pending task are in [context #243](https://github.com/Vidcar/thtaib/issues/243#issuecomment-5972194765). This is source review, not executable validation or blanket approval.

[Task 02 #245](https://github.com/Vidcar/thtaib/issues/245) recommends eight safety behaviours in five compact journeys, separate actual Electron smoke and bounded real-model plumbing. Dave's coverage/real-model choices remain pending. Address zero-stream false-green, mandatory skipped-case reporting, isolated desktop/service/profile startup and build/process identity. Preserve useful tests; replace weak/obsolete assertions as each feature changes. Playwright metadata exists; installation/Windows compatibility is untested. Tiny-model weights exist; the smoke's Windows runtime override is unconfigured.

All pending tasks/five decisions remain Backlog / Needs review; saved bodies/statuses were read back. Later choices include editable files, retained-output Library placement, Settings grouping, document scope, Lab replay and standalone Windows backend delivery. Keep order provisional; distinguish technical prerequisites from delivery order.

Prior documentation/cleanup is complete: [PR242](https://github.com/Vidcar/thtaib/pull/242), [#264](https://github.com/Vidcar/thtaib/issues/264), [PR265](https://github.com/Vidcar/thtaib/pull/265), [PR266](https://github.com/Vidcar/thtaib/pull/266). Proposals, captures and product data remain preserved. No application tests/builds/installs/model calls/launches were performed. Documentation/whitespace verification passed: `.scratch/verification/20261003T183217Z-53df5efc/report.json`.

Next: obtain Task 02 decisions in chat, record scope/acceptance, then continue through remaining tickets/decisions. Ready also requires satisfied prerequisites. Keep remote CI disabled; no application restart is needed.
