# thtaib — Local AI Workbench

A Windows-first desktop for running local models and working with AI. The current app includes Chat with project files, browser/preview tools and approvals; model import and configuration; saved agents, skills, memory and MCP connections; and a Lab for local trials. Existing Agent run and Builder screens remain available. Electron/React provides the desktop, FastAPI provides the local backend, llama.cpp runs models, and Deep Agents/LangGraph provides agent execution and checkpoints.

## Set up and launch

This repository currently provides a checkout-based development launch. Prerequisites are Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22–24 and pnpm 10 or newer; the desktop manifest pins pnpm 10.33.3. Keep the existing lockfiles.

From the repository root in PowerShell:

```powershell
uv sync --project apps/backend --locked
pnpm --dir apps/desktop install --frozen-lockfile
pnpm --dir apps/desktop run build
```

Double-click **Launch Workbench.vbs**. It uses `scripts/Launch-Workbench.ps1` to start or reuse the compatible backend at `127.0.0.1:8000` and open the built Electron desktop. Rebuild after desktop changes. For a launcher preflight:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Launch-Workbench.ps1 -CheckOnly -ShowConsole
```

The preflight can start the backend if needed. To run development processes separately, start the backend with `uv run --project apps/backend python -m workbench_backend`, then run `pnpm --dir apps/desktop run dev` in another terminal.

Open **Models** to import a GGUF or download a selected Hugging Face variant, save its configuration and load it. Choose the model in **Chat**. Add a project for file work, select enabled tools and use **Ask** for approvals or **Full access** for permitted effects. Conversations and drafts persist; **Stop** cancels active work. Closing the desktop can leave work running in the background; use the tray's Quit action for deliberate shutdown.

## Check changes locally

```powershell
uv run --project apps/backend python scripts/verify.py --plan
uv run --project apps/backend python scripts/verify.py --tier acceptance --scope shared
```

The second command runs backend default/integration tests, desktop checks/build and generated-contract freshness. Select smaller affected scopes for smaller changes: `docs`, `workflow`, `backend`, `desktop`, `shared`. `workflow` tests the verification runner. Omitting scopes runs all areas. Evidence goes in `.scratch/verification/`; remote CI is disabled. See [AGENTS.md](AGENTS.md) for focused checks and explicit real-model validation.

## Storage

Windows product data lives under `%LOCALAPPDATA%\LocalAIWorkbench\`: models, runtimes, state, workspaces, cases, snapshots, knowledge, logs, `application.sqlite` and `checkpoints.sqlite`. `WORKBENCH_DATA_ROOT` selects an alternate root; development tests use `.scratch/` in this checkout. On Linux the default is `$XDG_DATA_HOME/LocalAIWorkbench`, or `~/.local/share/LocalAIWorkbench`. Windows remains the desktop target. Launcher and backend logs are in the active data root's `logs/` directory. Keep model weights, credentials and user data out of Git.

## Find the implementation

| Area | Owner |
| --- | --- |
| Backend startup and local services | `apps/backend/src/workbench_backend/app.py` and `__main__.py` |
| Agent execution, Chat and streaming | Backend `agents/`, `chat/`, `interaction/`; desktop renderer `InteractionStream.tsx` |
| Models and native runtime | Backend `inference/`; desktop renderer `ModelsPanel.tsx` |
| Records, assets and knowledge | Backend `state/`, `assets/`, `knowledge/` |
| Desktop, editor and previews | `apps/desktop/src/main/` and `apps/desktop/src/renderer/` |
| Shared API contracts | [Generated contract guide](apps/backend/contracts/README.md); `scripts/generate_shared_contracts.py` |

[AGENTS.md](AGENTS.md) is the development entry point; [HANDOVER.md](HANDOVER.md) records current delivery state. The [Local AI Workbench Project](https://github.com/users/Vidcar/projects/5) and its [rebuild context/task issues](https://github.com/Vidcar/thtaib/issues/243) hold the plans, unresolved choices, agreements and delivery evidence. Original proposals are preserved there for separately authorized tasks. Dependency versions come from manifests, lockfiles and installed source; framework source pointers are in AGENTS. [Third-party notices](apps/desktop/THIRD_PARTY_NOTICES.md) cover adapted desktop code; retained framework licence notices are under `.agents/notices/`.
