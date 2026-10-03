# Current handover

Updated 2026-10-03. Task 01 is implemented, reviewed and validated on `codex/reset-development-docs`, starting at `51c951133e8f017fd3bf61a02ad4195c87cd513d`. Final Git delivery is in progress. The 15 pre-existing `plans/` files are unchanged and remain untracked; later tasks have not started.

Removed 351 retired planning files, six generated development skills and their target marker, and 23 mirrored framework documents. README/AGENTS now describe current code, native owners and practical commands. Four engineering skills remain; three licence notices were relocated and the SDK notice retained under `.agents/notices/`. Stale explanatory identifiers and shipped project-change guidance are cleaned. OpenAPI/JSON schemas/TypeScript contracts remain, regenerated only for description/default-note text.

Verification: `uv run --project apps/backend python scripts/verify.py --tier acceptance --scope shared --scope workflow --scope docs` passed with stable inputs: backend 1,513 tests (one existing capability skip), integration 204, desktop checks/build, and contract freshness. Report: `.scratch/verification/20261003T155738Z-f8bb3758/report.json`. Independently reviewed with no findings; runner regressions pass 15 tests, default planning succeeds and removed scope is rejected. Locked installs, 31-document local-link audit, four skill metadata checks and Windows launcher preflight pass. No dependency/lock, SDK patch, permission or migration changes; no user data or weights touched. No restart, real-model trial or packaged-Windows test was needed.

Next: finish the current PR/merge and documentation-only gate. Task 02 requires Dave's separate instruction.
