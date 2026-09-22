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

## UX presentation

Follow the shared UX contract in `../03-complete-shared-chat/design.md#shared-ux-contract` for composer controls, activity, approvals, Library retention, output reuse and attention. Media features extend the existing composer, reply previews and Library: image/audio attachment controls live beside the composer, dictation is a compact configured entry point, transcription appears as an editable unsent draft, spoken replies are opt-in, and playback has explicit play/stop/navigation controls. Endpoint/template/voice settings use focused popovers or Settings surfaces rather than permanent raw configuration panels.

Media progress, previews, output lineage, reuse/delete actions and recovery states must be understandable without raw JSON, engine IDs or backend terminology. Technical template mappings, prompt IDs, event streams, endpoint capability records, conversion details and retrieval evidence remain available in expandable details. Text-only Chat remains a first-class path with media disabled or unused, and implementation must recheck ordinary text Chat for clutter after adding media controls.

Technical verification and Dave's UX acceptance are separate completion records. Media UX acceptance is currently pending, not accepted. It covers the built Windows journey at full-window and half-screen sizes, Windows display scaling, keyboard navigation, long media/progress/output content, interrupted media recovery, and one text-only Chat journey after media controls are present. UX acceptance remains pending until Dave accepts the built journey or explicitly defers it.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
## Dependency refinement — 2026-09-22

Dave explicitly advanced retained image upload, compact clickable previews and viewing screenshot/tool image outputs into the active shared Chat/Packet 04 delivery. Reuse its retained originals, multimodal content, viewer, source access checks and verified capability evidence here. This does not complete the remaining media/audio/voice work. Do not add a second image store, viewer or image transport.

Retained image originals, actual multimodal Chat input, scoped image viewing and source references are now implemented and verified with actual Gemma/Qwen image inputs. Packet 04's present connection kinds are MCP and public web; media endpoints require the explicit future catalogue extension rather than being implied by those tools. Image generation/editing, durable media jobs, audio/voice and their required Windows journeys remain Packet 08 work; its tasks stay unchecked.
