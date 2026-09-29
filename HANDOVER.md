# Current handover

Updated 2026-09-29. The largest backend start and estimate functions are split into smaller helpers with the same control flow. Chat, setup resolution, dependency preview, memory placement, input-source rows, and managed reconfigure keep their public behavior. Deep Agents `create_deep_agent` is still how a run is compiled.

Live check on the restarted backend: Chat on ANIMATIONTEST loaded Qwen3.8 27B Unsloth (IQ4_XS) and answered a one-word ping. My models still shows that setup as Ready. No model was downloaded or deleted.

Checks: backend default suite (1232 tests, one optional skip) and integration (213 tests, three optional skips). No desktop, generated-contract, or OpenSpec change, so those checks were not re-run.

Left dense on purpose: admitted tool presentation, and chat dispatch after a request is accepted. Browser tool binding was not part of this pass.

Still open: importing a model file from this computer. The Thinking hover retests reasoning only; the preserve-reasoning probe still runs automatically when that template capability is advertised. Quant names like `Qwen3.5-0.8B.Q4_K_M.gguf` still display as Unknown. Downloads was not rebuilt.
