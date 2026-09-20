# Current handover

Last updated: 2026-09-20.

## Goal and state

Models UX refinement is complete on `codex/models-experience`. Models now leads with the library and model setup, separates imports/presets, and places identifiers, paths and runtime diagnostics in disclosures. Controls offer model-specific choices, custom values and focus/hover help with flags. Related Chat, Knowledge, Lab and task-run copy is clearer.

## Decisions and completed checks

- GGUF metadata drives context choices and GPU layer limits. Keep gguf-py behind the existing inference boundary; its metadata-only reader skips tensor construction for newer tensor formats. Requested launch values remain distinct from observed server properties. CPU suggestions are recommendations, not fabricated observations.
- Stop-before-reconfigure retains edits. Explicit health checks refresh observed server properties.
- Old local UAT records were removed as requested. Current conversation, live model and downloaded weights remain. Future synthetic checks use isolated `.scratch/` product-data roots.
- Full backend suite: 302 tests passed. Desktop typecheck/build and SSE check passed. Shared-contract freshness and spec checker passed. Isolated Windows CUDA tiny-model managed start/props/stop passed with the new UI flags; this proves plumbing, not capability.
- Browser checks: 256k model offers eight 32k–256k choices, invalid oversized custom values are blocked, help is focusable, and the 500px layout has no horizontal overflow.
- Final backend restart passed: all three real models return configuration options, and the existing model remains healthy at 64k context with four concurrent slots. Latest metadata-reader and deployment tests passed after the full suite.

## Pointers and next step

UI: `apps/desktop/src/renderer/{ModelsPanel,DeploymentsPanel,ModelControls}.tsx`. Backend: `inference/configuration_options.py`, `inspect.py`, `deployments.py`. Behaviour: [model spec](specs/modules/models.md). Exact checks: [commands](specs/commands.md).

No implementation work remains. Launch locally with root `Launch Workbench.vbs`; desktop build is refreshed and the backend is healthy. Bonsai setup supports its newer tensor format; full tensor inspection still depends on gguf-py support. Synthetic validation must remain isolated from everyday product data.
