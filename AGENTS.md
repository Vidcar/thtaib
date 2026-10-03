# Working on thtaib

thtaib ships as **Local AI Workbench**, a Windows-first local AI desktop. Own the requested work through implementation, proportionate checks, independent review where needed, and authorized Git/local delivery. Dave should not need to read code or operate development tools. Choose sensible defaults for reversible decisions; ask only about material unresolved behaviour, access, cost or external actions. Give brief, plain-English updates.

## Start with the current checkout

Read [HANDOVER.md](HANDOVER.md), inspect Git state, open PRs and ongoing agent work, then trace the affected code and callers. Preserve unrelated changes and serialize writers to shared files. The user's instructions define the requested outcome; current code, generated API contracts and executable behaviour establish the implementation baseline. Do not introduce another specification or planning system.

The [Local AI Workbench GitHub Project](https://github.com/users/Vidcar/projects/5) tracks agreed work, unresolved choices, dependencies and delivery. Read its README and the relevant issue before substantial work. GitHub issues are the planning source; reviewed issue content records the intended change, while source appendices preserve original proposals without granting blanket approval. Maintain plans and decisions there rather than recreating a local planning folder. Work only on the task Dave authorizes, in its agreed order; leave later tasks untouched and check source references against the current checkout. Keep one concise current handover, normally under 300 words, updated at meaningful milestones and before finishing substantial work. Replace stale status; link the issue, actual checks, branch/PR and next concrete step if unfinished.

## Maintain the GitHub Project

Use GitHub CLI/API for routine tracking; no browser is needed to maintain issues, comments, item fields, membership, parent/sub-issue relationships or prerequisites. The owner is `Vidcar`, project number `5`, repository `Vidcar/thtaib`. [Context #243](https://github.com/Vidcar/thtaib/issues/243) holds the retained pack boundaries; task issues are #244–256 and decision issues #257–261. Find the current item before creating anything; do not duplicate it or treat these ranges as a permanent inventory.

### Access and commands

On this Windows host, invoke the installed executable directly. GitHub CLI 2.100.0 supports the name-based commands below; on another host, locate `gh.exe`/`gh` and check its help. Verify authentication and actual private-project access at the start of a fresh session:

```powershell
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
& $gh auth status --hostname github.com
& $gh project view 5 --owner Vidcar --format json
& $gh project field-list 5 --owner Vidcar --format json
& $gh project item-list 5 --owner Vidcar --limit 100 --format json --jq '{totalCount,items:[.items[] | del(.content.body)]}'
```

Raise the limit or paginate when the returned items do not cover `totalCount`. Then read the selected issue and comments with `gh issue view` and inspect its native parent/prerequisites. Access was verified on 2026-10-03: active account `Vidcar`, Windows keyring credentials, `repo` and `project` scopes, repository admin and Project write access. Recheck rather than assuming another session/host has access. If authentication fails, ask Dave to complete the CLI login; if only the Project scope is missing, use `gh auth refresh --hostname github.com --scopes project`. Do not refresh working credentials, expose tokens, or save credentials in this repository. A successful login alone does not prove Project write permission.

Set the variables below from the currently authorized task; examples show syntax, not authorization to start a task. Write multiline content to a UTF-8 file and pass `--body-file`. Always specify the repository/owner.

```powershell
& $gh issue view $issueNumber --repo Vidcar/thtaib --comments
& $gh issue edit $issueNumber --repo Vidcar/thtaib --body-file $bodyFile
& $gh issue comment $issueNumber --repo Vidcar/thtaib --body-file $evidenceFile
& $gh project item-add 5 --owner Vidcar --url $issueUrl
& $gh project item-edit 5 --owner Vidcar --url $issueUrl --field Status --value 'In progress'
& $gh project item-edit 5 --owner Vidcar --url $issueUrl --field Agreement --value Agreed
& $gh project item-edit 5 --owner Vidcar --url $issueUrl --field Order --number $order
& $gh issue edit $issueNumber --repo Vidcar/thtaib --parent $parentNumber --add-blocked-by $prerequisiteNumber
```

Each item-edit updates one field. Current CLI also supports removing prerequisites and adding/removing sub-issues; inspect help before unfamiliar operations. For GraphQL, use `gh api graphql` with a structured JSON input file; discover current node/field/option IDs rather than hardcoding them. See the [Project API guide](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects) and [item-edit manual](https://cli.github.com/manual/gh_project_item-edit).

### Keep agreement and delivery truthful

- At the start, reconcile the issue, Agreement, Status, Order and open prerequisites with Dave's current instruction and the checkout. Existing authorization remains valid; do not ask again just to satisfy a field. Record the agreed outcome, boundaries and acceptance criteria before implementation. Respect explicit read-only requests.
- New proposals start **Backlog / Needs review**. Set these explicitly when adding an item. Use `plan-task`, `decision` or `plan-reference` labels as appropriate. Retain the original pack text; update the reviewed summary and record decisions with their rationale. Plan tasks belong under #243; decision issues belong under their owning task and block it until resolved. Give decisions their owner's Order. Do not reorder later work without an agreed reason.
- **Agreement:** Needs review = unconfirmed; Agreed = authorized scope recorded; Revisit = a material change or reopened outcome needs review. **Status:** Ready requires agreed scope, clear acceptance and satisfied prerequisites; In progress means implementation has started; In review means verification/review is underway; Blocked requires a concrete reason and next unblocking step.
- During authorized work, update at meaningful milestones and before finishing. Record PR links, checks and results, independent review, actual Windows/model evidence, local delivery and remaining limits in the issue. Update its summary when scope changes; preserve Dave's edits and unrelated work. Keep HANDOVER concise with links to this detail.
- Set **Done** and close with `--reason completed` only after the agreed outcome is verified, relevant changes are merged and required local delivery is complete. A decision can be Done once Dave's decision and rationale are recorded; it does not require an implementation PR. Use **Not planned** and close with `--reason 'not planned'` for rejected/withdrawn work. Reopened work returns to review with Agreement Revisit before further implementation.
- Serialize remote writers, re-read saved issue/field/relationship values after changes and reconcile partial failures before retrying. Report an access or update failure honestly; do not claim synchronization from a command being dispatched.

Plan, Delivery, Decisions and Completed are the saved views. Auto-add issues/sub-issues and the Backlog default are configured; automatic closure, completion and archiving remain disabled. Maintain both issue state and Project status explicitly: issue closure or PR merge alone does not establish Done. Routine CLI/API maintenance covers Project description/README, fields, items and relationships. Workflow activation/filter changes, field defaults and view sorting/grouping currently require the browser; use it only for requested settings changes. Project workflows are separate from GitHub Actions; keep remote CI disabled.

The Project is private but repository issues are public. Keep secrets, private logs and unnecessary personal data out of issues and notes. Preserve Project visibility, access and unrelated items/settings unless Dave authorizes a change.

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

Preserve weights, runtimes, credentials, chats, drafts, project files and unrelated work, including ScratchArea and ScratchProject. Product data defaults to `%LOCALAPPDATA%\LocalAIWorkbench\`; tests/UAT use `WORKBENCH_DATA_ROOT` under the root `.scratch/`. Keep one `.scratch/` directory at the repository root for temporary outputs, browser captures and validation evidence; resolve it from the checkout root regardless of the current working directory. Do not create nested `.scratch/` directories. Never reset product data to make a check pass, or commit secrets, weights, private data or unredacted model context. Remove only test records created for the task. Ask before new publishing destinations, spending, important-data deletion or contacting people unless specifically authorized; do not uninstall global tools as repository cleanup.

## Finish delivery

Own appropriate commits, pushes, PRs, merges and clear routine conflict resolution. Resolve failures and supported review findings; do not bypass checks. Make the result ready locally and refresh an established deployment only when the requested outcome needs it. Report the usable result, checks actually run and truthful limitations. Update the existing handover and stop when the authorized task is complete.
