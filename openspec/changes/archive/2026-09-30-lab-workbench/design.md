# Design

## Context

See proposal.md. Lab is off the sidebar. The panel that remains is the older case-capture flow, and its only speed action runs llama-bench with a fixed 16-token prompt and 8-token generation, then shows the raw result. Model loading, legal context sizes, and server timings already exist. Chat publishes generation speed from those timings and does not publish prefill speed. The application database is the store for mutable records. No chart component is installed.

## Goals / Non-Goals

**Goals:**

- Reuse the model loader, legal configuration choices, and server timings.
- Keep Performance, Memory, and Challenges buildable in that order after the shared destination and result store.
- Leave saved configurations and the saved loaded-model limit unchanged.

**Non-Goals:**

- A second model launcher or llama-bench as the measurement.
- Deleting the case-capture implementation in this change.
- Challenge-specific tools, variable tracking, or a plain-sentence needle.
- Workflows, image generation, and speech.

## Decisions

### Measurements go through the loaded model

Single stream and Memory load a configuration with the existing loader and the saved maximum. The benchmark request asks for the selected generation length and tells the pinned server not to stop at end-of-sequence, so a short answer cannot end the sample early. The implementation confirms that control's name against the pinned runtime. Prefill speed, generation speed, prompt length, and context length are taken from the timings the server already returns. Chat's generation readout stays as it is.

Alternative considered: llama-bench with the same flags. Rejected because it loads a second copy of the weights and cannot run concurrent requests through the server.

### Concurrent serving borrows capacity

A concurrent benchmark may start configurations above the saved maximum. Those extra loads are marked as benchmark-owned. Stop and leaving Lab unload only the benchmark-owned extras. The saved maximum is not written. Configurations that already fit the maximum stay under the normal loader.

Alternative considered: requiring the person to raise the maximum on the Models page. Rejected because the benchmark must not change that setting.

### One chart component

Performance adds one chart dependency that can append a point to a series without rebuilding the history by hand. Prefill and generation are two charts. Each saved benchmark is a series. A hand-drawn canvas is not used.

Alternative considered: drawing the chart in application code. Rejected because the series, axes, and live points are the whole screen, and a one-off drawing becomes the component anyway.

### Results live in the application database

Benchmarks, points, needle runs, challenges, and challenge results are rows in the existing application database under the local data root. A result stores the check or settings it was scored with. Delete removes those rows. Nothing is written into a saved model configuration.

### The new Lab replaces the sidebar entry only

The sidebar destination opens Performance, Memory, and Challenges. The case-capture panel is not deleted and is not a sidebar destination. Its remaining requirements stay in `lab-evaluation`.

### Needles are generated locally

UUID values and filler are produced for the run. Depths are the start, one quarter, one half, three quarters, and the last position that leaves a reserved tail for the question and a short answer. No external essay corpus is required.

### Challenge tools skip approval

A challenge run offers only echo and time_now, labeled Echo and Clock. Those calls are not sent through the approval interrupt. The run is not a Chat conversation.

## Risks / Trade-offs

- [The pinned server uses a different name for disabling end-of-sequence] → Confirm it in the single-stream task before accepting a short sample as a 512-token result.
- [A long prompt length dominates the benchmark] → Points appear per length, and stop keeps finished lengths.
- [Concurrent extras exhaust memory] → The failure is shown and the benchmark-owned processes are unloaded. No speed is invented.
- [Case capture becomes unreachable] → Accepted for this change. Removal of that screen is a later decision.

## Migration Plan

Ship the destination and result store first, then Single stream, Concurrent serving, Memory, and Challenges. Rollback removes the sidebar destination and leaves saved Lab rows unread. Saved model configurations are untouched, so rollback does not restore model settings. On archive, set the `lab-evaluation` purpose to the remaining case-capture contract. The delta does not do that edit.

## Open Questions

No unresolved behaviour choices. Confirm the end-of-sequence control and available timing fields against the pinned runtime during implementation; do not infer those fields from a chart design. API-020 requires an approved detailed Lab layout before substantial interface implementation, and technical verification remains separate from acceptance of the built experience.

## Implementation and acceptance record (2026-09-30)

Implementation is authorized by Dave's request to complete this existing change, including real-local-model QA/UAT in the application on this computer. Layout review and Dave's acceptance of the built experience are recorded separately below; authorization to implement is not visual acceptance.

### Impact and existing owners

The new desktop destination calls a backend Lab workbench service alongside the retained case-replay service. New mutable records use the existing application database; model loading and temporary extra processes remain owned by the existing model/deployment services. Performance and Memory call the loaded llama-server; Challenges use the existing Deep Agents harness with only Echo and Clock. No Chat conversation, alternate agent loop, benchmark launcher or saved model-setting owner is introduced.

The pinned b11045 native router fixes its loaded-model limit at startup. Temporary concurrent capacity therefore uses the existing managed-deployment launcher for explicitly Lab-owned extras, preserving ordinary router loads and the saved limit. Extra ownership must survive long enough to clean up stop, leave, failure and application shutdown/recovery safely. Saved configuration and application-setting hashes will be compared before and after real-model runs.

### Acceptance plan

- Automated: focused Lab store/service and desktop regressions, including incremental results, stop/failure/restart, exact token lengths, legal controls, concurrent ownership, tool restriction and immutable challenge checks; full affected backend/integration, desktop build, shared contracts and OpenSpec gates.
- Independent: fresh-context review of the concrete diff, lifecycle boundaries and whether tests detect violations. Supported findings are fixed and affected checks rerun.
- Native: built Electron main/preload/renderer and repository backend, installed local GGUF and runtime, isolated disposable data. Exercise all three Lab views, full and half windows, actual display scale, keyboard, long answers, failure/recovery, restart and deletion. Record build/process/model identity and actual server measurements. API calls alone are not desktop UAT.
- Delivery: merge through the existing repository workflow and verify the established local launcher uses the delivered build. Keep protected product data and weights intact.

Detailed layout review: **approved by Dave on 2026-09-30**, after presenting the interactive `.scratch/lab-workbench/layout.html` preview at `http://127.0.0.1:8769/layout.html`. His explicit answer was "Approve this layout". It covers compact setup with separate prefill/generation charts; empty, running, stopped, failed and complete states; full/half-screen arrangements; expandable load controls; concurrent configuration rows; Memory depth answers and missing values; challenge cards, editor/history and deletion confirmation. This approval permits interface implementation. Built-product UX acceptance by Dave remains pending. Agent-driven technical QA/UAT is complete; Dave has not yet accepted or deferred the built experience.


### Implemented behavior and evidence

- Native b11045 `ignore_eos` plus exact `n_predict` produced 256, 512 and 1024 tokens through the loaded server. Recorded `tokens_evaluated`, `tokens_cached` and native timings drive the chart axes/speeds. Oversized requested input is shortened to reserve output within the actual per-slot context; requested and observed capacities remain visible.
- Concurrent trials use the existing loader. Above-limit children have exact Lab ownership and process identity; normal models remain protected. Identical loading plans aggregate their request slots while keeping one series per saved configuration. Native evidence shows two slots launching before either finishes, `total_slots=2`, and two 512-token results on one process.
- Memory uses native tokenization/chat templating to reserve the question and answer. All three tests completed all five depths with the real model; exact expected/missing values were independently checked. Stop preserved the first completed depth and omitted unstarted depths.
- Challenges run the shared harness with only Echo and Clock, excluding its implicit reader through existing input policy. Live Echo/Clock, text-only and tool-only checks passed. Correct text without Echo failed, editing the required text affected only the next result, and no Chat conversation was created.
- Runs/challenges survived normal application Quit and restart. Confirmation cancellation preserved everything; confirmation removed one selected result only. A 57-card list and bounded long task/answer content worked. Deleting every challenge left add guidance without reseeding.
- A controlled renderer status-read failure kept prior points and recovered on Retry. Interrupting only the isolated model child after the first point produced a failed later measurement without zero speeds; re-running loaded successfully. Saved configuration bags and maximum-loaded-models=1 remained unchanged. Temporary children and test-only records were removed; installed weights were unchanged.

Native evidence is under `.scratch/lab-workbench/candidate-20260930-022406/`: `phase1.json` through `phase5.json`, `qa-summary.json`, native reports/screenshots, native process logs and clean-shutdown session reports. It used the actual built Electron main/preload/renderer and repository backend with separate disposable data, the installed Qwen3.5 4B Q4_0 model and CUDA b11045 runtime. Windows sidebar/arrow-key interaction and Electron input exercised the app, with independent API/process reads corroborating outcomes. Actual Windows display scale was 200%; full 1440×852 and half 720×852 DIP windows plus 125% renderer zoom were checked. Screenshot review supplemented interaction and state assertions.

Independent review found and resolved extra-model cleanup, scoped leave, stale response ordering and aggregate-slot defects. Twenty backend Lab regressions and the restricted-harness tests pass. Native UAT found a cramped Generation label; two Lab-local CSS rules repair it. The new native geometry check fails with only those fixes removed (8.9-pixel, 15-line label), then passes full/narrow at both zoom levels. Existing build guards were retained.

Backend acceptance evidence: `.scratch/verification/20260930T011917Z-286027f7/` has 1,288 default and 220 integration tests passing (suite-declared optional skips: one and three). Shared-contract freshness also passed. Its overall changing-tree result is intentionally not a current-tree acceptance claim: desktop fixes and documentation changed during that run. Every backend input hash still matches the passing suite snapshot; final affected desktop/spec acceptance is recorded in the delivery handover/PR. Full desktop build and strict change validation have passed; final checks are repeated after closeout edits.
