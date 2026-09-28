# Design

## Context

See proposal.md. Both controls already use shared backend authorities; the changes concern desktop presentation.

## Goals / Non-Goals

Make remembered approvals discoverable and model/configuration identity readable. Keep existing grant scopes and model loading intact.

## Decisions

- Refresh grant presence only when opening access; a failed lookup leaves management available through Settings.
- Keep configuration rows directly visible instead of adding another expand button. Whole rows remain selectable through the existing exact-configuration path.
- Shorten generated repository/file labels while preserving authored names, quantization and filename variants. Distinguish shortened collisions by publisher or installation label; full identities remain searchable and in tooltips.

## Risks / Trade-offs

- More configuration rows require scrolling; the existing bounded list and keyboard following remain in use.
- Reloading an open editor could discard an unrelated draft; validate in an isolated window and refresh the everyday renderer only when its draft is safe.
