# Design

## Context

See proposal.md for the measured cause. The existing application.sqlite run payload combines operational fields and captured requests. Browser status currently rehydrates it on every normal agent-control poll on both asynchronous loops; attention and harness publication repeat the same privacy work.

## Goals / Non-Goals

Use the existing store and upstream execution/interaction owners. Preserve diagnostic privacy, Plan/Work permissions and recovery. No new database, scheduler, model loop or cosmetic status override.

## Decisions

- Add separate frozen operational projection models with narrow existing-column/JSON reads for ownership, permissions, lifecycle and attention. Capture-free full routine views exclude model_requests in SQL before parsing; persistence accepts only complete AgentRun objects. Normalized columns remain lifecycle authority.
- Cache both agent and user ownership scoped to current run identity. Resolve one owner per polling iteration, pass it through route/service calls, and offload synchronous database and filesystem work from both loops.
- Exclude model_requests in source model dumps/public state frames and remove diagnostic policy from ordinary interaction observation.
- Keep one shared capture policy, storing a canonical content/policy/detector fingerprint. Check expiry on every policy entry. Reuse unchanged captures, copy only changed captures and avoid whole-run deep copies or duplicate harness normalization. Diagnostic inspection happens outside shared execution locks with ownership/coherency checks before accepting persisted changes.
- Store capture bodies in indexed per-capture rows within the existing application database, with ApplicationStore retaining ownership. Existing run columns and capture-free operational JSON remain the observation source. Migrate legacy capture arrays once without policy work; preserve the complete diagnostic API shape. Commit operational updates, appended captures, linkage and Chat completion atomically. Diagnostic CAS updates only changed capture rows and retries concurrent capture changes.
- Add view=operational to existing list/detail routes and generate canonical contracts. Default diagnostic reads retain current behavior; routine desktop reads select operational.
- Use real-store fixtures with >=50 captures and >=10 MB, actual Browser route/service integration, mounted Chat successive-turn/helper transitions and incremental privacy invalidation coverage.
- Live acceptance records provider, native message, event delivery and rendered times on Dave's real model, while Browser rail and attention polling stay active. Compare backlog and profile both loops.

## Risks / Trade-offs

- A capture-free object could overwrite diagnostics: separate immutable DTOs and persistence type guards, plus update-preservation regressions.
- Fingerprints could skip privacy after in-place edits: recompute canonical content hash, include detector/settings, and test changed bodies/expiry.
- Cache handoff could weaken ownership: bind cache to current run, keep existing execution control authoritative, cover takeover/restart/cancellation.
- Concurrent diagnostic reads could overwrite execution: keep expensive work outside shared locks and persist only coherent diagnostic changes; verify race behavior.
- Removing test data could hide the fault: validate substantial history before cleanup; preserve weights and unrelated files.

## Live validation findings

The first native three-turn workload completed all 30 Browser/filesystem calls and ten Plan investigation calls. Browser/attention profiles contained zero diagnostic redaction, but status p95 was 392 ms. Excluding synthetic-history creation still left status p95 374 ms. Native completion reached 1,813 ms after client stream-consumption completion; this is not an independent provider-completion measurement. The 470-sample profile located remaining contention in execution UPSERTs and capture-array length reads under the shared store lock; Browser and interaction metadata readers waited behind these writes. Each small execution update still parsed/rebuilt the 12 MB diagnostic blob. Separating capture rows in the same database removes this remaining storage coupling; acceptance must be rerun without relaxing thresholds or reducing captured history. The rerun measures provider terminal SSE on an independent network-reader thread, before application consumption, and requires the complete settled assistant answer to survive a paint before proceeding to another turn.

The next two native workloads passed: 60 Work Browser/filesystem calls and 20 Plan investigation calls, with three uninterrupted mounted Work turns in each workload and >=50 captures / >10 MiB retained per run. Unprofiled status/event p95 were 12.61/35 ms; successive-turn event p95 were 35/32/38 ms. The heavier 250 Hz profiling workload also passed at 141.68/92 ms. All 22 provider completions matched their exact Workbench/LLM invocation identities; independent raw SSE completion to native message-finish was at most 1,015 ms, delivery at most 1,077 ms, and full settled-answer paint at most 1,611 ms. Both workloads preserved the visible Browser rail, truthful generation/tool phases and actual reload-equivalent transcripts. In the unprofiled workload, composer phase transitions painted within 1-5 ms of delivery and event delays stayed bounded across each turn. Plan completed its read-only investigations; its renderer timing was not measured.

The new 10,600-sample profile contained 1,166 Browser and 64 attention samples, with zero diagnostic-policy/redaction/hash work in either path. Three samples could not be collected during thread transitions. Retained scratch evidence is under `.scratch/responsive-live`; it contains validation data only and is excluded from Git. Final review also closes capture-free cold archived Interaction registration/state reads and validates schema-3 backup capture-table presence, embedded-history exclusion, JSON and owner/ordinal integrity. Concurrent offloaded Browser marker operations must remain serialized and loss cleanup must act only on the current session.

After the cold-read, backup and Browser-loss race fixes, a third latest-source native workload passed another three uninterrupted Work turns / 30 calls and ten Plan calls. Status/event p95 were 41.09/39 ms, with successive-turn event p95 38/44/37 ms. Totals across successful workloads are 90 Work and 30 Plan calls; all 33 raw-provider completions correlate exactly and the maximum completion/render delays remain within the limits above. Every run retains >=50 captures / >10 MiB. The final Browser regressions use concurrent real staging writes, cancellation during shared loss cleanup, Reset while a stale observer is blocked, and replacement-session identity checks.

Final gates: backend default 1,021 passed / one existing Windows symlink-privilege skip (1,022 collected, 276.84 seconds), integration 206 passed (143.86 seconds), desktop build and mounted multi-turn/helper/status/refresh checks passed, shared contracts fresh, OpenSpec validation and whitespace passed. The earlier isolated Windows snapshot staging-rename failure passed its focused rerun and final full suite without weakening its assertions.

## Migration Plan

Additive response projection and optional fingerprint fields require no new database. Regenerate contracts, run all local gates and real-model acceptance, merge/archive and rebuild the established local application. Existing captures without fingerprints are processed on diagnostic access. Do not sweep all history during startup.
