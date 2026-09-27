# Design

## Context

See proposal.md for motivation. Chat's owned SDK projection feeds the transcript directly. The composer consumes a cached conversation run plus a separate lightweight measurement subscription; its cache signature omits activity-only updates. The hover token strip inherits arbitrary word breaking while compressing four pairs horizontally.

## Goals / Non-Goals

**Goals:** One truthful main-Chat activity readout, current scoped measurements, readable compact token rows and preserved transcript continuity.

**Non-Goals:** Backend execution changes, new wire fields, reasoning/answer phase detection, helper UI removal or data migration.

## Decisions

- Extend the existing measurement subscription with an owner key and lifecycle/activity snapshot. The composer accepts only its current owner/run. Guard publication against stale selection and retain lightweight updates rather than making every token update the full conversation.
- Resolve cancellation, saving, waiting, summary and tool execution before generation observations. Use Generating for a current generation sample, Preparing for current prompt processing, and Working for active work without precise observation. Pending admission takes Starting; terminal work clears live stages.
- Add an opt-out for live shared-feed message badges, used by main Chat only. Keep Partial markers on stopped incomplete messages and leave other surfaces/helpers on their existing presentation. Remove main-Chat generic waiting/saving transcript lines.
- Use vertically aligned token pairs with nonbreaking, right-aligned values and wrapping labels. Retain all reported counts and explain input subdivisions. Current/last-request speed text reflects the observed interval; unavailable values stay unavailable.

## Risks / Trade-offs

- Stale global readout after navigation -> match the selected owner/run and guard publication with current selection identity; test switching away/back and late events.
- Measurements disturb stable transcript -> keep the current lightweight subscription and verify mounted row continuity.
- Broad shared-feed impact -> default the new presentation option to existing behaviour and opt out only in main Chat.

## Migration Plan

No stored-data or wire migration. Validate existing desktop regressions and native/live isolated Chat, archive the completed OpenSpec change, merge the validated branch and rebuild the established desktop. Preserve unsaved everyday editor work.
