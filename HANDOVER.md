# Current handover

Updated 2026-09-29. The densest backend paths are split into phase helpers with the same control flow. Admission presentation, helper startup, chat dispatch setup, branch creation, request-default descriptors, setting display, startup normalisation, capture assembly, browser argument checks, and capability probes keep their public behavior. Deep Agents `create_deep_agent` is still how a run is compiled.

Live check on the restarted backend: Chat on ANIMATIONTEST, with Qwen3.8 27B Unsloth (IQ4_XS) already Ready, answered "birch" to a one-word prompt at about 60 tok/s. No model was downloaded or deleted.

Checks: backend default suite (1232 tests, one optional skip) and integration (213 tests, three optional skips). No desktop, generated-contract, or OpenSpec change, so those checks were not re-run.

Left dense on purpose: the helper stream loop inside `invoke`, `resolve_effective_setup`, and the chat acceptance try/except/finally. `ChatPanel` is still the largest desktop function.

Still open: importing a model file from this computer. The Thinking hover retests reasoning only; the preserve-reasoning probe still runs automatically when that template capability is advertised. Quant names like `Qwen3.5-0.8B.Q4_K_M.gguf` still display as Unknown. Downloads was not rebuilt.
