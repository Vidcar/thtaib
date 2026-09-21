# Complete image, dictation, spoken replies and media handover

## Why

Media must use real configured engines and retained outputs, not endpoint placeholders, while preserving the shared agent/workflow lifecycle and safe local model residency.

## What Changes

Add verified image intake/understanding, one real ComfyUI generation template, concrete STT and TTS endpoint adapters, trusted microphone/playback controls, shared media jobs/artifacts and the required same-run two-sided residency round trip.

## Capabilities

### Modified Capabilities

- `environments-tools`: Complete the creative adapter and add endpoint, image, STT/TTS, media-job and residency contracts.

## Impact

Work order **08 of 08**. Change 07 must be implemented and verified first. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No endpoint-owned weight/voice installation or separate media database, automatic custom-node setup, unsafe shared-server kill/unload, silent cloud recogniser, required voice cloning/duplex or mandatory image-to-image template.
