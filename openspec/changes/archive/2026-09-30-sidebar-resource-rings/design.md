# Design

## Context

See proposal.md. `MemoryEstimator.hardware` already owns one thread-safe `HardwareObserver`, using `psutil` and a hidden, two-second-bounded NVIDIA command. Models consumes available/total budgets and the legacy overall observation time/stale flag. `WorkbenchSidebar` renders the always-present 54px destination rail. No new runtime or dependency is needed.

## Goals / Non-Goals

**Goals:** Implement API-055 with shared hardware ownership, independent metric freshness and presentation-local updates.

**Non-Goals:** GPU compute utilisation, additional GPU vendors, telemetry history, model scheduling, additional settings, hover/click disclosures or startup-status changes.

## Decisions

- Extend the existing observation additively with device `used_bytes` and root `gpu_observed_at`, `gpu_stale`, `ram_observed_at`, `ram_stale`. Preserve existing available-memory fields and conservative legacy GPU-budget staleness. A missing used value must not invalidate a still-valid available-memory budget, and failed RAM reads must remain null for Models rather than become a cached fresh budget.
- Expose `/v1/system/resources` from the existing model-manager router using its shared observer directly. Keep default five-second caching for existing callers; the monitor requests a two-second maximum cache age. The synchronous route runs blocking probes in FastAPI's worker pool, under the existing observer lock.
- Retain last valid percentages in a component-local projection. Poll visible windows every two seconds, abort after four seconds, expire after ten seconds, and guard callbacks by observer generation. Hidden/unmounted windows dispose requests/timers. No update is lifted into App or Chat.
- Draw two 36px SVG circles with theme-based fills and whole-number tabular percentages. Blend existing `--ok`, `--warn` and a desaturated `--danger` using CSS colour mixing. Use the fixed rail's available interior and compact vertical spacing; respect reduced motion.
- For multiple GPUs select the greatest valid used/total ratio, with deterministic device-ID tie breaking. Incomplete GPU observation is grey; accessible text carries device and stale/current state. Unknown values have no numeric meter claim.
- Preserve recoverable device budgets when only used-memory data is missing. Unrecoverable/skipped device rows stale the overall budget as well, preventing an incomplete device list from becoming a current single-GPU estimate.
- Reserve the rail footer and let destination icons scroll in short windows. Native regression checks verify Settings hit targets, both rings, the service dot and the final scrollable destination, in both themes through 200% zoom.
- Reuse `psutil`/`nvidia-smi` instead of adding NVML bindings or native DIY code: the actual host probe takes approximately 47ms and the two-second shared cache is sufficient.

## Risks / Trade-offs

- GPU driver tools may fail or return N/A -> keep honest independent stale/unavailable states, strict numeric bounds and bounded subprocesses; RAM continues.
- A new monitor could change Models budgets or cause duplicate work -> preserve legacy observation semantics and share its singleton/lock/cache; test both consumers and failure paths.
- The bottom stack consumes more height -> native checks cover short/scaled windows without widening or hiding destinations.
- An old process could appear to validate the change -> check candidate build/process identity, use isolated native UAT, then restart the established local deployment while preserving saved user data/drafts.

## Migration Plan

No stored-data migration. Generate additive shared contracts and build the candidate, run shared/spec acceptance and fresh-context review, validate live/native behaviour with isolated data, then merge and refresh the existing local application. Reverting the feature changes restores the previous rail without affecting stored models or chats.

## Validation evidence

Focused backend checks: 50 tests passed in `.scratch/verification/20260930T120735Z-d027af48/report.json`. Final shared/spec acceptance passed in `.scratch/verification/20260930T122551Z-5200e7e1/report.json`: 1,301 default backend tests and 220 integration tests (one and three existing suite-declared skips respectively), full desktop build, generated-contract freshness and all 15 OpenSpec items. Independent backend and desktop reviews have no remaining supported findings. The backend review reproduced and resolved the mixed GPU-row defect; the desktop review independently reran mounted/headless checks and assessed the strengthened native geometry gate.

Mounted desktop checks cover actual polling, aborts, freshness, recovery, multi-GPU selection, colours, no parent rerenders and headless rendering. Native geometry/screenshots are in `.scratch/lab-workbench/resources-20260930-131501/resource-geometry.json`; all destinations, collapsed Chat, themes and 125/150/200% zoom passed, including a 365px content height. The existing retained-viewers build gate now guards short/scaled footer and destination reachability, including 0%/100% values.

The continuously open built Electron app passed eight live checks and 109 samples in `.scratch/lab-workbench/resources-final-20260930-134457/resource-live.json`. An isolated real 4B CUDA model changed GPU usage from 3% to 16% and back to 3% after unload; RAM changed from 20% to 24% and back. A controlled 2 GiB physical allocation raised RAM to 23%, recovering to 20% after release. Stable readings agreed with contemporaneous NVIDIA/psutil samples. Controlled request failure retained grey percentages, recovery restored colour, and native window hiding stopped polling before visible-window recovery. This used isolated data; saved user records and model files were preserved.

Delivery: [PR #212](https://github.com/Vidcar/thtaib/pull/212) merged as `e6a8a9c`. The established launcher restarted Workbench from that revision. `.scratch/lab-workbench/local-delivery/resources-launch.json` confirms healthy/authenticated services, refreshed timestamps, unauthenticated rejection, the required tool catalogue, the owned backend listener and native artifacts matching the live candidate. The fresh native window loads the repository's built `dist/index.html` and shows both real meters beneath Settings. `.scratch/lab-workbench/local-delivery/resources-comparison.json` reports identical saved-record/configuration and 25 model-file fingerprints (approximately 81 GB). Isolated UAT stopped cleanly without changing model files. Dave authorized discarding the temporary import review during restart. API-055 exactly matches the main contract.
