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
