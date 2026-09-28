# Current handover

Updated 2026-09-28. **Unified model controls are implemented and validated** on `codex/unified-model-controls`; Git delivery, everyday app refresh and archive remain. Contract/tasks: [OpenSpec change](openspec/changes/unified-model-controls/tasks.md). Main specifications are synchronized.

Models owns saved setups, inline pinned recipes, response and memory tuning with one Save; load/unload is explicit. Chat keeps local Thinking and deliberate context Reload/Stage. Agents saves in place; shared engine settings live in Settings. Exact native residency is separate from saved response identity. Accepted main/helper choices freeze policy/provenance and bind numeric budgets once, including queued/retried/resumed execution. Import choices survive setup retry with weights retained. Existing effective saved values are preserved; new setups use native Auto/four-slot unified defaults.

The compiled b11045 / 2b1847030 native planner is installed. Actual text/vision/separate-draft/shared-MTP allocations match native logs. Dynamic overhead remains unknown. Live checks verified non-disruptive preview, same-child response reuse and capacity recovery. The knowledge-config concurrency repair passed regression checks.

Checks passed: backend default/integration (1,329 passed, four environment-specific skips), final desktop build, generated contracts, all 13 OpenSpec items and whitespace. Windows Electron UAT passed 32 theme/width/scaling layouts, keyboard use and two real native turns. Reload preserved history, draft and uploaded attachment; unknown Thinking defaults remain editable and the Reload footer stays visible.

Next: commit/PR/merge, refresh through `scripts/Launch-Workbench.ps1`, then archive and finalize this handover. Preserve weights and unrelated active changes (`lab-workbench`, `startup-catalogue`, `consolidate-product-contract`). Isolated UAT processes stopped; original router PID24772 remains. Evidence: `.scratch/unified-model-controls/` and `.scratch/unified-model-controls-uat/screens/report.json`. Everyday product data remains `%LOCALAPPDATA%\LocalAIWorkbench`, backend port8000.
