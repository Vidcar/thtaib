# Current handover

Updated 2026-10-03. [Task 02 #245](https://github.com/Vidcar/thtaib/issues/245) is being verified/reviewed on `codex/executable-baseline`. Dave selected 1A/2A: retain useful existing checks, add five compact browser journeys, actual Windows Electron smoke and bounded real-model plumbing. Use existing assets; deeper model interaction work belongs to Tasks 03–04. Real models remain essential during feature development.

Initial source findings for all pending tasks are in [context #243](https://github.com/Vidcar/thtaib/issues/243#issuecomment-5972194765). Later tasks/decisions remain unverified Backlog / Needs review; no blanket approval. Preserve original issue appendices and provisional order.

Implemented: Playwright 1.62.1, authenticated test-only native backend, rendered journeys, isolated Electron startup and mandatory case reporting. Desktop build passed; five browser journeys passed with no skips/retries, and deliberate draft loss failed the expected visible assertion. Actual built Windows smoke passed (rendered conversation, authentication, main/preload/PID/profile/sandbox/native IPC). Copied renderer assets match the build; only its test backend CSP differs. Default backend: 1517 passed with one legacy skip. Latest focused runner/fixture: 30 passed.

Existing CPU llama.cpp build 11045 and Qwen2.5 0.5B Q4 assets passed four isolated real-model smoke cases (6.6s). This proves bounded backend/model plumbing, not model quality or desktop delivery. No downloads/upgrades or product data changes. Runtime identity is in `.scratch/executable-baseline/native-baseline.json`.

Prior cleanup is complete: [#264](https://github.com/Vidcar/thtaib/issues/264), [PR265](https://github.com/Vidcar/thtaib/pull/265), [PR266](https://github.com/Vidcar/thtaib/pull/266). Main contains handover commit `b9a47b0`; no Task 02 implementation commit/PR yet.

Independent cross-review corrected canonical storage/temporary guards and failure-path cleanup; current follow-ups strengthen Node pre-write validation, teardown error reporting and actual reload process replacement. Agents own separate files. Next: close review findings, run final delivery gates on stable inputs, record evidence, then commit/PR/merge Task 02. Preserve native owners/SDK patch/product data; keep remote CI disabled.
