# Proposal

## Why

The current Lab contract describes screens that were never built, and it disagrees with how models load today. It still requires llama-bench, a second copy of the model, and an exclusive hold on the machine, while the app can keep more than one model loaded and already records prefill and generation timings from llama-server. Lab needs a contract that matches that loader, split so Performance, Memory, and Challenges can be built one at a time.

## What Changes

- Add a Lab destination back to the sidebar. Performance opens first, then Memory, then Challenges.
- Specify Performance as two benchmark modes, Single stream and Concurrent serving, with prefill and generation charts drawn from the loaded server's timings.
- Specify Memory as three exact needle tests at five context depths.
- Specify Challenges as a list a person can add to, checked by required answer text and an optional echo or time_now call.
- Keep benchmark settings and results on this computer. A benchmark does not write model configuration or the saved loaded-model limit.
- **BREAKING** for the current Lab screen contract: remove the llama-bench measurement requirements, the exclusive machine hold, and the older three-screen wording from `lab-evaluation`. Case capture, recorded replay, and restore stay in that capability for the older screen.

## Capabilities

### New Capabilities

- `lab`: Sidebar destination, unsaved benchmark configuration, local results, and stop, failure, and delete behaviour shared by the other Lab specs.
- `lab-speed`: Performance. Single stream and Concurrent serving, legal model controls, prompt lengths, generation length, and the prefill and generation charts.
- `lab-memory`: Single UUID, multi-key, and multi-value needle tests, scored by exact text at five depths.
- `lab-challenges`: A growing challenge list, an included echo challenge, and checks that can require answer text, echo, or time_now.

### Modified Capabilities

- `lab-evaluation`: Remove the screen, llama-bench, and exclusive-hold requirements that the new capabilities replace. Keep case capture, recorded replay, and restore for the older screen.

## Delivery State

Reviewed 2026-09-27: this is a complete plan with no implementation tasks finished. The existing case-capture/replay panel and engine smoke command do not satisfy these new views. This change is the sole Lab implementation owner; the former consolidation Lab tasks/delta were retired. Models loading choices, server timings and the application database are reuse points, not completed Lab acceptance.

## Impact

Desktop Lab navigation and three views. Backend benchmark runs reuse the existing llama-server loader, configuration choices, and request timings. Results live under the local application data root. llama-bench is not the measurement path. Workflows, image generation, speech, and challenge-specific tools are out of scope.
