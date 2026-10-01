# Agent-tool audit correction

1 October 2026. Corrects five gaps found when the closed audit was reassessed on main `6e43b44`. The archived audit resolutions stay in force, including their measured model and evaluation limits. This record does not reopen those limits or claim the reassessment scripts were present: the report was checked against the current source, and the reproductions below use the product paths.

| Finding | What was still wrong | Correction |
| --- | --- | --- |
| N01 mutation admission | Async waiters acquired the project lock on the default executor, so enough waiters could stall the holder | Awaitable per-project lease. Async waiters park on the loop. Sync and async hooks set the same admitted-lease marker so `apply_edits` borrows instead of acquiring again |
| N02 tool defaults | The desktop derived an old Standard list, so one checkbox could save destructive and host tools | `GET /v1/agent-tools` is the catalogue projection. The editor materialises a list only from that payload for the applicable context |
| N03 evidence researcher | The project-optional template pinned project discovery, so a projectless run was rejected before the model | Project reads stay in the template for a bound project and are not pinned. Projectless admission omits unpinned project-file tools. Trusted search and page tools are added only for an already selected built-in public-web connection, and not when tools are off |
| N04 retained results | Stock templates never selected `read_tool_result`, while notices always named it | New templates that consume retained evidence select it. Notices name an accepted reader, the line-oriented fallback, or the limitation. Saved setups are not rewritten |
| N05 resource-only MCP | An empty tool list was treated as unready | Readiness follows capabilities recorded by a successful test. Empty tool manifests, unsupported resources, failed tests, revocation and version changes stay distinct |

Explicitly selected shell and preview tools still remain selected without a project, so using them pauses for a project. That pause was dropped by the first projectless omission and restored after `test_projectless_selected_shell_pauses_only_when_used` failed.

Independent review of the diff found no delivery blocker. It noted that the synchronous tool hook did not mark the lease admitted, so a sync `apply_edits` could wait on itself. The shipped graph uses the async hook. The sync hook now sets the same marker, and the existing subprocess watchdog covers that call. The review's remaining notes are limits, not open defects: cancellation after a waiter is already marked admitted is not a separate test; a resource probe whose error text merely contains "method not found" is classified as unsupported resources; browser and Windows template runs that are rejected for a missing worker or grant prove the reader through the compiled tool directly rather than a full admitted graph.

Live Electron was not refreshed. A Workbench window was already open, debug port 9222 was closed, and the healthy backend on port 8000 was still the process started before this correction. The conversation list was empty and no run was active. The window was left as it was. The Agents editor was exercised by the desktop production-editor check inside `pnpm run build`, not by that open window.

Acceptance passed: `.scratch/verification/20261001T084852Z-a962e818` (1,424 default tests, 1 skip; 222 integration tests, 3 skips; desktop build; contract check; OpenSpec). The pinned real-model launcher is a Linux CPU build, so it does not start on this PC by itself. Pointing it at the installed Windows `llama-server.exe` for release b11045 and the cached tiny GGUF passed 4 smoke tests in an isolated data root. That smoke proves the tool round-trip, not model quality.

Saved agents, grants, weights and the active `consolidate-product-contract` change were not rewritten.
