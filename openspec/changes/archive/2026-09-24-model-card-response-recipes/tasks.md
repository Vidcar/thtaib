# Tasks

## 1. Backend import and configuration

- [x] 1.1 Preserve and validate the file hint against pinned complete variants; verify exact-selection and unavailable-hint tests.
- [x] 1.2 Extract pinned-card recipes separately from automatic defaults and correct sampler validation; verify card, ambiguity, zero and penalty tests.
- [x] 1.3 Persist selected recipe IDs through import/retry and create idempotent configurations after install; verify durable-job, default, collision, template and partial-failure tests.
- [x] 1.4 Refresh existing-bundle card metadata without weights or setup changes; verify local-hash, pinned-fetch and no-mutation tests.

## 2. Desktop journeys

- [x] 2.1 Make variant family and exact-file selection clear and offer recipes during import; verify link-hint, accessibility and selection checks.
- [x] 2.2 Show effective value/source for staged model controls without saving inherited overrides; verify model-settings UI checks and desktop build.
- [x] 2.3 Offer pinned-card refresh and explicit configuration creation on installed models; verify library refresh, error recovery and stale-selection checks.

## 3. Integrated acceptance

- [x] 3.1 Run backend default and integration suites, shared-contract freshness, desktop build and OpenSpec validation; repair any regression.
- [x] 3.2 Import the intended LOW-MTP IQ4_XS beside the standard file and verify its actual template, loaded behavior and transmitted recipe values on Windows; preserve both weights.
- [x] 3.3 Update the established local app and handover after checks; verify the intended configurations and default are usable.
