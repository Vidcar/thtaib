# Current handover

Updated 2026-09-29. A second structural split follows the merged dense-path pass (PR #196). Chat panel actions, the helper stream event body, model-selection facts, native memory checks, bundle configuration options, chat readiness and admission, effective setup, and backup linkage checks are phase helpers. Public behavior is unchanged. Deep Agents `create_deep_agent` is still how a run is compiled.

Live check on the restarted backend and rebuilt desktop: switched from SandPhysics to ANIMATIONTEST, then Qwen3.8 27B Unsloth (IQ4_XS), already Ready, answered "cedar" at about 61 tok/s. No model was downloaded or deleted.

Checks: backend default suite (1232 tests, one optional skip), integration (213 tests, three optional skips), and desktop `pnpm run build`.

Left dense on purpose: the helper `invoke` try/except/finally, the chat acceptance try/except/finally, and `ChatPanel` hooks plus composer wiring. Chat actions live in sibling modules beside `ChatPanel.tsx`.

Next dense units, if another pass is wanted: `hf_fetch.download`, `import_jobs.storage_summary`, harness admission freeze and compose, `interaction.observe`, and the remaining chat `create` path.

Still open: importing a model file from this computer. The Thinking hover retests reasoning only; the preserve-reasoning probe still runs automatically when that template capability is advertised. Quant names like `Qwen3.5-0.8B.Q4_K_M.gguf` still display as Unknown. Downloads was not rebuilt.
