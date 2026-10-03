# Working on thtaib

thtaib ships as **Local AI Workbench**, a Windows-first local AI desktop. Own the requested work through implementation, proportionate checks, independent review where needed, and authorized Git/local delivery. Dave should not need to read code or operate development tools. Choose sensible defaults for reversible decisions; ask only about material unresolved behaviour, access, cost or external actions. Give brief, plain-English updates.

## Start with the current checkout

Read [HANDOVER.md](HANDOVER.md), inspect Git state, open PRs and ongoing agent work, then trace the affected code and callers. Preserve unrelated changes and serialize writers to shared files. The user's instructions define the requested outcome; current code, generated API contracts and executable behaviour establish the implementation baseline. Do not introduce another specification or planning system.

The files in `plans/` are the retained implementation pack. Work only on the task Dave authorizes, in its stated order; leave later tasks untouched. Check their source references against the current checkout. Keep one concise current handover, normally under 300 words, updated at meaningful milestones and before finishing substantial work. Replace stale status; record actual checks, relevant branch/PR and the next concrete step if unfinished.

## Keep the native owners

There is one FastAPI backend in `apps/backend` and one Electron/React desktop in `apps/desktop`. llama.cpp owns inference; Deep Agents owns agent loops/helpers; LangGraph owns execution/checkpoints; LangChain supplies interfaces and integrations. The application owns configuration, admission/queue records, effects, permissions, local processes, visible history and retained assets. The renderer owns presentation and drafts. Reuse these owners rather than adding another runtime, protocol or conversation store.

Before integration changes, inspect `apps/backend/uv.lock`, `apps/desktop/pnpm-lock.yaml` and the matching installed source in `.venv/Lib/site-packages` or `node_modules`. Current integration pointers: [Deep Agents 0.7.19](https://github.com/langchain-ai/deepagents/tree/deepagents==0.7.19), [LangChain 1.4.2](https://github.com/langchain-ai/langchain/tree/langchain==1.4.2) and [LangGraph SDK source for 1.11.1](https://github.com/langchain-ai/langgraphjs/tree/ec67d5d70dc26341e92a0962d9d2f4018c310b39). Verify actual lock resolutions before relying on a pointer. Preserve the SDK patch until its specific regressions prove it unnecessary. Keep existing Agent run / Builder names until their owning feature changes.

## Use the four development skills when useful

- [change-impact](.agents/skills/change-impact/SKILL.md): trace owners, callers and observable acceptance before substantive shared changes.
- [diagnose-failure](.agents/skills/diagnose-failure/SKILL.md): reproduce failures and establish their cause before fixing them.
- [review-change](.agents/skills/review-change/SKILL.md): inspect a concrete diff and its evidence. Arrange fresh-context independent review for consequential changes and changes to mandatory verification.
- [verify-delivery](.agents/skills/verify-delivery/SKILL.md): select applicable checks and distinguish automated, independent and live evidence.

These are coding-agent guidance. Shipped application skills live separately in `apps/backend/src/workbench_backend/knowledge/runtime_skills/`.

## Verify proportionately

From the root, use `uv run --project apps/backend python scripts/verify.py --help` or `--plan`, then select affected scopes: `docs`, `workflow`, `backend`, `desktop`, `shared`. Omitted scope means all; repeated scopes are additive. `shared` includes both consumers and generated-contract freshness. `workflow` checks the verification runner, not the visual workflow feature. Pure text needs `docs`; runner changes need `workflow`. Meaningful skill changes also need authoring metadata checks and applicable [agent exercises](.agents/skills/verify-delivery/references/exercises.md).

`fast` allows focused `--test tests.MODULE` and `--desktop-check scripts/check-NAME.mjs`. `acceptance` runs the selected area gates: backend default plus integration tiers, desktop `pnpm run build`, and shared-contract freshness. Example: `uv run --project apps/backend python scripts/verify.py --tier acceptance --scope shared`. `delivery --real-model` requires the existing isolated real-model fixtures; missing mandatory prerequisites block acceptance. Evidence is saved under `.scratch/verification/`; it does not certify independent review or the running desktop. Rerun affected checks after relevant edits.

Shared contract sources live in `apps/backend/src/workbench_backend/contracts/` and referenced schema owners. Regenerate from the root with `uv run --project apps/backend python scripts/generate_shared_contracts.py`; add `--check` for freshness. Preserve OpenAPI, JSON schemas and generated TypeScript; never hand-edit generated outputs.

Use isolated tests through `tests.run` or package-qualified unittest modules, bounded polling and worker cleanup. A mock is not a live model test. Verify build/process identity before claiming new artifacts are running. Documentation alone needs no model load or application restart. Keep remote CI disabled and respect repository protections without adding remote checks.

## Preserve permissions and data

Development autonomy never grants the product more runtime access. Preserve access choices, approvals, scope confinement and authored instructions. Host shell access is not sandboxing. Keep full visible history distinct from compacted model context and transport replay.

Preserve weights, runtimes, credentials, chats, drafts, project files and unrelated work, including ScratchArea and ScratchProject. Product data defaults to `%LOCALAPPDATA%\LocalAIWorkbench\`; tests/UAT use `WORKBENCH_DATA_ROOT` under the root `.scratch/`. Never reset product data to make a check pass, or commit secrets, weights, private data or unredacted model context. Remove only test records created for the task. Ask before new publishing destinations, spending, important-data deletion or contacting people unless specifically authorized; do not uninstall global tools as repository cleanup.

## Finish delivery

Own appropriate commits, pushes, PRs, merges and clear routine conflict resolution. Resolve failures and supported review findings; do not bypass checks. Make the result ready locally and refresh an established deployment only when the requested outcome needs it. Report the usable result, checks actually run and truthful limitations. Update the existing handover and stop when the authorized task is complete.
