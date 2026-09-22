# Current handover

Last updated: 2026-09-22. Active goal: finish Packet03, then implement Packet04 in full (Dave confirmed this order). Branch `codex/packet-03-shared-chat`, [draft PR118](https://github.com/Vidcar/thtaib/pull/118). Compact overhaul PR119 is merged into this branch; its change remains9/9 verified.

Packet03 follow-up repaired Explorer drops doing nothing on ordinary Chat, stale multi-file uploads after navigation, saved-attachment hydration losing earlier selections, independent completion notifications, correct Chat/Workflows notification navigation, sticky notification selection and draft loss during activation. Regeneration no longer clones the source answer's future pending checkpoint writes; ancestor history remains intact. Failures were reproduced before fixes. Details: `openspec/changes/03-complete-shared-chat/design.md`.

Checks passed: backend510 default/153 integration; final desktop build; generated contracts; strict OpenSpec16/16; diff. Real Qwen regeneration had3 durable messages during generation,4 afterward, no duplicated answers, zero tools and unchanged source history. Native review fixture: `Regeneration fix verified`, chat_090b89ebfeb9. Source fixture deleted through the product API. Compact-overhaul live evidence remains in its OpenSpec design; MTP speedup is unbenchmarked.

Backend8000 PID31812 and rebuilt desktop PID33332 run current fixes. Qwen8080 PID4644 preserved. Everyday root: `%LOCALAPPDATA%\LocalAIWorkbench`. Pending question chat_6d5ab59844b9/run agent_be73f5983362 survived restart; explicit Quit cancels it. Preserve weights; Dave allows disposable chats/user data.

Packet03 remains19/25 until actual Windows gates and final visual acceptance close. Dave reported drag failure; root rebuilt/restarted and asked him to retry a text-file drop and tray reopening. Notification activation still needs an actual shell click; native controller cannot operate these shell/cross-window surfaces. Next: collect those results, demonstrate notification activation, finish cleanup/delivery, then Packet04. Packet04 has read-only ownership assessment only. All shell through RTK.
