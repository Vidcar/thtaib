# Tasks

## 1. Pinned card access

- [x] 1.1 Share a size- and hash-verified card reader between viewing and refresh, with pinned Hugging Face fallback; verify local, fallback, missing, corrupt and no-weight cases in backend tests.
- [x] 1.2 Expose the selected bundle's full card and provenance through a read-only response contract; verify route identity and generated-contract freshness.

## 2. Response recommendations

- [x] 2.1 Extract the Gemma inline and jica98 per-field recommendation formats conservatively, including omitted guidance; verify fixtures and ambiguous-value rejection alongside existing recipes.
- [x] 2.2 Add mode-neutral recipes and configuration creation that preserves thinking, launch and unrelated response settings; verify explicit creation, existing mode checks and retry idempotency.

## 3. Models desktop

- [x] 3.1 Show the selected Hugging Face bundle's full pinned card in an on-demand, bounded, inert viewer with source link; verify loading, failure and late-switch behavior in desktop checks.
- [x] 3.2 Present mode-neutral recipes and omission notes in My models and Add models; verify refresh and explicit configuration creation in desktop checks.

## 4. Delivery

- [x] 4.1 Validate actual installed Gemma and jica98 pinned cards without altering their configurations, and run backend default/integration, desktop build, contract, OpenSpec and diff checks.
- [x] 4.2 Refresh handover, verify the established local app, and prepare the reviewed Git changes for PR delivery.
