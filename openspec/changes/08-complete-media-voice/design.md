# Design: Complete image, dictation, spoken replies and media handover

## Technical Approach

After successful implementation and verification of `migrate-local-agent-interaction` and change 07, reuse shared SDK-backed content/run presentation where supported and the existing shared output browser. The shared SDK presents content and scoped activity; it does not execute media. Extend existing connection, creative-job, artifact and Chat/Workflow services. Users manually provision compatible ComfyUI, speech-to-text and text-to-speech endpoints; thtaib owns connection settings, supported selections, requests, jobs and retained outputs, not their model/voice files. Choose and document one concrete tested protocol/implementation for STT and one for TTS during implementation, including setup, supported settings and failure/cancellation behaviour. A generic URL field does not complete either integration. Do not route these settings through GGUF inspection or llama-server flags.

Use a versioned ComfyUI API-format prompt template with explicit parameter-to-node/input mappings and expected final output nodes. Verify actual server node/model schemas and error/event/queue/history contracts. Keep ComfyUI's internal graph inside ComfyUI rather than turning its sampler nodes into thtaib workflow steps. Persist submit intent and returned prompt ID, subscribe/correlate events, and retrieve/validate final bytes through the existing artifact owner. Node outputs/previews and queue acknowledgement are not whole-job success. Reconcile the same job after disconnect/restart; no blind resubmission.

Image understanding sends authorised actual image blocks through the shared local adapter and compatible projector route. Image generation can still be called by a text-only model; do not imply it can see the result. Input validation/decoding, derived documents/media and artifact serving share existing security, retention and lineage.

Microphone access belongs to the trusted Electron application document/frame and explicit audio permission. Negotiate recording format; verify any converter needed by the chosen transcription endpoint. Dictation produces an editable draft. Opt-in spoken replies synthesise only the final user-visible text through the distinct TTS adapter, with synthesis and playback separately controlled.

## Recovery and residency

Await the same media adapter from agent tools, children and direct Workflow nodes. Reuse exact invocation identity, policy, Lab exclusion and admission. Connected-server cancellation must be targeted unless exclusive management is actually verified; neither one job nor an empty queue grants global interruption/unload authority.

Complete change 06's real two-sided handover with a suitable explicitly authorised local setup: quiesce/unload Chat, run actual media, retain verified output, verify necessary media release, restore the exact frozen Chat configuration and continue the same run/thread. Preserve outputs across failures and retry restoration only, never generation. A shared endpoint lacking safe exclusive release remains usable for ordinary compatible jobs but cannot satisfy the handover test.

Use the existing Windows UI and output browser. Leave image-to-image, voice cloning and real-time duplex optional. Missing required live engines/device/handover evidence blocks this change's affected acceptance checks, not earlier completed changes.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
