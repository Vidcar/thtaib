# Current handover

Updated 2026-09-29. **Add models Review keeps a fresh import on llama.cpp's own defaults until a loading control is set.** This follows the archived Models native-defaults delivery (`d6c99f2`, PR 192) and is the current Models behavior on `D:\CodeProjects\thtaib`.

Find still accepts a Hugging Face link. Choose is quantization, an explicit projector or text-only choice, and the publisher generation recipe. Review is where context, GPU layers, K cache, V cache, cache location, flash attention, and MTP are set, beside the memory estimate. Untouched values stay omitted from the saved setup and the llama.cpp command. Host and port are still sent. An already-saved profile that stored those keys is left as saved. The estimate stays advisory and does not block Download.

MTP appears only when a real draft head exists: a main-file tensor ending in `nextn.eh_proj.weight`, or a separate file whose own header contains a NextN tensor. Filename alone is not enough. MTP off skips those tensors in the GPU estimate. MTP on prices the head. Turning context to Automatic on an already-matching launch records that request without restarting the process.

Capability checks are one icon row on Review and on the installed model. Detail and Retest sit in the hover. Before download, the row uses the file and header only. The first healthy load runs the existing probes once, and only for advertised kinds.

Checks passed: desktop `pnpm run build`, backend default suite (1232 tests, one optional skip), integration (213 tests, three optional skips), generated-contract `--check`, and `openspec validate --all` (12 passed). Read-only Review of `prithivMLmods/Qwen3.5-0.8B-MTP-GGUF` (`Qwen3.5-0.8B.Q4_K_M.gguf`, text only) offered Built-in draft head, priced speculation only after MTP was on (weights 494.3 MB to 506.3 MB, speculation 512.0 MB), and a context slider at 43,008 tokens changed only the context pool while K cache, V cache, cache location, and MTP stayed Engine default or Off. No download was started and the installed Qwen was not loaded. The open Review was put back to Engine default and MTP Off.

Still open: importing a model file from this computer. The Thinking hover retests reasoning only; the preserve-reasoning probe still runs automatically when that template capability is advertised. Quant names like `Qwen3.5-0.8B.Q4_K_M.gguf` still display as Unknown. Downloads was not rebuilt.
