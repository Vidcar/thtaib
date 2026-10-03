# Current handover

Updated 2026-10-03. Authorized repository cleanup is tracked in [#264](https://github.com/Vidcar/thtaib/issues/264) on `codex/repository-cleanup`, starting from main `c2cd4bd900fdcf30fbacafef0e6f51897cbacfdf`. Local cleanup and focused checks are complete; review and Git delivery are pending.

Removed 18 orphan compiled Python caches and 11 obsolete/empty directories, including root `tests/specs`, old `.github/scripts`, `.vite`, the empty backend browser-worker resources and both nested `.scratch` remnants. Maintained source paths now contain one root `.scratch`; the scan excludes dependency/build environments, product/model data and retained scratch contents.

Preserved all 339 historical browser captures/logs under `.scratch/browser-artifacts/legacy-playwright-20261003`; file hashes match. Renamed `tests.test_deepagents_0718` to `tests.test_deepagents_release` without changing content or coverage. AGENTS now requires root scratch resolution regardless of working directory; ignore rules retain safety nets.

The 15 untracked `plans/` files are unchanged by hash. Current application tests, licences, generated contracts, dependencies, permissions, weights and product data are preserved. Audit found no active OpenSpec dependency. Exact cleanup manifest: `.scratch/repository-cleanup/cleanup-result.json`.

[Local AI Workbench Project](https://github.com/users/Vidcar/projects/5) remains the tracking entry point; [AGENTS](AGENTS.md#maintain-the-github-project) documents CLI/API maintenance. Access was reverified without a browser. Task 01 remains Done/Agreed; Tasks 02–13 and five decisions remain Backlog/Needs review. Cleanup is an agreed prerequisite before Task 02. Keep automatic completion and remote CI disabled.

Checks passed: six renamed tests, default-tier discovery, 15 verification-runner tests, whitespace checks and default verification planning. Report: `.scratch/verification/20261003T175434Z-04445315/report.json`. Next: finish review and Git delivery. [Task 02 #245](https://github.com/Vidcar/thtaib/issues/245) still requires Dave's scope review/instruction before implementation. No application restart is needed.
