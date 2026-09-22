# Current handover

Updated 2026-09-22. The consolidated contract is on main. Current specs are `openspec/specs/`. Active changes are `rewrite-loaded-boundaries` and `consolidate-product-contract`. The old open plan folders `04` through `08`, `compact-workbench-experience`, and `familiar-chat-sidebar` are removed. Their surviving behaviour is in the current specs. Archived changes stay. Leave the app code alone until Dave asks to build.

Build order when implementation starts:

1. Everyday workspace still specified beyond the dock: compact destinations, immediate archive, chat deletion that leaves project files, skill import, document extraction, web search, and connection secrets.
2. Lab: prefill and decode charts, the configurable needle test, the small exact challenges, and the visible machine reservation.
3. Named helpers and confirming a model swap.
4. The Workflows canvas.
5. ComfyUI image generation, dictation, and spoken replies as configured plugs.

Screens are part of the contract, not a later pass. Lab opens on Measurements. Helpers are an empty section until named. Workflows is a palette, canvas, and inspector. Media controls stay hidden until an address is saved.

The dock, Monaco, the file tree, and the one-line activity rows remain as specified in `rewrite-loaded-boundaries`. Ordinary Chat still has no general-purpose helper. `+N -M` still comes only from the observed file difference.

Retained, and not part of this rewrite: Packet 03 is merged. Packet 04 tasks 2.8/2.9 stay open. Deferred and not accepted: document-source inspection, memory-proposal review, the skill journey, the half-screen review, and leftover fixture cleanup. Dave accepted project-file attach/send, the full-screen review, and drop/notifications/tray only. Gemma combined JSON/tool failure remains visible; Qwen can ignore loaded memory without explicit reading.

Preserve weights. Qwen 8080 PID 34364 was running with vision; Gemma is installed and stopped. `.scratch/packet03-followup-runtime.py` inspects and restarts services. Held fixtures: `.scratch/packet04-live-qwen/fixture.json`, Workspace review `project_66e6291b6ef8`. No new trackers or CI. `codex/packet-03-shared-chat` is fully merged; do not continue it.
