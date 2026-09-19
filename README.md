# Local AI Workbench

Local AI Workbench is a Windows-first, local-first workbench for running models and agent work on your own machine. One FastAPI backend does the work; one Electron desktop shows it. Inference comes from llama.cpp, the agent loop from Deep Agents, LangGraph and LangChain. The workbench integrates those projects behind a coherent user experience instead of reimplementing them.

## Where things stand

Seen working live on David's PC (2026-09-19, Qwen3.8-27B on an RTX 3090): the backend downloads the pinned llama.cpp build, starts `llama-server` itself, reports it healthy and stops it cleanly; Chat sends a task to the agent, the agent writes a real file into the project folder and a follow-up turn continues the same conversation; a saved profile's settings reach the model. A real-model smoke test with a tiny model now runs on every pull request. Built but not yet proven live: Hugging Face import, companion files for vision, Lab capture and replay, durable knowledge. Not started: workers (shell, browser), Builder, Model Lab runners, approvals, retrieval.

The honest status of every requirement is in [the catalogue](specs/catalog.json); what "built" and "verified" mean is in [verification](specs/verification.md).

## Coding agents

Start at [AGENTS.md](AGENTS.md). Specifications live under [`specs/`](specs/README.md).

## Install and run

Requirements: Python 3.12.x with [uv](https://docs.astral.sh/uv/); Node.js ≥22 and <25 with pnpm 10+. Windows is the supported target; Linux is used for CI and the real-model smoke tier. All commands are listed in [commands](specs/commands.md).

Backend (in `apps/backend`): `uv sync`, then `uv run python -m workbench_backend`.

Desktop (in `apps/desktop`): `pnpm install`, then `pnpm run dev` (needs a machine that can open a window). `pnpm run typecheck` and `pnpm run build` check and build it.

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
