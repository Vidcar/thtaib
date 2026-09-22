# Current handover

Last updated: 2026-09-22. Active overhaul on `codex/compact-workbench`, based on unmerged Packet03. Dave authorized every-surface compact UX, chat archive/delete, model cache/settings/probes, actual reasoning/tool activity and adjacent fixes. Contract: `openspec/changes/compact-workbench-experience`.

Implemented compact dark/light themes, Lucide icons/no disclosure arrows, shared accessible hover help, persistent resizing, chat icon actions/delete dialog, immediate archive and draft preservation. Deletion clears owned history/checkpoints/interaction projections/caches/grants while preserving project files and shared records; stale callbacks cannot resurrect deleted chats. Reasoning precedes answers; tool rows show actual names, arguments/results/errors. Model inspection survives manager restart; template-derived thinking and tensor-derived MTP controls/probes/applied settings are visible. Fixed runtime thinking-off transmission, inherited invalid effort, and reload bypass of weight integrity.

Checks: first full backend default507/integration150 and desktop build passed; final suites running after review fixes. Strict OpenSpec16/16 passed. Live Qwen tools/thinking probes passed; patched toggle off produced zero reasoning vs70 characters on. Cache repeated/fresh-manager reads15ms/<1ms vs16.7s first read. Native dark screens inspected across all destinations; light Chat/Settings and nav drag/collapse/reset passed. Inspector currently covers composer: final layout fix underway.

Next: finish final checks, restart exact backend safely, native live Chat/archive/delete/model settings, narrow panels, final review/commit and stacked PR onto `codex/packet-03-shared-chat`; rebuild locally. All shell through RTK; fixtures only `.scratch/`; preserve weights.

Packet03 PR118 remains draft19/25, with Explorer drag/tray/notification activation and Dave final visual acceptance unresolved. Preserve pending Tea/Coffee chat `chat_6d5ab59844b9`, run `agent_be73f5983362`. Backend8000 PID18588, model8080 PID4644; recovery audit supports exact backend stop/restart, not graceful shutdown (cancels question). Do not claim Packet03 acceptance.
