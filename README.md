# Local AI Workbench

The Windows-first desktop for **thtaib**, a local-first AI workspace for using and understanding models, Chat, Lab and Workflows. **Agent run / Builder** are existing UI terms for Workflows; the desktop name remains Local AI Workbench. Current product contracts and future changes use [OpenSpec](openspec/).

## Use the local product

On this prepared Windows checkout, double-click **Launch Workbench.vbs**. It starts the backend if needed and opens the built desktop. Closing and reopening the desktop retains conversations and project files; the backend and any running model remain available in the background.

1. Open **Models**. Under **Start managed**, select the existing **Qwen3.8-27B-UD-IQ4_XS** bundle and choose **Start**. If it is already running, use it without starting another copy. The first model check after backend startup can take time; no download is needed for an installed bundle and runtime.
2. Open **Chat**. The running model is selected automatically. Leave **Profile** at **None** for defaults, or choose a saved profile deliberately.
3. Send a message. For file tasks, enter an existing project folder first. The assistant can read and edit files there. Shell commands that need approval show the exact command with **Approve** and **Deny**.
4. Use **Cancel** to stop work, and choose a saved conversation from the left to continue. Recent conversations appear first. Stop the model from **Models** when you want to release its GPU memory.

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
| Current product contracts | [OpenSpec capabilities](openspec/specs/) |
| Proposed and active changes | [OpenSpec changes](openspec/changes/) |
| Current delivery snapshot | [HANDOVER.md](HANDOVER.md) |
