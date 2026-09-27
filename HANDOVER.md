# Current handover

Updated 2026-09-27. Dave's documentation review is complete in [PR181](https://github.com/Vidcar/thtaib/pull/181): all nine main OpenSpec capabilities and five formerly active changes were checked against current source, tests and delivered changes. This is a documentation-only delivery; no application, deployment or product data was changed.

Completed: archived the already-synced `rewrite-loaded-boundaries` and `chat-stream-follow`; restored two missing archived Models delta files; retired obsolete warming and duplicate Lab/consolidation deltas; corrected the duplicate Models requirement ID and stale packet/connection/prerequisite wording. Main specs now distinguish accepted targets from delivered features. Skill import, document reading and current Connections/public web are marked delivered. Lab planning is tracked rather than left uncommitted.

Three changes remain, with actual implementation work only:

- [lab-workbench](openspec/changes/lab-workbench/tasks.md): no implementation completed; loaded-server Performance, Memory and Challenges replace the older Lab target. Detailed layout approval precedes substantial interface work.
- [consolidate-product-contract](openspec/changes/consolidate-product-contract/tasks.md): workflow registry/validation, LangGraph execution, React Flow canvas, ComfyUI and speech. Existing task runner is not a delivered workflow editor.
- [startup-catalogue](openspec/changes/startup-catalogue/tasks.md): failed initial lists stop after thirty retries and can appear empty. Finish truthful retry/recovery and its mounted/live verification; do not restore automatic model warming.

Validation: 99 focused backend tests passed; six existing desktop checks passed (Knowledge, Settings, dock, transcript following, stream ownership, conversation restoration); strict OpenSpec validation passed; all 186 documentation files have valid local links and current requirement IDs are unique; whitespace passed. No fresh runtime capability/performance claim is made.

The latest installed responsiveness repair remains [PR179](https://github.com/Vidcar/thtaib/pull/179), archived in PR180. Existing runtime evidence/backups and unrelated worktrees remain preserved. Next feature work should use the remaining change tasks; none was started during this review.
