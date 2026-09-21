# Complete image, dictation, spoken replies and media handover

## Why

Media must use real configured engines and retained outputs, not endpoint placeholders, while preserving the shared agent/workflow lifecycle and safe local model residency.

## What Changes

Add verified image intake/understanding, one real ComfyUI generation template, concrete STT and TTS endpoint adapters, trusted microphone/playback controls, shared media jobs/artifacts and the required same-run two-sided residency round trip.

## Capabilities

### Modified Capabilities

- `environments-tools`: Complete the creative adapter and add endpoint, image, STT/TTS, media-job and residency contracts.

## Impact

Work order **08 of 08**. Changes 07 and `migrate-local-agent-interaction` must be implemented and verified first. Reuse shared SDK-backed content/run presentation and the existing shared artifact browser, while keeping media intake, engine calls, durable job lifecycle, cancellation, validation, permissions and retained outputs in application-owned media adapters/services. SDK content components do not execute media or establish whole-job success. SDK integration does not satisfy any media feature or real endpoint evidence below. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

Media extends the shared composer, reply previews and Library rather than creating a separate media workspace. Attachment controls handle images/audio; dictation is a compact configured entry point that returns editable unsent transcription; spoken replies are opt-in with explicit synthesis/playback controls. After media is added, ordinary text-only Chat must be rechecked for clutter. UX acceptance is currently pending, not accepted, until Dave accepts the built media journey or explicitly defers review.

## Non-goals

No endpoint-owned weight/voice installation or separate media database, automatic custom-node setup, unsafe shared-server kill/unload, silent cloud recogniser, required voice cloning/duplex or mandatory image-to-image template.
