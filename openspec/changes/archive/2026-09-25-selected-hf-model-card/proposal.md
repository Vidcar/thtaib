# Proposal

## Why

The Models screen shows only response recipes extracted from a Hugging Face README, so installed models with valid cards can appear to have no model card at all. The current extractor also misses clear single-set sampler recommendations in the installed Gemma and jica98 cards.

## What Changes

- Show the full, verified card for the model selected in My models, tied to that model's installed repository revision.
- Offer explicit configuration creation from supported single-set response recommendations, while showing guidance that is not copied.
- Preserve the selected configuration's thinking choice when a card does not recommend a thinking mode.
- Keep card viewing and refresh separate from applying settings.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: Selected-model card viewing, conservative single-set recipe extraction, and unchanged thinking mode for mode-neutral recipes.

## Impact

The existing Hugging Face card reader, model recipe and configuration records, a read-only backend card response, Models desktop presentation, generated HTTP contracts, and model acceptance checks change. Model weights, saved configurations, and live deployments remain untouched by card viewing or refresh.
