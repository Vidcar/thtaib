# Local AI Workbench

Local AI Workbench is a Windows-first, local-first workbench for running models and agent work on your own machine. One FastAPI backend does the work; one Electron desktop shows it. Inference comes from llama.cpp, the agent loop from Deep Agents, LangGraph and LangChain. The workbench integrates those projects behind a coherent user experience instead of reimplementing them.

## Use the local product

On this prepared Windows checkout, double-click **Launch Workbench.vbs**. It starts the backend if needed and opens the built desktop. Closing and reopening the desktop retains conversations and project files; the backend and any running model remain available in the background.

1. Open **Models**. Under **Start managed**, select the existing **Qwen3.8-27B-UD-IQ4_XS** bundle and choose **Start**. If it is already running, use it without starting another copy. The first model check after backend startup can take time; no download is needed for an installed bundle and runtime.
2. Open **Chat**. The running model is selected automatically. Leave **Profile** at **None** for defaults, or choose a saved profile deliberately.
3. Send a message. For file tasks, enter an existing project folder first. The assistant can read and edit files there. Shell commands that need approval show the exact command with **Approve** and **Deny**.
4. Use **Cancel** to stop work, and choose a saved conversation from the left to continue. Recent conversations appear first. Stop the model from **Models** when you want to release its GPU memory.

The current next-work list is in [the delivery map](docs/delivery-feature-map.md#next-path). Detailed requirement status and scoped evidence live only in [the catalogue](specs/catalog.json); [verification](specs/verification.md) distinguishes live checks from mocks and unfinished acceptance clauses. Builder, optional MCP integration and broader Lab workflows are not prerequisites for Chat.

## Coding agents

Start at [AGENTS.md](AGENTS.md). Specifications live under [`specs/`](specs/README.md).

## Install and run

Requirements: Python 3.12.x with [uv](https://docs.astral.sh/uv/); Node.js ≥22 and <25 with pnpm 10+. Windows is the supported target; Linux is used for CI and the real-model smoke tier. All commands are listed in [commands](specs/commands.md).

Agent setup: backend (in `apps/backend`): `uv sync`, then `uv run python -m workbench_backend`.

Desktop (in `apps/desktop`): `pnpm install`, then `pnpm run build`. The double-click launcher uses that build; rebuild after code changes. `pnpm run dev` is the agent development mode. Launcher errors and backend startup logs live under the product `logs` directory.

## Where data lives

Product data — models, runtimes, state, cases, snapshots, knowledge, the two SQLite databases — lives under `%LOCALAPPDATA%\LocalAIWorkbench\`. Throwaway files belong only under `.scratch/` at the repository root, which git ignores. Model weights and secrets are never committed.

## Entry points

| Need | Open |
| --- | --- |
| Agent working rules | [AGENTS.md](AGENTS.md) |
| Index and working rules | [specs/README.md](specs/README.md) |
| Architecture | [specs/architecture.md](specs/architecture.md) |
| Status and evidence | [specs/catalog.json](specs/catalog.json) |
| Commands | [specs/commands.md](specs/commands.md) |
| Decisions | [specs/decisions/](specs/decisions/README.md) |
| Open questions | [specs/open-questions.md](specs/open-questions.md) |
| Glossary | [docs/glossary.md](docs/glossary.md) |
| Delivery plan | [docs/delivery-feature-map.md](docs/delivery-feature-map.md) |
| Original vision (Revision 0.5) | [specs/sources/README.md](specs/sources/README.md) |
