# Current handover

Updated 2026-09-22. Goal: finish Packet 03, then implement Packet 04 in full. Branch `codex/packet-03-shared-chat`; [draft PR 118](https://github.com/Vidcar/thtaib/pull/118). PR 119 compact overhaul is included, its change 9/9 verified.

Dave accepted Explorer drop and notification activation. Tray reopening confirmation is still pending; the native controller cannot click the shell tray. Requested compact model/tools/usage controls, hover/focus details, actual counts/live speed and adjacent cleanup are implemented. Packet 03 remains 22/25: 1.8/2.8 await tray, 3.2 retains final UX acceptance separately. Packet 04 is unimplemented; start from its existing OpenSpec artifacts after 03 closes.

Verified: backend 522 default/155 integration, complete desktop build/regressions, generated contracts, strict OpenSpec 16/16 and diff checks. Native dark/light 1269/794px at 200% scaling: compact menus, keyboard/outside dismissal, Models/Library/recovery and repaired narrow navigation. Live Qwen UI showed 3431 input + 1464 output = 4895 tokens and 41.2 tok/s, matching saved/native timings. Updates use the existing stream at 4 Hz; transient replay is bounded with real-gap recovery. Fixed built-in tool Command projection, async cleanup, stale Live phase and duplicate progress. Full evidence in 03/design.md.

Backend PID 34740 and desktop PID 23480 run current code. Qwen 8080 PID 4644 retained. Data root `%LOCALAPPDATA%\LocalAIWorkbench`; preserve weights. Review chat: Live context and speed, chat_07dbc960dadf. `.scratch/packet03-followup-runtime.py` verifies identity before restarts; `.scratch/packet03-usage-review.py inspect-current` reads measurements without exposing authentication. System theme restored. Obsolete pending notification fixture cancelled/deleted; other chats retained.

Next: retain the requested tray/final acceptance gates honestly, then complete/merge/archive 03 and proceed to 04. All code is validated and the local app is ready for review; PR 118 retains the remaining gates. Shell commands through RTK. No CI re-enablement or memory writes.
