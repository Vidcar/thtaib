# Current handover

Updated 2026-09-24. Review of the supplied `results.json` and probe scripts is complete. Their copied methods matched the then-current commit, but their doubles did not prove full application behavior. Three failure paths were reproduced with actual backend services and repaired in merged [PR #145](https://github.com/Vidcar/thtaib/pull/145): a terminal save retry could orphan another live worker; a classified interaction failure could leave live Chat and its queue uninformed; and a failed subscriber/telemetry flush could discard buffered message and tool events. Current OpenSpec recovery scenarios were updated.

Validation on Windows: backend default 728 passed (one existing symlink-privilege skip), integration 186 passed, shared-contract freshness passed, and strict OpenSpec validation passed (13 items). The new regressions use a real held agent worker, SQLite write failures, and loopback SSE with an already-connected subscriber. Responses were scripted; this does not measure failure frequency with a local model.

The established backend was restarted from merged `main` on port 8000 after confirming no active runs or imports. It is healthy; the saved managed Qwen3.8 27B deployment reports running and healthy. Ordinary product data and model weights were retained. No desktop code changed.

An unsaved General run outcome remains uncertain if the process exits before its in-process terminal retry. Restart recovery reports it as orphaned rather than claiming completion. No delivery work remains.
