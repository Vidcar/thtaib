# Working on Local AI Workbench

Dave wants to use the product. Agents own implementation, proportionate validation, independent review and authorized Git/local delivery, including PRs, merges and routine conflict resolution. Choose sensible defaults; do not ask Dave to run commands, operate Git or select routine architecture. Ask only for a material unresolved product decision, access restriction or consequential action outside the authorized scope. Keep updates brief and plain-English.

## Find the relevant context

Start substantial work with [HANDOVER.md](HANDOVER.md), the actual working tree, open PRs and ongoing agent work. Preserve unrelated changes and keep writers to shared files serial. Current product contracts are [OpenSpec specs](openspec/specs/); plans and unfinished work are [OpenSpec changes](openspec/changes/). Read the affected capability and interfaces, and [architecture](openspec/specs/architecture/spec.md) when crossing boundaries. Discover with `openspec context --json`, `openspec list --specs` and `openspec show <capability> --type spec`. Use `openspec.cmd` on Windows if needed.

OpenSpec is the sole specification/change-planning system. Use its generated skills without editing them; explicit user authorization takes precedence over generic skill pauses. Tooling-only changes may use `skip_specs: true`; do not invent product requirements or parallel trackers. Workflows is the intended product area; do not rename existing Agent run / Builder surfaces as incidental cleanup.

## Route ordinary development work

These repository-local skills are for coding agents, never application runtime skills. Natural requests are sufficient; load only what applies:

- [change-impact](.agents/skills/change-impact/SKILL.md): before substantive shared-behaviour, ownership or boundary changes; trace owners, consumers and observable acceptance.
- [diagnose-failure](.agents/skills/diagnose-failure/SKILL.md): bugs, failing checks, regressions or repeated failed fixes; reproduce and challenge the cause before editing.
- [review-change](.agents/skills/review-change/SKILL.md): inspect a concrete diff and its tests. The implementer arranges fresh-context independent agent review for consequential changes, including this verification system and mandatory checks. Scrutinize weakened guards explicitly. Trivial edits need no multi-agent ceremony.
- [verify-delivery](.agents/skills/verify-delivery/SKILL.md): before completion, merge or deployment refresh; distinguish automated evidence, independent review and live results.

When a defect escapes, improve a regression or executable boundary where possible. Change skills only when the workflow needs improvement; do not accumulate historical rules or schedule autonomous refactoring.

## Verify locally

From the repository root: `uv run --project apps/backend python scripts/verify.py --tier acceptance --scope desktop` (use `--help` or `--plan`). Scopes are additive: `docs`, `workflow`, `backend`, `desktop`, `shared`, `spec`; omitted scope means all. Select affected consumers by impact, not filenames alone. `shared` includes backend, desktop and generated contracts. `workflow` tests the runner; skill changes also need authoring-tool metadata validation and the relevant [agent exercises](.agents/skills/verify-delivery/references/exercises.md). Pure text edits use `docs`; OpenSpec edits also use `spec`.

`fast` supports focused backend `--test tests.test_name` or desktop `--desktop-check scripts/check-name.mjs`. `acceptance` runs area delivery gates: backend default **and** integration tiers, desktop `pnpm run build`, shared contract freshness and/or `openspec validate --all`. `delivery` adds required runtime verification when the outcome needs it; `--real-model` selects the existing smoke with required assets. The runner records revision, worktree inputs, commands and results under `.scratch/verification/`; it never certifies independent review or live desktop behaviour. Mandatory failure/unavailability blocks acceptance. Later relevant edits require affected checks again.

Use isolated deterministic tests via `tests.run` or package-qualified tests, with bounded condition polling and worker cleanup. A mock is not a live backend/model check. Verify build and process identity before claiming the running application uses new artifacts. Do not reload an old window as proof, start conflicting processes, or run full suites for trivial text. Keep GitHub CI disabled; respect branch protections without adding remote checks.

## Preserve boundaries and data

One FastAPI backend (`apps/backend`) and one Electron/React desktop (`apps/desktop`). Reuse llama.cpp inference, Deep Agents loops, LangGraph checkpoints/workflows and LangChain interfaces; inspect pinned source or [local upstream references](.agents/references/langchain/README.md) when integrations change. The app owns lifecycle, settings, identity, permissions and records; frontend projections do not own execution or durable state. Development autonomy never weakens runtime permissions or approvals.

Keep model weights, unrelated files and scope-protected data (including ScratchArea and ScratchProject chats). Other development chats, memories and skills are disposable; avoid compatibility shims solely to retain obsolete fixtures. Product data lives under `%LOCALAPPDATA%\LocalAIWorkbench\` (Linux: `~/.local/share/LocalAIWorkbench/`); use root `.scratch/` for isolated development/UAT data and temporary output. Remove test-only records after necessary live checks. Never commit secrets, weights, private data or unredacted model context. Ask before new publishing destinations, spending, important-data deletion or contacting people unless specifically authorized.

## Done means delivered

Deliver the requested usable outcome, pass applicable checks, resolve supported review findings and state limitations truthfully. Refresh an established local deployment only when needed and authorized. Update the existing handover during substantial work and before finishing: a concise current snapshot with relevant branch/PR, actual verification and next step if unfinished. Preserve unrelated active changes; do not resume historical cleanup merely because it appears in the handover.
