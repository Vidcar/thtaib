# Tasks

Reviewed 2026-09-27: all implementation tasks remain open. The existing case-replay panel and engine smoke are not the new Lab. Complete the API-020 detailed-layout review before substantial interface implementation; no new product code is part of this documentation reconciliation.

## 1. Destination and stored results

- [ ] 1.0 Obtain the API-020 detailed Lab layout approval covering empty, running, stopped and failed states; verify the layout approval is recorded in this design/PR separately from built-product UX acceptance.

- [ ] 1.1 Add Lab to the sidebar so it opens on Performance, with Memory and Challenges available, and verify a focused desktop test that the destination is present and Performance is the first view.
- [ ] 1.2 Store benchmarks, needle runs, challenges, and their results in the application database, and verify a backend test that restart keeps them, they are not Chat conversations, and deleting one leaves the others.
- [ ] 1.3 Show an empty Performance state until a model and a prompt length are chosen, and verify the focused desktop test that Run is unavailable and the screen says why.

## 2. Single stream

- [ ] 2.1 Offer the Models page's legal controls and prompt-length switches, with none selected and generation length starting at 512, and verify a test that a length past the model maximum or the selected context size is absent.
- [ ] 2.2 Run a single-stream benchmark through the loaded model for the exact generation length, keeping prefill speed, generation speed, prompt length, and context length from the server timings, and verify a backend test that no second bench process is started and a short end-of-sequence does not end the sample early.
- [ ] 2.3 Append each finished prompt length to the prefill and generation charts, and verify a focused desktop test that the first length is visible before the second finishes and Stop leaves only finished points.
- [ ] 2.4 Keep benchmark edits off the saved configuration and the saved loaded-model maximum, and verify a backend test that both stored values are unchanged after a benchmark.

## 3. Concurrent serving

- [ ] 3.1 Allow a benchmark to load configurations above the saved maximum and unload only those extras on stop or leaving Lab, and verify a backend test that the saved maximum is unchanged and the extra process is gone.
- [ ] 3.2 Plot each configuration as its own series while its selected concurrent requests run together, and verify a backend test that four concurrent requests on one configuration are measured together and the charts keep one series per configuration.

## 4. Memory

- [ ] 4.1 Build the single UUID, multi-key, and multi-value prompts at five depths that start on, leaving room for the question, and verify a unit test that the multi-key context is other codes, the multi-value test has four values, and the final needle is outside the reserved tail.
- [ ] 4.2 Score answers by exact text and list missing multi-value codes, and verify a unit test that an omitted value fails and a judge model is not called.
- [ ] 4.3 Show each finished depth immediately and keep finished depths on Stop, and verify a backend test that the first depth is stored before the run ends and a stopped run has no result for a depth that did not start.

## 5. Challenges

- [ ] 5.1 List challenges as cards, seed the echo challenge when none exist, and verify a backend test that the first read contains it and a saved challenge appears without removing earlier cards.
- [ ] 5.2 Check required answer text and echo or time_now calls without an approval card, offering no other tool, and verify a backend test that the correct text without echo fails and an echo call does not create an approval.
- [ ] 5.3 Store the task and check with the result, and verify a backend test that editing the expected text leaves the stored result unchanged and the next run uses the edited check.

## 6. Check

- [ ] 6.1 Run `openspec validate lab-workbench --type change --strict` from the repository root, the focused backend tests from `apps/backend`, and `pnpm run build` from `apps/desktop`. Verify each passes.
