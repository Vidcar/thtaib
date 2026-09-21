# Tasks: Complete image, dictation, spoken replies and media handover

Prerequisites: change 07 and `migrate-local-agent-interaction` must be implemented and verified first. Reuse shared SDK content/run presentation where supported, but keep media execution and evidence in the application-owned adapters/services. SDK integration does not implement a media feature or pass a live check. All tasks below remain unchecked until their own implementation and required real endpoint/device evidence is verified. Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [ ] 1.1 Implement manually configured ComfyUI, one concrete STT and one concrete TTS connection contract with tested setup guidance, supported selection discovery/configuration and backend-only credentials.
- [ ] 1.2 Extend retained intake with validated image/audio bytes, metadata, attachment-only turns, actual image-content model dispatch and shared output serving/reuse.
- [ ] 1.3 Implement one versioned working ComfyUI image-generation API template with validated mappings/dependencies and expected output nodes.
- [ ] 1.4 Complete durable correlated media submit/progress/history/retrieval, same-job reconnect/restart recovery, targeted cancellation and truthful partial-output failures.
- [ ] 1.5 Implement trusted Windows microphone permission, device selection/level, format negotiation, verified conversion and real transcription into an editable draft.
- [ ] 1.6 Implement opt-in final-answer TTS, verified audio artifacts and distinct playback/synthesis controls without an application-owned voice-model worker.
- [ ] 1.7 Expose the same awaited media adapters through authorised Chat/child tools and typed Workflow nodes, using shared admission, permissions, events and Lab exclusion.
- [ ] 1.8 Complete real same-run Chat → media → Chat handover with verified two-sided release and restore-only recovery; finish endpoint/preview/output controls in existing views.
- [ ] 1.9 Extend the shared composer, reply previews and Library with compact attachment, dictation, editable transcription, opt-in spoken reply and explicit playback controls without cluttering ordinary text Chat.

## 2. Verify

- [ ] 2.1 Test invalid/oversized/unsupported media, attachment-only inputs, original/derived deletion, secret-free authorised previews and preserved text/document Chat when integrations are disabled.
- [ ] 2.2 Run actual retained-image understanding through a suitable managed vision/projector setup; verify transmitted image content and truthful text-only generation behaviour.
- [ ] 2.3 Run the real ComfyUI template; inspect actual parameters, prompt/event identity, final expected-node history and decoded retained outputs. Test missing dependencies, node errors, cached/preview events and partial retrieval.
- [ ] 2.4 Test disconnect/restart/resume against the same recorded prompt, unknown dispatch outcomes, target-cancel races and refusal of unsafe global interruption/unload on a shared endpoint.
- [ ] 2.5 On Windows, grant only intended microphone access, select a device, observe level, record/cancel/release tracks, and transcribe real microphone/upload audio through the concrete endpoint into an editable draft.
- [ ] 2.6 Generate and play real opt-in spoken replies through the concrete TTS endpoint; verify final-answer-only content, selected voice/settings, saved audio and text survival after synthesis failure.
- [ ] 2.7 Run equivalent real media via agent and Workflow routes, verifying awaited typed artifacts, tools-off/permissions, Lab-owned media tests and attributable cancellation/recovery.
- [ ] 2.8 Run the saved Lab-owned round trip with actual managed Chat unload, actual media generation/retrieval, authorised verified media release, exact Chat restore and same-thread continuation. Retain phase timings/output; test restore failure/cancel/restart without generation replay.
- [ ] 2.9 Render and use the Windows attachment, endpoint, media progress and output-browser controls; exercise open/save/reuse/delete and playback navigation/restart. Mocks or a returned job ID do not satisfy live acceptance.
- [ ] 2.10 Record technical verification separately from Dave's UX acceptance. Exercise the built Windows media journey at full-window and half-screen sizes, with Windows display scaling, keyboard navigation, long progress/output content, one interrupted recovery state and a repeated ordinary text-only Chat journey; leave UX acceptance pending until Dave accepts or explicitly defers review.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
