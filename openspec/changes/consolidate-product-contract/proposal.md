# Proposal

## Why

The current specs describe the dock, the editors, and the live activity lines. The older plans still describe Lab, helpers, Workflows, and media, plus everyday workspace rules that never landed in the current contract. Those plans also treat the screens as a thin layer over the behaviour. Each of these areas needs a finished, calm screen, specified with the behaviour.

## What Changes

- Bring the surviving older behaviour into the current capability specs, in this order: everyday workspace, Lab, named helpers and model swapping, the Workflows canvas, then the three media plugs.
- Specify the screens in enough detail that a later implementation can be judged by what a person sees, not only by an API.
- Lab measures prefill and decode first, with configurable settings, charts, and saved comparisons. A needle test and a small expandable set of exact challenges sit beside that, on their own screens. Lab has the machine while it runs.
- A chat helper exists only when named. A workflow step can call an agent or another workflow. Both are off until configured.
- Image generation, dictation, and spoken replies are plugs to engines the person configures. Later voice and image features stay possible.
- **BREAKING** for the old Lab text: task challenges no longer require the Inspect product. Exact checks through the shared agent replace that requirement.
- Remove the old open plan folders once this text is in the current specs. Archived history stays.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `lab-evaluation`: Measurement-first Lab, configurable needle test, small exact challenges, and the screens for each.
- `agents-workflows`: Named helpers, and a Workflows canvas whose steps match what actually runs.
- `backend-desktop`: Compact screens, visible Lab reservation, helper and model-swap confirmation, and child activity a person can read.
- `environments-tools`: Web search, connection secrets, ComfyUI image generation, and configured speech plugs, with composer controls.
- `state-recovery`: Immediate archive, chat deletion that leaves project files, skill packages, and document extraction without a source-inspection screen.
- `architecture`: Later features extend the same plugs and are not banned.

## Impact

Specification only. No application code. Desktop presentation for Lab, Workflows, Chat helpers, and the composer. llama-bench remains the speed runner. ComfyUI and speech engines stay outside the app. Old change folders `04` through `08`, `compact-workbench-experience`, and `familiar-chat-sidebar` are removed after the sync.
