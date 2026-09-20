# Evidence: guided model setup, runtime controls and planning

**Date:** 2026-09-20 · **Requirements:** MOD-001, MOD-003, AGT-005 (partial coverage) · **Tested commit:** ea3f8557da8c0602ad55c8af2e0751f9ccea05c0 · **Dirty tree:** checks ran during integration; final code captured by that commit, subsequent edits are documentation and CI paths · **Tier:** uat · **Related issue:** #37

## Environment

David-PC, Windows, existing product data preserved. llama.cpp b11045 (2b1847030); installed huggingface-hub 1.32.0, Deep Agents 0.7.15, LangChain 1.4.2 and LangGraph 1.2.11. Disposable CPU checks used Qwen2.5-0.5B-Instruct q4_k_m; the existing managed RTX 3090 deployment used Qwen3.8-27B UD-IQ4_XS for planning. The latter retained its explicit 65,536 context and process across backend restart.

## What ran

| Check | Live / mocked | Result |
| --- | --- | --- |
| Rendered Electron Models: paste repository, discover variants, choose q4_k_m, inspect selected files and startup controls | Live desktop + HF metadata | Nine variants returned; selected download enabled; context blank/model default; startup preview omitted an invented context value. Production download was not clicked. |
| Selected HF download and repeat import into disposable root | Live HF library | Revision `9217f5db79a29953eb74d5343926648285ec7e67`; one weights file (491,400,032 bytes) and README; repeat reused bundle `bundle_72814a388790`, one catalogue entry, matching hashes; upstream resume metadata retained. |
| Managed disposable CPU startup with KV q8_0, batch threads 2, fit off, flash auto, omitted context | Live llama-server | Actual arguments contained selected controls; `/props` and runtime log reported context 32,768. Negative context rejected with HTTP 400 before startup. |
| Project-free Chat explicitly requests planning | Live existing 27B GPU deployment through product harness | Run `agent_bd178c737f57` completed; actual `write_todos` call and result captured, no error. |
| Windows real-model integration tier | Live disposable tiny CPU model | Four checks passed in 13.7 s: plumbing, tools, Chat continuity and request settings. Not a general capability claim. |
| Backend unit suite | Scripted models/fakes | Initial full run: 289/290 passed; one stale default-tool expectation omitted newly exposed `write_todos`. Corrected expectation; targeted projectless permission test passed with its denial assertions retained. |
| Final focused backend checks | Deterministic/fakes plus official middleware | Settings 14, deployments 14, bundles 18, HF selection 8 passed; official planning middleware round-trip passed; relevant runtime and harness checks passed. |
| Desktop build, generated-contract freshness, specification checker | Static/build/mock stream | Passed. Final desktop build includes the imported-bundle handoff and accurate resolved-preview wording. |

Local disposable artifacts are under root `.scratch/hf-reset-live`, `.scratch/runtime-controls-live-rerun`, and `.scratch/reset-planning-result.json` (gitignored). The CPU startup log records actual arguments and `n_ctx_slot=32768`; no secret, model weight or unredacted context is committed. HF weights SHA-256: `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.

## Conclusion

These are narrow integration observations, not verification of the complete requirements. Catalogue statuses remain `built`, with no requirement digest claiming full acceptance. The initial complete local unit run is not described as green; the corrected assertion was rerun, and final-branch CI is recorded on the delivery PR.

No live evidence here establishes vision/projector compatibility, MTP speed or correctness, broad reasoning quality, automatic capability probes, child-agent policy inheritance, long-run continuation, memory write-through, a working visual Builder, context-performance comparisons, voice or MCP execution. Those remain explicitly sequenced in the delivery feature map and DEV-006. Automatic, cancellable tool/image discovery through the existing compatibility service is the next delivery.
