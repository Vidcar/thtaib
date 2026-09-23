# Current handover

Updated 2026-09-23. The Attention count is the same small circle on the bell in both rail widths. Opening a notice selects that chat and clears it; dismiss is also on the notice; deleting a chat clears notices for runs that leave with it. Setup, Changes, Files, Library, and Actions live in one right rail that starts closed. Enter queues while a reply is running, and the queued row can edit, remove, or steer. Steer stops the live step and sends that message on the same thread. The composer Stop control is the only stop. The reasoning control uses its own icon and the accent colour when on. Desktop `pnpm run build` passed. Focused attention and steer tests passed. `openspec validate --all` passed. The live window was reloaded; ScratchArea chats were kept.

The consolidated contract is on main. Current specs are `openspec/specs/`. `rewrite-loaded-boundaries` is merged in pull request 123. The remaining active change is `consolidate-product-contract`. The old open plan folders `04` through `08`, `compact-workbench-experience`, and `familiar-chat-sidebar` are removed. Their surviving behaviour is in the current specs. Archived changes stay.

Opening a chat paints the saved transcript and continues after `interaction_cursor`. It does not play earlier tokens again. A live answer is included in that snapshot. The desktop stream sends that cursor on the first subscribe and again after a disconnect. An approval is shown only after the run is actually waiting for it.

`rewrite-loaded-boundaries` is implemented. Ordinary Chat registers a Deep Agents harness profile that turns off the general-purpose helper and the recursive `delete` tool, including for a compiled child. One budgeted summarizer remains. `rename_file` and single-file `delete_file` stay the only custom file mutations. Chat has a dock beside the transcript: Changes uses Monaco on the stored before/after text, Files uses a virtualized tree and a read-only Monaco view backed by `GET /v1/projects/{id}/file`. Setup is a header popover. The conversation menu stays in the header. A narrow conversation stacks the dock. Tool rows are one checklist and one activity line; `+N -M` comes from the stored texts. Choosing a file line opens the dock and does not send a message. Desktop `pnpm run build` passed, including the local Monaco worker check. Focused backend tests passed for the catalogue, one summarizer, file-read confinement, and line counts. `openspec validate --all` passed.

Dave then asked for app fixes. A second chat or agent run may start in a folder or workspace another run is already using. The person chooses which run writes. Lab case capture and application backup still refuse to copy while a run is live. Restarting the backend marks a live run that cannot resume as failed or orphaned.

The chat shield and each saved agent choose Ask, Approve for me, or Full access. Ask keeps today's pauses. Approve for me lets an already selected rename or delete proceed. Full access also lets an already selected shell command or external tool proceed. A question still waits, a tool that is off stays off, and memory is not saved by itself. Detailed activity is the button beside the model name. The review card remains when a pause still happens.

The live file-write display is included with the approval-mode change. Measured in ScratchArea while `write_file` wrote `stream-bench-tail.html` at about 42 tok/s. The open tool box stayed on the newest lines: about bench-20 to bench-34 at 2.1 KB, the rule being written near bench-92 at 5.3 KB, and bench-126 to bench-141 at 8.2 KB, with the latest 4,000 characters labelled. An earlier look, before the box was pinned to the newest line, stayed on the start of the file at 3.5 KB. The open reasoning panel still fell behind while the model wrote the rules there first: the screen showed about bench-78 to bench-98 after the text had already passed bench-133. A saved tool list that names `read_attachment` no longer blocks a message that has no attachment. Do not delete Dave's ScratchArea chats.

Next implementation is `consolidate-product-contract` task 1, everyday workspace beyond the dock: compact destinations, immediate archive, chat deletion that leaves project files, skill import, document extraction, web search, and connection secrets.

Build order after the dock:

1. Everyday workspace still specified beyond the dock: compact destinations, immediate archive, chat deletion that leaves project files, skill import, document extraction, web search, and connection secrets.
2. Lab: prefill and decode charts, the configurable needle test, the small exact challenges, and the visible machine reservation.
3. Named helpers and confirming a model swap.
4. The Workflows canvas.
5. ComfyUI image generation, dictation, and spoken replies as configured plugs.

Screens are part of the contract, not a later pass. Lab opens on Measurements. Helpers are an empty section until named. Workflows is a palette, canvas, and inspector. Media controls stay hidden until an address is saved.

The dock, Monaco, the file tree, and the one-line activity rows are on main, as specified in `rewrite-loaded-boundaries`. Ordinary Chat still has no general-purpose helper. `+N -M` still comes only from the observed file difference. Half-screen review is still not accepted.

Retained, and not part of this rewrite: Packet 03 is merged. Packet 04 tasks 2.8/2.9 stay open. Deferred and not accepted: document-source inspection, memory-proposal review, the skill journey, the half-screen review, and leftover fixture cleanup. Dave accepted project-file attach/send, the full-screen review, and drop/notifications/tray only. Gemma combined JSON/tool failure remains visible; Qwen can ignore loaded memory without explicit reading.

Preserve weights. Qwen 8080 PID 34364 was running with vision; Gemma is installed and stopped. `.scratch/packet03-followup-runtime.py` inspects and restarts services. Held fixtures: `.scratch/packet04-live-qwen/fixture.json`, Workspace review `project_66e6291b6ef8`. No new trackers or CI. `codex/packet-03-shared-chat` is fully merged; do not continue it.
