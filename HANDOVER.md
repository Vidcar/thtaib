# Current handover

Updated 2026-10-04. Dave authorized [Task 03.3 #273](https://github.com/Vidcar/thtaib/issues/273), Agreed/Order 3 under open parent [#246](https://github.com/Vidcar/thtaib/issues/246). Delivery is in progress on `codex/compaction-history`, base `df717ed`. Goal: complete published Chat/Agent history survives native context reduction, reconnect and reopening.

Implemented first complete tool-result preservation by message ID; human/assistant completion updates remain supported. Native summaries/checkpoints, replay, scoped tools, permissions, edits/rewinds and SDK patch retain their owners. No public API/store/migration/dependency addition or speculative historical reconstruction. Supported images, upgrades and broader crash recovery remain outside this slice.

Preliminary evidence: 103 affected backend tests and 23 fixture tests passed without skips; desktop build/typecheck passed. Fresh-context independent CLI review found no remaining actionable defects after scenario corrections, independently passing 79 focused backend/verification tests and both rendered journeys. Built Windows compaction passed both screens with completed-backend restart, exact history and one write/three reads. Existing product snapshot comparison preserves 30 tables/7,409 file fingerprints and authored settings; large assets use metadata fingerprints. Actual Qwen3.5 4B compaction is running; frozen full delivery gates, negative controls, merge and local refresh remain outstanding.

Agent reopening uses the existing enabled completion notice once; real Agent configuration enters through public admission, then actual approval/display/navigation/reload. Chat uses its composer. These are explicit journey conditions.

Next: complete model/gates/negative controls, review evidence, merge, refresh established backend/desktop while preserving exact loaded CUDA router/27B processes, verify preservation, reconcile/read back GitHub and update this snapshot. Root `.scratch/task03-compaction/` retains evidence/scripts. Parent #246 stays open; #247/#257 remain unagreed. Remote CI stays disabled; no later implementation authorized.
