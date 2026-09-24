# Proposal

## Why

Hugging Face imports currently retain publisher configuration files as generic companions but never apply their chat templates or generation settings. Users can therefore download a model successfully and still run it with unrelated defaults.

## What Changes

- Guide source-only model links to explicitly selected GGUF conversions and verify source lineage before using publisher settings.
- Persist revision-pinned, hash-checked configuration provenance in downloaded bundles.
- Select and validate the runtime chat template, with GGUF embedded metadata winning when it conflicts with a publisher file unless the user chooses the compatible publisher template.
- Apply supported publisher generation settings to actual chat requests while retaining explicit user overrides and reporting unsupported or conflicting fields.
- Show discovered, selected, applied, and unverified configuration in Models and validate two different families through the desktop download-to-chat journey.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: Extend Hugging Face selection, bundle provenance, managed template loading, request setting resolution, and source-visible applied settings.

## Impact

The model manager download, bundle, configuration, deployment, and adapter boundaries; the shared API contract and desktop model import/settings surfaces; Models OpenSpec and associated tests. GGUF remains the executable format.
