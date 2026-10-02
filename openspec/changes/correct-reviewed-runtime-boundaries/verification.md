# Review findings and verification

Updated 2026-10-03. Build, fixes and live Qwen validation are in progress on `codex/verify-qwen-real-journeys`, based on merged `fdea336`.

## Confirmed application defects

Severity follows user impact: P1 can silently discard the user's requested work; P2 breaks a normal workflow or its permission/recovery guarantees; P3 misreports diagnostic information. No P0 was found.

| Severity | Finding and user impact | Resolution and evidence |
| --- | --- | --- |
| P1 | First-turn Edit/Retry after compaction retained the old native summary cutoff, so the new request could be omitted from model context. | Reset native summary/session state on first-turn rewind. Real compiled graph/checkpoint tests prove Edit and Retry include the new input and discard the old summary. |
| P2 | Queue lost acknowledgements could lead to duplicate accepted work. | Stable input identity, read reconciliation, exact retries and newer-draft preservation. Mounted tests cover response/read failures, queue completion, hydration and reopening. |
| P2 | Managed commands and skill scripts bypassed the chat's mandatory first host-command confirmation. | One host-action policy with resolved-folder grants. Ask/Full access, cross-chat grants and exact-action tests; live Qwen managed start produced the required first card in Full access. |
| P2 | Interrupted managed jobs could leave partial changes without a durable continuation hold. | Existing ToolOutcome inspection/acknowledgement boundary now records interrupted jobs. Native file-writing timeout, cancellation, helper settlement/publication, restart and persistence faults exercise the boundary. |
| P2 | Failed preview shutdown could discard ownership and allow chat deletion. | Retain the process-tree owner/handle, expose Retry Stop, and stop before deleting records. Process/handle fault tests and mounted controls prove retry behavior. |
| P2 | A UI preview start could race deletion and create a process for a deleted chat. | Start and deletion share lifecycle admission/conversation locking and recheck membership. Both orderings are covered. |
| P2 | Compact helper discovery omitted the native list of available identities and roles, encouraging invented or unsuitable helper choices. | Preserve the native task description. Actual compiled native helper-schema tests cover both loading modes; natural live delegation is checked separately. |
| P2 | Smoke diagnostics addressed a nonexistent model alias, falsely failing a working loaded Qwen. | Reuse adapter identity resolution and disable router autoload. Baseline live response was 400; corrected live smoke succeeds. Connected ambiguity fails closed. |
| P3 | Shared-router process RSS appeared as model RAM. | Report unavailable when only shared-router RSS is observed. Backend/direct-process tests, mounted screen and native rebuilt UI show RAM unavailable. |

Independent review also challenged the managed-job fix's lock order, late child persistence and split child/root commits. These are correction hardening within this change, with bounded concurrency and persistence-fault regressions; their review closure remains required before delivery.

## Real Qwen end-user work

The installed DavidAU Qwen 27B IQ4_XS runs through the production Chat/Deep Agents/LangGraph application, actual tool discovery, selected helpers and the owned browser. Prompts describe desired outcomes without prescribing tools or output filenames. The saved General agent was explicitly configured for browser interaction; admitted run permissions remain frozen. No task prompt can silently broaden a saved agent's capabilities.

- Game: Qwen created a playable local space game. Independent native Chrome checks passed start, keyboard movement, pause/resume, touch start/pause and phone layout. Scoring, difficulty, lives and restart checks are in progress. The initial agent could not perform all browser interaction because its admitted setup lacked those tools; a fresh correctly configured run is required.
- Website: Qwen produced ten events and the requested controls. Independent browser checks found a favourites ID-type mismatch; other search/filter/sort, RSVP validation/confirmation, theme and phone checks passed. The original run repeated a launcher write 85 times and was cancelled. A natural follow-up has fixed the mismatch and is exercising real browser interaction; final independent retest remains pending.
- Research: Qwen browsed primary MDN/W3C pages and delegated to actual helpers, then saved a report. Independent source checking found an unsupported numeric focus-contrast claim. A natural correction with online/helper evidence checking is underway.

Repeated writing, unsuitable helper selection and unsupported claims are observed model task-quality limitations. The missing helper catalogue is a supported application cause and is fixed; this audit does not attribute every model choice to application code or certify general unattended reliability.

Ignored local evidence lives under `.scratch/qwen-journeys/`: prompts, compact API records, browser test scripts/results and screenshots. It is intentionally excluded from Git to avoid committing model context and product records.

## Automated and live evidence

Baseline desktop acceptance passed in `.scratch/verification/20261002T223835Z-9ed7829b/report.json` before fixes. The first broader run passed 1,455 backend default tests (one declared skip), 202 integration tests (three declared skips), desktop build, contract freshness and OpenSpec validation, but source changed during execution; report `20261002T230522Z-1bf1c1b1` correctly marks acceptance incomplete. It is supporting evidence, not the final gate.

Final affected acceptance, fresh independent review, Git delivery, launcher compatibility and loaded process/build verification are pending. Controlled fault tests establish rare recovery mechanisms; live smoke and natural Qwen browser/helper work establish separate runtime outcomes. Neither substitutes for the other.
