# Evidence: Windows host-shell approve, deny and no-project refuse on David-PC (uat tier)

**Date:** 2026-09-19 · **Requirements:** ENV-001, ENV-002, ARCH-005, AGT-001 (partial clauses; see Conclusion) · **Tested commit:** `8887f9f86fab29db3bdf57e3b4c81e47ba3a2dcd` (`origin/main` after PR #89; worktree of that tip) · **Dirty tree:** no on the UAT worktree; David's checkout was left detached at `5728b94`, clean and unused · **Tier:** uat · **Related:** PR #89 (implementation); this report is recorded after the run.

## Provenance and limits

Performed by a Cursor agent on David's Windows PC through the product's own backend HTTP API with the desktop shared-secret token (token not reproduced). No Electron clicks. No CI job — do not invent a run URL. Raw traces stayed on that machine under `.scratch/logs/host-shell-uat-2026-09-19/` (`api-trace.jsonl`, no token) and are not committed.

This is `uat`-tier evidence for the clauses it covers. It does **not** cover every acceptance line, so catalogue rows stay **`built`**. The durable Approvals inbox remains [OQ-011](../open-questions.md#oq-011). Digest is left `null`.

## Environment

David-PC (same machine as the 2026-09-19 managed-inference UAT): Windows, NVIDIA GeForce RTX 3090 24 GB, CUDA 13.4 UMD; managed llama.cpp `b11045` CUDA (`b11045-2b1847030`). Preferred capability UAT model bundle `bundle_ee208ec8f733` (Qwen3.8-27B UD-IQ4_XS). Profile `profile_b5fa6de51705` (3090 defaults, listen 8091, `tools_enabled`). Data root `%LOCALAPPDATA%\LocalAIWorkbench\`. Product backend `uv run python -m workbench_backend --port 8002` from a `.scratch/uat/host-shell-main` worktree of `8887f9f`. Project `.scratch/uat/host-shell-2026-09-19/project`. Ports 8002 / 8091 so a later desktop default bind would not collide.

## What ran

| Step or command | Working directory | Live / mocked / recorded | Result |
| --- | --- | --- | --- |
| `GET /health`; `GET /v1/runtime` without token | HTTP client | live | 200; **401** |
| `POST /v1/runtime/pin {}` | HTTP client | live | 200 in 481 ms; already-ready b11045 CUDA 13.4; skip-download (no re-fetch) |
| `GET /v1/bundles/bundle_ee208ec8f733` | HTTP client | live | `complete`, `disk_matches: true` |
| Managed deploy `deploy_7baf2f55c46e`; smoke | HTTP client | live | create returned `running`; health 200; `llama-server` PID 25476; smoke 200; VRAM 1156 → 19075 MiB |
| Case 1 — project + Approve. Conversation `chat_d277bfe692a6`, run `agent_4c0e59eac076`. `presented_tools: ["execute"]`. Task caused `execute` `echo shell-uat-ok> uat-shell.txt` | HTTP client | live model, live host shell | Interrupt captured (`pending_interrupt`; file still absent). `POST …/interrupt-decision` `{"decisions":[{"type":"approve"}]}` → 200. Tool succeeded. Run `completed`. **On disk:** `uat-shell.txt` = `shell-uat-ok`. `host_shell.available=true`, `environment=windows_host_shell`, `isolation=none`, cwd = the UAT project (ENV-001 command + result; ENV-002 / ARCH-005 approve path; AGT-001 harness owns the loop) |
| Case 2 — project + Deny. Conversation `chat_b0137ed917c5`, run `agent_8e777542bc44`. Command `echo shell-uat-denied> uat-shell-denied.txt` | HTTP client | live model, live host shell | Interrupt captured. `POST …/interrupt-decision` `{"decisions":[{"type":"reject"}]}` → 200. Run recorded the rejection and `completed`. **`uat-shell-denied.txt` absent.** Project still contains only `uat-shell.txt` (ENV-002 / ARCH-005 deny path) |
| Case 3 — no project. Conversation `chat_5cb53b412de0` | HTTP client | live | Create: `shell_tools_available=false`. `POST …/start` with `presented_tools=["execute"]` → **400** `shell_requires_project`. Visibility-only run `agent_22fc2f8afe96` completed (`echo`, `time_now`; `host_shell.available=false`, `cwd=null`) (AGT-001 project-less half for the shell; ENV-001 no invented home cwd) |
| `POST /v1/deployments/deploy_7baf2f55c46e/stop` | HTTP client | live | 200 in 1.1 s, `stopped`; VRAM back to 1156 MiB; UAT backend on 8002 stopped. Cursor and David's checkout untouched |

## Covered clauses (not whole acceptance lines)

| ID | Covered on this run | Still uncovered |
| --- | --- | --- |
| ENV-001 | Real host `execute` in the bound project; approve produced the working file; API-reported cwd / `windows_host_shell` / `isolation=none` matched that project, not conversation-state files; no home-directory cwd | Filesystem-tool edit on this commit; Electron-displayed paths; browser/graphical workers |
| ENV-002 | Same Chat HTTP path: approve ran, deny did not; decision recorded on the run | Agent-run HTTP live; workflow adapters, interpreter, interactive panels; durable inbox ([OQ-011](../open-questions.md#oq-011)); Electron Approve/Deny |
| ARCH-005 | Agent-tool `execute` through Chat; interrupt_on enforced approve/deny (not prompt-only) | Workflow adapter; other invocation-path comparison; parent/child run attribution |
| AGT-001 | Chat → Deep Agents harness → real `execute` (tool_call, interrupt, resume); no-project run with shell/filesystem tools absent and reported; explicit `execute` is `shell_requires_project` | Filesystem file-edit on this commit (earlier UAT at `5728b94`); Electron Chat |

Related live observations not attached as catalogue rows: AGT-005 / API-004 (catalogue still lists `execute`; Chat `interrupt-decision` worked). Outbound `available_tools` still named the full nine-tool catalogue while `presented_tools` was `["execute"]`; the model used `execute`. Middleware is the fail-closed gate; this run did not try to bypass with `write_file`.

## Conclusion

Executable checks at the HTTP boundary on the target Windows GPU path: a dangerous host-shell command paused; approve wrote one project file; deny wrote none; Chat without a project refused `execute` and did not invent a home cwd. Requirement statuses stay **`built`**. No row is `verified`. No `requirement_sha256` is recorded.

**Not covered:** Electron Approve/Deny; cancel-while-interrupted on this machine; Lab live rerun with `execute`; WSL/Docker; durable Approvals inbox (OQ-011); `%` auto-allow leftover; OpenAPI for the new POSTs.
