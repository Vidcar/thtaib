# Proposal

## Why

Model cards often contain several response recommendations that the current Hugging Face importer cannot expose or apply as an explicit choice. Similar filenames can also obscure the exact GGUF variant being installed, while inherited settings appear as bare defaults even when their values are known.

## What Changes

- Preserve a file-specific Hugging Face link through inspection and make the exact primary variant prominent before transfer.
- Extract conservative, revision-pinned response recipes from a GGUF repository card and offer explicit creation of named model configurations during import or after a metadata-only refresh.
- Keep card recommendations separate from verified automatic generation defaults, and validate zero-valued samplers and supported penalties correctly.
- Show resolved values and sources across model controls without saving inherited values as overrides.
- Import and verify the selected LOW-MTP IQ4_XS variant separately from the already installed standard IQ4_XS variant.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: Exact Hugging Face file selection, card-derived response choices, durable configuration creation and refresh, and effective model-control presentation.

## Impact

The existing Hugging Face fetch/import boundary, model bundle and configuration records, Models desktop UI, shared HTTP contracts, and model acceptance checks change. Card text does not gain authority to set automatic request defaults or runtime loading settings.
