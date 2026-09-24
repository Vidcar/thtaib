# Proposal

## Why

The Models page buries important configuration behind disclosures, mixes downloads with the model library, and makes GGUF variants hard to compare. Discarded downloads remain in history, including three existing records in the everyday workspace.

## What Changes

- Organize Models into My models, Add models, and Downloads tabs with continuous progress updates.
- Present GGUF variants in a compact, accessible table with filename-derived quantization hints, exact sizes and file completeness; separate obvious MTP auxiliary files from primary weights.
- Expose common startup, response and thinking controls together on the selected model, while retaining resolved-value provenance and safe save/reload behavior.
- Clear terminal download records after safe discard, including already-discarded records, without removing shared or installed model files.
- Move storage management into Downloads and improve narrow-window and long-name layouts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: Model discovery, configuration visibility, download progress and terminal-job cleanup behavior.

## Impact

The desktop Models components and styling, Hugging Face repository inspection schema, import-job service, generated shared contracts, and focused backend and desktop checks change. Model weights, saved configurations, active work and connected-server ownership remain protected.
