# Proposal

## Why

Workbench agents can read project images through Deep Agents, but the application does not reliably deliver tool images to the selected vision model or offer owned browser and Windows test surfaces. People need to let an agent inspect the interface it is building, including local sites and selected desktop windows, while keeping access, evidence and recovery truthful.

## What Changes

- Complete bounded image reading through the native `read_file` tool and the existing model adapter.
- Add optional, owned Playwright MCP browser sessions and project preview processes for Chat and project Chat.
- Add optional Windows window inspection, interaction and capture with configurable Off, Selected window and All windows access.
- Retain captures as scoped assets, make them readable through the existing file tool, and show them in Chat and Library.
- Apply existing setup, approval, helper inheritance, cancellation and recovery rules to these capabilities.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environments-tools`: browser, preview and Windows adapters, access modes and action policy.
- `agents-workflows`: shared Chat harness, tool image reading and inherited authority.
- `models`: truthful selected-deployment vision support and model-boundary image delivery.
- `state-recovery`: retained capture provenance, session lifecycle and restart behavior.
- `backend-desktop`: compact setup controls and capture presentation.

## Impact

FastAPI tool integration and worker lifecycle, the llama.cpp LangChain adapter, retained assets and shared setup contracts, Electron Chat and Library views, optional pinned Playwright MCP and WinApp CLI workers, and Windows live validation. Core Chat remains usable when optional workers are absent.
