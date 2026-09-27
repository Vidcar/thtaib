# Local AI Workbench

The Windows-first desktop for **thtaib**, a local-first AI workspace for using and understanding models, Chat, Lab and Workflows. **Agent run / Builder** are existing UI terms for Workflows; the desktop name remains Local AI Workbench. Current product contracts and future changes use [OpenSpec](openspec/). Contracts include intended capabilities; the presence of a requirement does not prove a feature is built. Remaining implementation is recorded in active change tasks: [Lab](openspec/changes/lab-workbench/tasks.md), [Workflows and media](openspec/changes/consolidate-product-contract/tasks.md), and [catalogue failure recovery](openspec/changes/startup-catalogue/tasks.md).

## Use the local product

On this prepared Windows checkout, double-click **Launch Workbench.vbs**. It starts the backend if needed and opens the built desktop. Closing and reopening the desktop retains conversations and project files; the backend and any running model remain available in the background.

1. Open **Models**, choose an installed model and its configuration, then load it. **Save changes** updates that configuration; **Save as configuration** creates another. Loading changes use **Apply & reload**. An already running model can be used directly.
2. Open **Chat**. Select a model and use its adjacent tuning control for thinking and context. **Apply** keeps an override for this model in this chat. During work, changes prepare the next message; its model loads at the safe handoff. Response limits and saved model defaults belong in **Models**.
3. Add an existing project from the Chat list for file tasks. **Ask** pauses before edits, shell commands, and other effects unless a saved permission applies; **Full access** permits enabled tools. **Plan** remains read-only at either access level. Save tools, helpers and review criteria in **Agents**.
4. Use **+**, **@** or **/** for context, saved skills and task prompts. Each accepted message freezes the latest saved instructions and knowledge; later edits cannot change work already accepted. **Knowledge** provides guided skill fields, native Source editing and supporting files saved together as one version.
5. Use **Stop** to cancel active work. Queued messages follow a successful turn, and pause after cancellation or failure. Choose a saved conversation from the left to continue; visiting another destination retains its draft and reading position. Unload the model from **Models** when you want to release its memory.

## Install and run

Requirements: Python 3.12.x with [uv](https://docs.astral.sh/uv/); Node.js 22–24 with pnpm 10+. Windows is the supported target; the real-model smoke tier also supports Linux. Validation runs locally; GitHub CI is disabled. Agent validation commands are maintained in [AGENTS.md](AGENTS.md).

Backend setup, from `apps/backend`: `uv sync`, then `uv run python -m workbench_backend`.

Desktop setup, from `apps/desktop`: `pnpm install`, then `pnpm run build`. The double-click launcher uses that build; rebuild after code changes. `pnpm run dev` is the development mode. Launcher errors and backend startup logs live under the product `logs` directory.

## Where data lives

Product data—models, runtimes, state, cases, snapshots, knowledge and the SQLite databases—lives under `%LOCALAPPDATA%\LocalAIWorkbench\`. Throwaway files belong only under `.scratch/` at the repository root, which Git ignores. Model weights and secrets are never committed.

## Entry points

| Need | Open |
| --- | --- |
| Agent working rules | [AGENTS.md](AGENTS.md) |
| LangChain framework references for development agents | [Local upstream references](.agents/references/langchain/README.md) |
| Current product contracts | [OpenSpec capabilities](openspec/specs/) |
| Proposed and active changes | [OpenSpec changes](openspec/changes/) |
| Current delivery snapshot | [HANDOVER.md](HANDOVER.md) |
