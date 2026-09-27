# Proposal

## Why

Live tests on the selected Qwen deployment confirmed that changes to the system-prompt project outline can turn a subsecond tool continuation into 42 seconds of repeated prefill. Image processing also takes substantial time, while temporary image removal, repeated stream aggregation and missing prefill measurements make performance harder to explain and improve.

## What Changes

- Freeze the project outline during a run and present it truthfully as an initial snapshot; subsequent tool results carry project changes.
- Reconstruct retained visual context consistently from canonical capture references until upstream context compaction removes it.
- Complete necessary vision checks before the main agent starts building a warm context, with visible check activity and private probe output.
- Validate streamed tool arguments once without repeatedly aggregating the entire response.
- Retain bounded per-call cache, prefill and first-token measurements and expose meaningful timing details in Chat.
- Benchmark supported runtime settings on the actual model and hardware, applying only measured improvements that preserve useful context and model capability.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agents-workflows`: stable initial project context and deterministic retained visual context.
- `models`: admission-time image checks and faithful, efficient stream validation with measured inference timing.
- `backend-desktop`: bounded per-call timing history and truthful prefill/cache details.

## Impact

Existing harness middleware, model adapter, inference telemetry, image capability admission, run projections and Chat measurements. Uses the pinned llama.cpp runtime and upstream Deep Agents/LangGraph integration. No new execution engine or model downloads. Validation uses isolated product data and the existing model weights; saved runtime settings change only after live comparison.
