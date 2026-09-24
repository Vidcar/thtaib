# Current handover

Updated 2026-09-24. Active branch: `codex/deepagents-0718-simplify`. The Deep Agents 0.7.18 upgrade and simplification are implemented. The focused OpenSpec change is archived at `openspec/changes/archive/2026-09-24-upgrade-deepagents-simplify-workbench/`; current specs and overlapping active changes are reconciled. Dave chose Deep Agents' native model-aware summarization thresholds, retaining Workbench's narrow input-budget correction.

Final checks passed: backend default 724 tests (one skip), integration 188, desktop build, shared-contract freshness, and OpenSpec validation 13/13. A real Windows Qwen3.8 tool turn passed. The desktop displayed one ordered `ask_user` plus shell approval batch; selecting Alpha and approving `echo WORKBENCH-APPROVAL` produced a final model answer with exit code 0 at 16K context. The 4K setup exposed Workbench's early custom summary trigger, which was replaced by native defaults and verified in focused tests.

The user-authorized reset removed all old app data and all six approved linked project folders, including the separate Git repository. Model weights, runtimes, and Hugging Face staging/cache were preserved. A second audited reset removed live-validation chats/project. The established desktop has been rebuilt and relaunched: Chat visibly has no chats or projects, Attention shows zero items, and Qwen3.8 is ready at 16K context (`deploy_252229cd8cec`). No migration or compatibility paths were added.

Next: commit, push, open and merge the PR, mark archived task 4.5 complete, and refresh this handover with the delivery pointer. Shell commands must use RTK.
