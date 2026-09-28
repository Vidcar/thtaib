# Current handover

Updated 2026-09-28. The [refined agent tool picker](openspec/changes/archive/2026-09-28-refine-agent-tool-picker/proposal.md) is complete and delivered on `main`: [PR185](https://github.com/Vidcar/thtaib/pull/185), merge `f624e45`. OpenSpec is synced and archived. The open Windows Workbench was refreshed and the new rows verified; saved agent settings are unchanged and the normal backend remains healthy. Existing Appearance preview is intact.

Picker decisions: one rounded group row, name left, one selected/total count and switch right; row expands indented tools without an arrow or second heading. Expansion and selection are independent. Partial groups switch on to complete the set. Groups start collapsed, open independently and remain open while editing. Existing bulk actions and canonical agent settings/access ownership remain intact; no API or migration changes.

Full desktop build/typecheck/regression/native gates passed, including partial/full/off selection, multiple open groups, bulk actions, unavailable/loading/disabled states and retained drafts. Final OpenSpec validation passed all 12 active changes/specs; whitespace passed.

Built Windows UAT passed against a separate real backend: 24 captures covering creation/editing, collapsed/expanded groups, both themes, 1280/760 widths and 100%/125% scaling without overflow or alignment failures. Native Enter/Space/Tab, saved versions and draft retention passed. Evidence: `.scratch/tool-picker-uat/`; isolated backend stopped.

No outstanding picker work. Permissions/model-picker [PR184](https://github.com/Vidcar/thtaib/pull/184) and [PR183](https://github.com/Vidcar/thtaib/pull/183) are preserved. Lab, Workflows/media and startup-catalogue remain separate active changes. Preserve weights and unrelated work.

Normal launch: `scripts/Launch-Workbench.ps1`; port 8000. Launcher compatibility check passed. Verify desktop changes with `pnpm run build` in `apps/desktop`, `openspec.cmd validate --all` and `git diff --check`. Keep disposable validation under root `.scratch/`.
