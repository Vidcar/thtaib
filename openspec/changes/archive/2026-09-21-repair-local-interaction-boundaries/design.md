# Design

## Context

See proposal.md for motivation. Baseline is main 87e0f507, matching the source review. Chat currently changes conversation before registration, and background hydration/cancel callbacks select records. Electron 44.4.3 injects tokens by destination without requesting-document proof. Interaction seeding greedily matches equal text from the start and appends checkpoint rows; existing registration skips seeding. The migration remains delivered.

## Goals / Non-Goals

Repair ownership and presentation using existing SDK, runtime and SQLite owners. Do not add a message reducer, persistent queue, second execution path, general browser or async transition. Packet 03 remains separate and Packet 04 owns async work.

## Decisions

- Use one selected conversation/binding generation, with safe registration loading and guarded callbacks. Cache updates do not select. Capture command configuration and draft identity before awaits; accepted runs continue under backend ownership. Merely checking conversation ID fails away-and-back navigation.
- Keep URL parsing/validation and navigation denial in Electron main. Verify the current exact application document and main frame as well as WebContents and backend origin for each token injection. Reject unknown frame evidence. Destination-only or ID-only checks do not establish the caller's authority.
- Align readable history with retained checkpoint messages in order using durable identity and suffix/provenance evidence. Keep uncertain history display-only; preserve content-block/reasoning representations and interleaved tools. Repair only an identified old seed region when evidence supports it; respect display replacement/exclusions/cutovers and retain later projection output. Blind reseeding would erase edits or partials.
- Reproduce before fixes with controlled component promises, real backend fixtures and an actual Electron receiver. Keep Windows model checks separate from deterministic fixtures.

## Risks / Trade-offs

- Legacy identity may be unprovable: preserve original archive with deterministic display identity and report uncertainty rather than invent correspondence.
- Electron frame metadata differs by lifecycle: use installed APIs and fail closed, exercising both development and file-document modes.
- Async UI acknowledgements outlive mounts: generation plus draft revision prevents stale writes without cancelling accepted work.

## Migration Plan

Validate on disposable roots/copies first. Preserve runtime/checkpoint association and model weights. Narrow repair stays within application projection persistence and is repeatable; no private checkpoint manipulation. Build and run the repaired local desktop, then synchronize/archive only verified contracts. Record actual results here before delivery; keep Packet 03 blocked until completion.

## Verification evidence

- Baseline 87e0f507 repeated-text backend reproduction failed with `First answer / Continue / Continue / Second answer` before repair. Repair now requires exact old-seed records and deterministic UUID provenance; a matching text multiset alone is rejected. Unmatched ambiguous execution history is not appended to the readable archive or reintroduced by later values.
- Recovery/display modules: 23 tests passed, covering repeated user/assistant text, ID-less tools/reasoning/blocks, ambiguity, exact faulty-seed repair, later/partial output, known IDs, display edits, isolated database-copy repair and same-runtime-thread continuation with one explicit scripted invocation.
- Backend default: 351 tests passed; integration: 147 tests passed; generated shared contracts are current. Installed dependencies verified with `uv sync --check --locked` (no changes); documented `--no-sync` used while backend processes are running.
- Actual Windows built Electron app through its production main/preload and unchanged CSP: Qwen3.8-27B at existing loopback8080 with disposable backend data. Observed incremental content, navigated to New during generation, revisited/cancelled, reopened retained partial output and continued on the same thread. Exactly two application runs; final answer `AZALEA`, four distinct rendered samples and no renderer errors. Evidence under `.scratch/repair-live/`; this establishes the exercised text/continuity flow only.
- Isolated backend rejects missing/wrong tokens with 401/403. Actual Windows Electron 44.4.3 receiver checks reproduce the original same-session window/frame token injection and in-app external window. Production boundary passes development and file-document modes: trusted requests authenticate; untrusted windows/frames, replaced documents and spoofed headers do not; backend redirects do not forward the token. Actual Markdown clicks deny new in-app windows and route validated HTTP(S) to a captured system-browser call. Relative/protocol-relative/fragment/file/custom links, redirected navigation, missing and destroyed frame evidence are checked. No external browser is launched by the harmless fixture. These checks use received headers, not CORS outcomes.
- Actual Chat component plus stock SDK/loopback fixture: 12 controlled cases pass. The reviewed baseline fails 10 cases independently: held binding, hydration after New/B/away-back A, delayed cancellation, abandoned create/register, submission while loading, same-selection newer-run protection and newer-draft isolation. Positive controls verify unchanged submitted draft clearing and accepted command ownership/revisit. Fixtures wait for response consumption and real subscriptions, use controlled barriers, and verify selected run metadata as well as visible SDK output. Agent-run delayed cancellation/new-run ownership also passes; analogous Lab observer ownership is guarded.
- Final `pnpm run build` passes typecheck, existing SDK/StrictMode/Markdown/interrupt/Packet 02 settings checks, the new Chat/Agent-run tests and actual Electron receiver fixture. Only existing bundle-size/bundler warnings remain. No dependencies changed. The final production desktop/model rerun passed with two runs, four incremental samples, cancelled then completed status, same runtime thread, answer `AZALEA` and no renderer errors. This exercises built file-document Electron and actual local inference, not an NSIS installation or untested model modalities.
