# Tasks

## 1. Managed model runtime

- [x] 1.1 Add the positive managed loaded-model limit and generated router presets with zero startup loads; verify policy/preset tests and a cold launch.
- [x] 1.2 Replace managed per-model load/status handling with exact router load, queue, eviction and recovery observations; verify one- and two-slot lifecycle tests without touching connected endpoints.
- [x] 1.3 Route generation and properties by exact configuration ID and preserve loaded-versus-saved settings; verify adapter tests, helper requests and model-specific probes.

## 2. Setup and agent admission

- [x] 2.1 Make model, agent, project, conversation and app setting owners explicit in backend resolution and conversation records; verify project and agent changes cannot silently change Chat's model or access.
- [x] 2.2 Add conversation-aware capability/readiness preflight with live Windows grants and repeat it at dispatch and tool boundaries; verify reopened-chat and stale-window tests avoid the predictable 409.
- [x] 2.3 Enable alternate-model Deep Agents helper loading and one-slot handoff without interrupting an in-flight call; verify parent/helper and separate-chat concurrency tests.

## 3. Desktop experience

- [x] 3.1 Remove automatic model warming and show explicit selection, pending load and first-Send load states; verify desktop tests and a cold app launch.
- [x] 3.2 Put separate model and agent selectors, supported thinking, Plan pill, Ask/Full and capability groups at the composer; verify keyboard and narrow-window use in the desktop build.
- [x] 3.3 Put named helper work in an expandable rail and remove unfinished Lab/Workflows from primary navigation while retaining routes and Attention; verify activity and navigation tests.
- [x] 3.4 Show the managed loaded-model limit and selected/loaded configuration truth in Models; verify limit one/two and failed selection states in the desktop build.

## 4. Cutover and validation

- [x] 4.1 Retire incompatible development setup records without compatibility shims, preserving weights and external project files; verify bundle integrity and safe old-process cutover.
- [x] 4.2 Run backend default and integration suites, desktop build, generated-contract freshness, OpenSpec validation and diff check; repair confirmed failures.
- [x] 4.3 In an isolated Windows data root, run both installed Gemma 4 E2B and Qwen 3.5 4B together, separate chats and a different-model helper; verify actual generations and truthful memory/failure reporting.
- [x] 4.4 Update the established local installation, save Dave's limit of two, refresh the handover, archive the completed change and deliver through Git/PR; verify the usable build and clean branch state.
