# Current handover

Updated 2026-09-22. The consolidated contract is on main. Current specs are `openspec/specs/`. Active changes are `rewrite-loaded-boundaries` and `consolidate-product-contract`. The old open plan folders `04` through `08`, `compact-workbench-experience`, and `familiar-chat-sidebar` are removed. Their surviving behaviour is in the current specs. Archived changes stay.

Dave then asked for two app fixes. A second chat or agent run may start in a folder or workspace another run is already using. The person chooses which run writes. Lab case capture and application backup still refuse to copy while a run is live. Restarting the backend marks a live run that cannot resume as failed or orphaned.

The live file-write display is on `codex/chat-tool-stream-display`, pushed and not merged. Measured in ScratchArea while `write_file` wrote `stream-bench-tail.html` at about 42 tok/s. The open tool box stayed on the newest lines: about bench-20 to bench-34 at 2.1 KB, the rule being written near bench-92 at 5.3 KB, and bench-126 to bench-141 at 8.2 KB, with the latest 4,000 characters labelled. An earlier look, before the box was pinned to the newest line, stayed on the start of the file at 3.5 KB. The open reasoning panel still fell behind while the model wrote the rules there first: the screen showed about bench-78 to bench-98 after the text had already passed bench-133. Some saved project chats still fail to send because their tool list includes `read_attachment` and the message has no attachment. A new ScratchArea chat sent. Do not delete Dave's ScratchArea chats.

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
