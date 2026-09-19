# Local AI Workbench

Local AI Workbench is a Windows-first, local-first workbench for running models and agent work on your machine. One FastAPI backend coordinates the product; one Electron desktop presents it. llama.cpp owns supported inference. Deep Agents, LangGraph and LangChain stay behind application boundaries — the workbench owns configuration, lifecycle, visibility and connecting contracts, not a second implementation of those loops.

## Coding agents

Coding agents start at [AGENTS.md](AGENTS.md).

## Requirements

- Python 3.12.x and [uv](https://docs.astral.sh/uv/) (uv can install 3.12)
- Node.js ≥22 and <25 (develop on 24) and pnpm 10+
- Windows is the supported target; Linux/macOS are used for smoke

## Install and run

Use only the commands recorded in [commands](specs/commands.md). Application commands name their working directory.

### Backend

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS for smoke. **Prerequisites:** [uv](https://docs.astral.sh/uv/) and Python 3.12.x (uv can install 3.12).

```text
uv sync
```

```text
uv run python -m workbench_backend
```

### Desktop

**Working directory:** `apps/desktop`. **Platform:** Windows (supported target); also runs on Linux/macOS for install/type-check/build. **Prerequisites:** Node.js ≥22 and <25 (develop on 24) and pnpm 10+.

```text
pnpm install
```

```text
pnpm run dev
```

Type-check and build from the same directory after `pnpm install`:

```text
pnpm run typecheck
```

```text
pnpm run build
```

`pnpm run dev` needs a machine that can open an Electron window (David-PC for UAT). See [commands](specs/commands.md) for what each command does.

## Durable data

Durable product and managed-inference data stays under `%LOCALAPPDATA%\LocalAIWorkbench\`. Throwaway UAT and temp files belong only under `.scratch/` at the repository root (the entire tree is gitignored).

## What exists and what does not

Present today: the model manager, the embedded Deep Agents harness, debug-quality Chat, Lab capture/restore/rerun, and durable knowledge versioning. The desktop exposes Models, Deployments and Chat. Optional Agent-run, Lab and Knowledge debug panels remain for raw debug. Chat is not finished polish. Builder is not shipped.

## Specification pack

The [specification index](specs/README.md) is the behavioural home. To check pack integrity, use [commands](specs/commands.md#spec-integrity). [Repository setup](specs/repository-setup.md) covers adoption and protections.

## Entry points

| Need | Open |
| --- | --- |
| Agent working rules | [AGENTS.md](AGENTS.md) |
| Specification index | [specs/README.md](specs/README.md) |
| Commands | [specs/commands.md](specs/commands.md) |
| Glossary | [docs/glossary.md](docs/glossary.md) |
| Open questions | [specs/open-questions.md](specs/open-questions.md) |
