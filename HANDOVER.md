# Current handover

Updated 2026-09-22. The consolidated contract is on main. Current specs are `openspec/specs/`. Active changes are `rewrite-loaded-boundaries` and `consolidate-product-contract`. The old open plan folders `04` through `08`, `compact-workbench-experience`, and `familiar-chat-sidebar` are removed. Their surviving behaviour is in the current specs. Archived changes stay.

Dave then asked for app fixes. A second chat or agent run may start in a folder or workspace another run is already using. The person chooses which run writes. Lab case capture and application backup still refuse to copy while a run is live. Restarting the backend marks a live run that cannot resume as failed or orphaned.

The chat shield and each saved agent choose Ask, Approve for me, or Full access. Ask keeps today's pauses. Approve for me lets an already selected rename or delete proceed. Full access also lets an already selected shell command or external tool proceed. A question still waits, a tool that is off stays off, and memory is not saved by itself. Detailed activity is the button beside the model name. The review card remains when a pause still happens.

The live file-write display is on `codex/chat-tool-stream-display` at `9c9ee9b`, pushed and not merged. It shows the file name and a short tail while a tool argument is still streaming. It does not fully remove the lag. The open-box scroll follow was rebuilt and not measured again. The open reasoning panel can still lag, and that was not changed. Some project chat sends still fail with `read_attachment` missing from the enabled catalogue. That is separate from the folder lock. Do not delete Dave's ScratchArea chats.

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
