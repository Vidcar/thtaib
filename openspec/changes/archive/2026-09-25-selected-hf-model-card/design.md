# Design

## Context

My models already keys recipe refresh to the selected bundle, but it displays only parsed recipes. Installed cards are recorded with immutable Hugging Face source revisions and file hashes. The existing parser recognizes named thinking modes but not a single recommended sampler set.

## Goals / Non-Goals

**Goals:** Make the full pinned README readable for the selected installed model and offer explicit response configurations from conservative single-set recommendations.

**Non-Goals:** Fetch the moving `main` card for installed weights, apply card advice automatically, or turn prompt, projector and launch prose into settings.

## Decisions

- Share one backend card reader between the new read-only bundle card endpoint and recipe refresh. It first validates a recorded root README's byte limit and checksum, then fetches only the same pinned README when needed. The response exposes repository, revision, checksum, Markdown text and saved-versus-fetched origin. A recorded checksum remains required on fallback when available.
- Render the full card lazily in a bounded My models panel. Use inert Markdown without raw HTML or remote image loads; resolve safe relative links against the pinned repository and retain a direct pinned Hugging Face link. Key the panel to the selected bundle and discard late responses after selection changes.
- Extend the existing recipe parser only for a clearly headed single recommendation with either comma-separated assignments or one sampler per bullet. Require at least two valid supported response values, reject conflicting or unrecognized sampler assignments, and report other guidance in that section as omitted notes. Existing named-mode extraction keeps precedence to avoid duplicate candidates.
- Add a mode-neutral recipe value meaning “preserve” across backend and generated desktop contracts. Configuration creation overlays its sampler values on the current default but omits a reasoning override; only explicit on/off recipes require the verified template toggle. Existing recipe origins remain valid and idempotent.
- Keep refresh explicit. Reading a card does not rewrite stored candidates; Refresh reparses the selected pinned card and updates candidate metadata only. The UI distinguishes missing candidates from a missing card.

## Risks / Trade-offs

- Large or HTML-heavy cards can be slow or imperfectly formatted → render only on expansion, bound the panel, keep raw content inert and link to the pinned source.
- Publisher prose can contain examples or mixed settings → accept only narrow recommendation forms, label non-response omissions and reject conflicting response values.
- Card bytes may be missing or changed locally → verify before display and fall back only to the recorded immutable source, with an explicit error if verification fails.

## Migration Plan

Existing bundles and configurations remain valid. Newly recognized recipes appear after an explicit refresh; no saved setup is rewritten. The new mode-neutral value is additive to existing on/off recipe records.
