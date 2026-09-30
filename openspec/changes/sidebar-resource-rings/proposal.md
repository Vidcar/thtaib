# Proposal

## Why

The persistent navigation rail does not show live GPU-memory or system-RAM usage. Dave needs a small, quiet monitor beneath Settings that stays useful across every page without opening another panel.

## What Changes

- Add two fixed-size GPU/RAM rings in the existing 54px rail, with whole percentages, theme-based green/amber/muted-red usage colours and independent grey stale states.
- Reuse the hardware observer shared with Models, add NVIDIA's reported used memory and per-metric freshness, and expose authenticated read-only `GET /v1/system/resources`.
- Poll every two seconds only while visible, retain last valid readings on failures, and provide accessible descriptions without menus, model loading or transcript updates.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: persistent system-resource rings and their read-only observation boundary.

## Impact

Backend hardware observation, inference routes and additive generated contracts; desktop rail presentation and isolated polling. Existing Models available-memory calculations and the local-service dot remain independent. No new dependencies, monitoring process, persistent telemetry or data migration.
