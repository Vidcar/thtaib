# Design

## Context

The importer pins and hashes selected GGUF files plus generic guidance companions. Model configurations, managed launches and chat request resolution currently have no link to those companion contents. See the proposal and MOD-024 for the intended behavior.

## Goals / Non-Goals

**Goals:** one immutable bundle configuration record, backend-owned effective settings, and desktop-visible provenance that can be checked against the running server and wire request.

**Non-Goals:** Safetensors execution, editing GGUF metadata, replacing llama.cpp template rendering, or treating every Transformers configuration key as a llama.cpp flag.

## Decisions

- Inspect Hugging Face metadata before transfer. A source-only link returns bounded GGUF candidates. A conversion can inherit source configuration only when its declared base model and conversion source SHA identify the same pinned publisher commit. Otherwise the source is unverified and the app offers only the GGUF's own metadata and files.
- Fetch source configuration into a namespaced managed bundle area using exact immutable revisions and hashes. Keep it separate from selected GGUF repository files so identical names cannot collide. Record the source identity, file hashes, selected template origin, normalized request defaults, and unsupported keys in the bundle.
- Use the GGUF embedded template when it differs from a standalone source template. If no embedded template conflicts, select the standalone file. An explicit publisher choice is validated using the pinned managed runtime's template parser and a representative rendered conversation before the saved selection changes; the managed launch uses the checked file and reports any later failure.
- Normalize only fields with a faithful runtime equivalent. Sampling and limits enter the common per-request resolution below explicit profile/chat settings; token suppression uses llama.cpp logit bias only after GGUF token identity verification. Source token IDs and architecture are checked or reported, never substituted into GGUF metadata. Unknown settings remain visible as unsupported.
- Persist defaults on the bundle instead of copying them into a user profile. This preserves the distinction between publisher defaults and intentional user overrides, including across restart and future profile edits. The same backend resolver feeds Models, Chat, Lab and Workflows; the desktop does not merge settings itself.

## Risks / Trade-offs

- Large candidate searches or remote metadata errors can delay inspection -> bound results and expose access/offline failures without starting a download.
- External templates may use constructs unsupported by the pinned runtime -> probe before selection and keep the GGUF choice available.
- A verified conversion can still have imperfect publisher metadata -> report selected and observed runtime settings separately and require actual two-family validation.
- Existing bundles lack this provenance -> leave their settings unverified until a deliberate repair/reimport; do not relabel their generic companions as applied.

## Migration Plan

Add optional bundle fields so old records remain readable. New downloads and explicit repair populate them. Validate in an isolated product root, then deploy the updated backend/desktop through the established local workflow; rollback uses the prior build and leaves existing weights and manifests intact.
