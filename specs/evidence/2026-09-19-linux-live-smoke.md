# Evidence: manual live smoke of backend trust, Chat → tool → file, thread continuity and applied settings (Linux, tiny model)

**Date:** 2026-09-19 · **Requirements:** API-003, AGT-001, STATE-001, STATE-002, MOD-005, ARCH-003 · **Tested commit:** `d8973bbc19e1909f9c3a5e894beb03aa5264badc` (main at the time; `b9c89d8` was one merge ahead and not checked out) · **Dirty tree:** no · **Tier:** manual · **Related:** read-only technical assessment of 2026-09-19 (Project record); recorded into the repository by the pack-slimming change.

## Provenance and limits

This report transcribes the live section of an independent read-only technical assessment performed by a Cursor cloud agent. Raw logs and HTTP captures were kept in `/tmp` on that VM and were not retained; the assessment document is the only record. It is a **manual** tier run on Linux with a 0.5B model: it proves that the plumbing works end to end against a real `llama-server`, and nothing about model capability, Windows, CUDA or managed start. It does not make any requirement `verified`.

## Environment

Ubuntu cloud VM, 4 vCPU, no GPU; Python 3.12.3, uv 0.12.17; llama.cpp release **b11045** (`llama-b11045-bin-ubuntu-x64`, reports `version: 0.4.1-dev (build 11045)`), CPU; model `Qwen/Qwen2.5-0.5B-Instruct-GGUF` `q4_k_m`; `llama-server --jinja -c 4096 --alias qwen-smoke`; backend started with `uv run python -m workbench_backend` after `uv sync --frozen`; project folder `/tmp/uatproj`; product data root `~/.local/share/LocalAIWorkbench/`.

## What ran

| Step | Live / mocked | Result |
| --- | --- | --- |
| `GET /health` | live | 200 |
| `GET /v1/bundles` without header; with wrong header; with correct header | live | 401; 403; 200 `[]` (API-003) |
| `POST /v1/deployments/connected` pointing at the running llama-server; health probe | live | attached with `scope=connected`; healthy |
| `POST /v1/chat/conversations` (project `/tmp/uatproj`); `…/start` with "create hello.txt" | live model, live filesystem tools | run `completed` in ~6 s; model emitted `write_file`; `/tmp/uatproj/hello.txt` = "hello from qwen"; captured request body carried 8 tools and the full system prompt; 6 checkpoint ids linked; `thread_id` recorded (AGT-001, STATE-002) |
| Second turn on the same conversation: "reply with the file name you created" | live | same `thread_id`; outbound request contained 6 messages including the earlier `assistant(tool_calls)` and `tool` result; answer "hello.txt" (STATE-001 continuity at the wire) |
| Profile `{temperature: 0.1, top_k: 20, min_p: 0.05, max_tokens: 64, bogus_setting: 1}` bound; third turn | live | wire body carried `temperature`, `top_k`, `min_p`, `max_completion_tokens`; `bogus_setting` reported in `unsupported.per_request`; `ctx_size` and `flash_attn` listed as startup mismatches (loaded startup null on a connected deployment); answer "PONG" (MOD-005, ARCH-003 applied settings) |
| `llama-server --mlock`, `--no-mmap` with b11045 | live binary | `error: invalid argument` for both; `--load-mode mlock` accepted; bare `--flash-attn` rejected (recorded as [DEV-002](../deviations.md#dev-002)) |
| `POST /v1/runtime/pin` on Linux | live | HTTP 200 with `status: failed`, "NVIDIA GPU was not detected" (honest Windows-only path) |

Also run on the same tree, not live evidence: 181 backend unit tests passed in 24 s (all model calls scripted or against the fake server); desktop type-check and build passed; shared-contract freshness passed; spec checker passed (28 documents, 50 requirements, 0 verified).

## Conclusion

Seen working live, plumbing only: backend token trust (401/403/200), Chat → Deep Agents harness → real tool call → file in the project, follow-up turn resuming the same LangGraph thread with prior tool messages on the wire, and a saved profile's per-request settings reaching the model with unsupported keys and startup mismatches reported. All results are executable observations at the HTTP boundary, not model judgements. Not covered: managed CUDA start on Windows, GPU detection, Hugging Face import, Lab capture/restore, knowledge store, Electron pairing, any capability claim. Requirements stay `built`; the first `verified` rows need the CI smoke tier or David-PC UAT.
