# Current handover

Updated 2026-09-28. The [refined agent tool picker](openspec/changes/archive/2026-09-28-refine-agent-tool-picker/proposal.md) is delivered on `main`: [PR185](https://github.com/Vidcar/thtaib/pull/185), merge `f624e45`. OpenSpec is synced/archived; the open Windows Workbench was refreshed. Saved agent settings and Appearance preview are intact.

Picker decisions: one expandable rounded group row, selected/total count and switch; independent expansion/selection, partial-to-full toggling, preserved bulk actions and canonical settings/access ownership.

Desktop build/typecheck/regression/native gates, all 12 OpenSpec changes/specs and whitespace passed. Isolated built Windows UAT passed 24 captures covering creation/editing, both themes, responsive widths, scaling, keyboard controls and draft retention. Evidence: `.scratch/tool-picker-uat/`; test backend stopped.

Running-server settings audit is complete for installed llama.cpp **b11045 / 2b1847030**. Output: `.scratch/llama-settings-audit/outputs/01a0e717-faf0-7801-9da7-da4a3db6aec1/llama-server-settings-b11045.xlsx` (Assessment plus 500 filtered entries). Exact source, catalogue and raw probes are beside it. No product/specification or preset changes.

Audit checks: 412 aliases accounted for (403 parser passes, eight obsolete aliases rejected, RPC source-only); existing 4B and 27B/MTP loaded/generated/unloaded; metadata-only fit, API clamps, ignored property/speculative writes and invalid quantized-V/Flash-Attention combination checked. Export matched all 9000 data cells, filters/panes and visual review. Original router remained running, initial empty residency restored, temporary workers stopped, backend healthy; weights preserved. No audit work outstanding.

Permissions/model-picker [PR184](https://github.com/Vidcar/thtaib/pull/184)/[PR183](https://github.com/Vidcar/thtaib/pull/183) are preserved. Lab, Workflows/media and startup-catalogue remain separate active changes.

Normal launch: `scripts/Launch-Workbench.ps1`, port 8000. For product changes use desktop build, relevant backend suites, OpenSpec validation and whitespace checks. Keep disposable work under `.scratch/`.
