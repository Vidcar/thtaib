# Current handover

Updated 2026-09-28. The [refined agent tool picker](openspec/changes/archive/2026-09-28-refine-agent-tool-picker/proposal.md) is delivered on `main`: [PR185](https://github.com/Vidcar/thtaib/pull/185), merge `f624e45`. OpenSpec is synced/archived; the open Windows Workbench was refreshed. Saved agent settings and Appearance preview are intact.

Picker: expandable group rows, independent selection/expansion, preserved bulk actions/access ownership. Desktop/regression/native gates, OpenSpec and whitespace passed; 24 isolated Windows UAT captures cover themes, responsive/scaled layouts, keyboard and draft retention. Evidence: `.scratch/tool-picker-uat/`; test backend stopped.

The original llama.cpp **b11045 / 2b1847030** audit is complete: `.scratch/llama-settings-audit/outputs/01a0e717-faf0-7801-9da7-da4a3db6aec1/llama-server-settings-b11045.xlsx`. It accounts for 500 entries/412 aliases, with native 4B/27B/MTP, fit/API/invalid-cache probes and 9,000 exported cells checked.

Model setup recommendations are complete: [journey/report](.scratch/llama-settings-audit/recommendations/outputs/01a0e768-7d8b-7483-b988-9506457c8a7a/model-setup-recommendations.html) and [setting matrix](.scratch/llama-settings-audit/recommendations/outputs/01a0e768-7d8b-7483-b988-9506457c8a7a/model-setup-settings-recommendations.xlsx). All 500 entries specify exposure, location, input/domain, suggested value and apply timing; 44 combined concepts reduce to six primary decisions. Main findings: pinned-card defaults already apply; Thinking is model-specific; separate response choices from loading identity; estimate all allocations together; Auto context means omission and Auto GPU requires fit On. Corrected reversed V-cache block-divisibility wording.

Review verification: current code/four saved model defaults, seven Windows screenshots, sandboxed exact-template rendering, 10,000 setting cells/440 control cells, filters/panes and all three sheet visuals passed. HTML content/search checks passed; local-file browser preview was blocked. No new native generation or product/specification/settings changes. Router PID24772 remains running; fresh read-only inventory had 14 unloaded entries. Weights preserved. No report work outstanding; implementation requires a new authorized change.

Permissions/model-picker [PR184](https://github.com/Vidcar/thtaib/pull/184)/[PR183](https://github.com/Vidcar/thtaib/pull/183) are preserved. Lab, Workflows/media and startup-catalogue remain separate active changes.

Normal launch: `scripts/Launch-Workbench.ps1`, port 8000. For product changes use desktop build, relevant backend suites, OpenSpec validation and whitespace checks. Keep disposable work under `.scratch/`.
