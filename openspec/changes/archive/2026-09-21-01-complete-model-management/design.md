# Design: Complete model installation, profiles and deployment lifecycle

## Technical Approach

Extend `inference/` services and the existing Models/Deployments panels. Reuse `ModelBundle`, `RunProfile`, `Deployment`, `RuntimeManifest`, `SettingsBags`, the Hugging Face fetcher and managed process supervisor; resolve current paths from those owners. The adapter remains an inference consumer, not a lifecycle owner.

Resolve repository metadata and an immutable revision before calling `snapshot_download` for the exact selection. Escape wildcard metacharacters in literal filenames and preserve relative paths. Keep metadata/cache, staging and installed copies distinct. Never launch a second download path through llama-server `-hf`. Projector completeness does not establish projector compatibility.

Make imports durable jobs with an owned worker and explicit stop/reconcile behaviour. Do not assume the Hub downloader has a cancellation argument or per-file byte callback. Measured file/stage progress is sufficient when byte telemetry is unavailable. Repair reuses the recorded revision; it is not an update operation.

Resolve profile identity and bundle binding at the backend. Freeze all launch inputs; show later edits as pending differences. Map controls against the installed llama.cpp build rather than copying historic flags. Request changes do not restart a server. Initially block disruptive changes while dependencies are active; change 06 adds authorised suspension and handover.

## Failure and data handling

Recheck ownership, active use, shared references and process identity at the destructive boundary. Preserve real weights, imported originals and historical configuration. Use the existing application database for new job records; preserve current authoritative record families until their supported migration is complete.

## Delivery boundary

This change proves installation and real text generation. Change 02 proves adapter capabilities. Diffusion/voice endpoints and their files are outside managed GGUF installation.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [Hugging Face downloads](https://huggingface.co/docs/huggingface_hub/guides/download)
- [llama-server contract](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
