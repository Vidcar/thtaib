# Review findings and verification

Updated 2026-10-03. Delivery is in progress on codex/verify-qwen-real-journeys, based on merged fdea336; initial fixes are committed as c7bade3. Draft [PR 239](https://github.com/Vidcar/thtaib/pull/239).

## Confirmed application defects

Severity follows user impact: P1 can silently discard requested work; P2 breaks ordinary work or its permission/recovery guarantees; P3 misreports diagnostics. No P0 was found. Ten supported application defects were corrected; final combined acceptance and local delivery remain pending.

| Severity | Finding and user impact | Resolution and evidence |
| --- | --- | --- |
| P1 | First-turn Edit/Retry after compaction retained the old summary cutoff, omitting new input. | Reset native summary/session state on first-turn rewind. Real compiled checkpoint/compaction tests prove Edit and Retry include new input and discard old summary. |
| P2 | Lost Queue acknowledgement could duplicate accepted work. | Stable input identity, acceptance reconciliation, exact retries and newer-draft preservation. Mounted response/read failure, completion, hydration and reopening checks. |
| P2 | Managed commands, skill scripts and custom-command previews bypassed first computer-command confirmation. | Shared action-dependent policy with exact argv/resolved-folder grants. Native Ask/Full rejection prevents dispatch; another chat's grant cannot bypass first use. Static HTML keeps its existing policy. Qwen exposed both the managed-command card and the missing custom-preview card. |
| P2 | Interrupted managed jobs could leave partial effects without a durable continuation hold. | Existing inspection/acknowledgement boundary records running jobs and uncertain terminal effects. Native writing timeout, cancellation, helper settlement, restart and persistence-fault checks. |
| P2 | Failed preview shutdown discarded ownership and allowed chat deletion. | Retain process-tree owner/handle, expose Retry Stop, stop before deleting records. Native-handle faults and mounted retry controls. |
| P2 | UI preview start raced deletion, creating a process for a deleted chat. | Shared lifecycle admission/conversation locking and membership recheck. Both orderings tested. |
| P2 | Compact helper discovery omitted available identities and roles. | Preserve official native task description. Real compiled-schema checks cover both loading modes. Qwen selected actual Browser validator/Evidence researcher without tool names or IDs in task prompts. |
| P2 | Smoke used a nonexistent model alias, falsely failing working Qwen. | Reuse adapter identity resolution, disable router autoload. Actual baseline 400 and corrected live smoke success; connected ambiguity fails closed. |
| P2 | Four Auto slots could exhaust one context pool and fail unrelated requests together. | Default omitted managed parallelism to one native slot with Workbench provenance; retain explicit Auto/positive counts and historical identities. Native queue owns waiting. Exact allocation failure gets capacity guidance/Review parallel setting. Actual props show one slot/full 76,800 context; two concurrent native requests returned 200. |
| P3 | Shared-router RSS appeared as model RAM. | Unavailable when only shared-router memory is observed. Direct-process/backend and mounted checks; native rebuilt Models shows RAM unavailable. |

Independent review resolved lock inversion, late child status, split persistence, failed atomic publication, helper-owned cleanup and restart with a saved approval. Each has concurrency/persistence regressions. A later review caught explicit Auto being displayed with the single-slot Shared-context default; selected and historical native facts were corrected and independently reverified. Final independent review is clear.

## Actual Qwen journeys

DavidAU Qwen 27B IQ4_XS ran through production Chat/Deep Agents/LangGraph, discovery, selected helpers and the owned browser. Natural prompts specify outcomes, without exact tools, helper IDs or output filenames. General was configured for browser interaction; admitted runs retained frozen authority. No packages were installed or people contacted.

| Journey | Actual result |
| --- | --- |
| Game creation | Qwen completed a playable space game. Independent Chrome checks passed ten mechanics/touch cases: start, keyboard movement, pause/resume, natural scoring, difficulty progression, life loss/game-over, Space restart, real phone touch movement/clamping/release and mobile pause. Mobile scoring/game-over/tap-restart were not separately tested. |
| Featured website | First output had a favourites ID mismatch; search/filter/sort, RSVP, theme and phone layout passed. Qwen's follow-up fixed favourites then rewrote incompatible DOM identifiers, breaking the page. Later one-slot targeted repair passed all ten independent checks: 10 events/no errors, search, categories, sorting, saved favourites, validation, confirmation and phone layout. Theme colors also change correctly; the initial retest falsely failed by reading before the CSS transition, corrected with bounded observed-color polling. No helper was used in that completed repair. |
| Online research | Initial Qwen browsed MDN/W3C, used helpers and saved a report; independent checking found an unsupported 2:1 focus-contrast claim. Thinking-enabled follow-ups repeated todos/writes. Final thinking-off source/helper correction is in progress. |
| Helper validation | Qwen correctly discovered Browser validator and prepared the static preview itself. Helper repeated 76 snapshots without interacting; cancelled deliberately. Discovery/delegation worked; the helper journey did not complete. |

Missed independent review, unsupported claims and repeated calls remain model task-quality limitations. Read-only reconstruction of real native checkpoints found unique calls with matching fresh results, growing context and valid compaction: no supported application replay/context-loss cause for loops. This does not certify unattended Qwen reliability.

Shared-context failure is separate. b11045 logs show an earlier helper's 86 text snapshots grew to 57,495 input tokens; website/research added about 14,253/5,316. Combined demand exceeded the 76,800 unified pool. Allocation retries reached one token, then native failure cleared all processing slots. These were text snapshots, not image overhead. Disabling MTP alone did not stop repetition. Early purported no-MTP tests still loaded MTP because an empty startup patch preserves launch settings; excluded from A/B conclusions. Later tests explicitly replaced startup and verified actual argv/props.

Primary checks: [W3C Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html), [Focus Appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html), [No Keyboard Trap](https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html), [MDN KeyboardEvent.key](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key), and [pinned native allocation error path](https://github.com/ggml-org/llama.cpp/blob/b11045/tools/server/server-context.cpp). AA contrast and AAA focus-area/contrast requirements remain distinct.

Ignored evidence: .scratch/qwen-journeys/ natural prompts, actual runs, independent browser checks/screenshots, native props and queue results. Excluded from Git to keep model context/product records private. Original saved model setup, weights and runtimes remain intact; test chats/work are disposable.

## Verification

- Baseline desktop acceptance: 20261002T223835Z-9ed7829b on fdea336.
- Stable c7bade3: backend 20261002T234628Z-e6bfccb5 passed 1,463 default tests (one declared skip) and 202 integration (three declared skips). Desktop/spec/docs 20261002T234853Z-fea03891 passed build/spec. Shared contracts matched. Initial independent chat/model/permission reviews cleared.
- Focused additions: 159 model tests plus desktop consumers (20261003T001151Z-c2b636e4); desktop pool recovery (20261003T001509Z-5ba227c4); 35 custom-preview permission tests (20261003T001646Z-eafda056). Final independent permission/runtime/UI review is clear, including 88 settings-consumer tests and native grant reuse/rejection exercises. The final 178-test focused run passed its code/desktop checks but was incomplete because this report changed during execution; stable acceptance follows.
- Earlier broad 20261002T230522Z-1bf1c1b1 and 20261002T233522Z-7d5e2540 passed individual checks but detected concurrent edits. Supporting evidence only.

Final combined acceptance, reviewed Git delivery and final process/bundle/launcher identity are pending. Controlled faults establish rare recovery mechanisms; actual model/browser/UI checks establish separate live outcomes. Neither substitutes for the other.
