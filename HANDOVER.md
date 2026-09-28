# Current handover

Updated 2026-09-28. [Refine agent tool picker](openspec/changes/archive/2026-09-28-refine-agent-tool-picker/proposal.md) is implemented, validated, synced and archived on `codex/refine-agent-tool-picker`; merge and local refresh are in progress. The permissions/model-picker follow-up is merged as [PR184](https://github.com/Vidcar/thtaib/pull/184); [PR183](https://github.com/Vidcar/thtaib/pull/183) remains its delivered baseline. Lab, Workflows/media and startup-catalogue stay separate. Preserve weights and unrelated work.

Picker decisions: one rounded group row, name left, one selected/total count and switch right; row expands indented tools without an arrow or second heading. Expansion and selection are independent. Partial groups switch on to complete the set. Groups start collapsed, open independently and remain open while editing. Existing bulk actions and canonical agent settings/access ownership remain intact; no API or migration changes.

Shared rounded rows and independent controls are implemented. Full desktop build/typecheck/regression/native gates passed, including editor checks for partial/full/off selection, multiple open groups, bulk actions, unavailable/loading/disabled states and retained drafts. OpenSpec passed all 13 current items; whitespace passed. Optional design is omitted because the change stays in the existing editor.

Built Windows UAT passed against a separate real backend: 24 captures covering agent creation/editing, collapsed/expanded groups, both themes, 1280/760 widths and 100%/125% scaling with no horizontal overflow or alignment failures. Native Enter/Space/Tab, actual saved versions and draft retention across agent navigation/creation steps passed. Evidence: `.scratch/tool-picker-uat/`.

Next: merge the validated picker PR and refresh the normal app, then verify delivery and clean Git state and mark the archived delivery task complete. The everyday Agents editor was inspected and currently has no unsaved changes; check again immediately before reload. Existing Appearance preview is left intact. Previous UAT evidence remains under `.scratch/chat-controls-uat/` and `.scratch/polish-controls-uat/`.

Normal launch: `scripts/Launch-Workbench.ps1`; port 8000. Keep disposable validation under root `.scratch/`.
