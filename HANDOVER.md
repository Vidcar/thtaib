# Current handover

Updated 2026-09-28. **Unified model controls are complete and running locally.** [PR186](https://github.com/Vidcar/thtaib/pull/186) merged as `e7b71f7`. Specifications are synchronized; [completed change](openspec/changes/archive/2026-09-28-unified-model-controls/tasks.md) is archived.

Models owns saved setups, inline pinned recipes and response/memory tuning with one Save and explicit load/unload. Chat keeps local Thinking and context Reload/Stage. Agents saves in place; shared engine settings live in Settings. Native residency is separate from response identity. Accepted main/helper choices freeze policy/provenance and bind output budgets once through queues/retries/resumes. Import choices survive setup retry; existing effective saved values remain. New setups use native Auto/four-slot unified defaults.

The compiled b11045 / 2b1847030 native planner is installed, protocol1, digest `6164138f…`. Actual target/projector/separate-draft/shared-MTP allocations match native logs. Dynamic overhead remains unknown. Live checks verified non-disruptive preview, response reuse and capacity recovery. Knowledge-config concurrent publication is repaired.

Checks passed: backend default/integration (1,329 passed, four environment-specific skips), desktop build, generated contracts, OpenSpec and whitespace. Windows Electron UAT passed 32 theme/width/scaling layouts, keyboard use and two native turns. Reload preserved history, draft and attachment; unknown defaults remain editable and Reload stays visible.

Everyday app refreshed: backend12792/port8000, Electron23916/renderer12448, 49 authenticated tools; current assets, native compatibility and launcher completion verified. Histories/drafts/weights retained; isolated test processes stopped. Evidence: `.scratch/unified-model-controls/everyday-refresh.json` and `.scratch/unified-model-controls-uat/screens/report.json`.

Launch: `scripts/Launch-Workbench.ps1`. Standard checks remain in AGENTS.md. No outstanding work for this change. Preserve unrelated active changes: `lab-workbench`, `startup-catalogue`, `consolidate-product-contract`.
