# Design

## Context

See [proposal.md](proposal.md). The current backend launches one managed `llama-server -m` process per deployment and Chat warms a preferred stopped deployment when its panel mounts. Setup resolution mixes app, project, agent and conversation overrides; a saved desktop-access choice can outlive its in-memory grant. The pinned Windows CUDA binary reports llama.cpp build 11045 and supports `--models-preset`, `--models-max` and model-specific router requests. Deep Agents already compiles named helpers and native child stream namespaces.

## Goals / Non-Goals

**Goals:** One authority for each setting; truthful preview and dispatch; owned managed-model residency with one- or two-model use; no model load at app launch; Deep Agents helper work and access preserved across chat restoration.

**Non-Goals:** A second agent loop, custom model eviction scheduler, automatic model recommendations, startup preloading, migrating disposable development chats or model setups, or controlling connected endpoints' residency.

## Decisions

1. **Configuration ownership.** Model configurations contain only launch and request inference settings. Agent definitions own instructions, review and named helpers; a helper can carry a model configuration override. Projects provide folder and selected knowledge. Conversations own main model, main agent, work/Plan, Ask/Full and capability groups. The app owns the new-chat access preference (factory Ask) and managed loaded-model limit (factory one). A backend resolver provides the effective values and readiness used by both UI and admission. Known incompatibility disables an action; unverified capabilities stay available with an honest label.
2. **Pinned router integration.** Start one owned router without `-m`, with a generated preset section per exact model configuration and `--models-max` from saved app policy. Generated presets are derived runtime files, never a second settings store. Isolate the router's cache view to Workbench-owned bundles. Each request carries the preset ID; `/props` includes that ID and passive probes suppress autoload. Use bounded `/models` polling during loads and passive status reads to distinguish pending, loaded and failed states. Router idle eviction and queueing remain upstream. Workbench coordinates explicit configuration edits, ownership, access and run admission.
3. **Cold launch and selection.** Remove Chat's mount-time warm effect and any preset startup loading. Restoring or browsing chats only reads status. An explicit model choice stages a pending selection and invokes load; readiness commits the chat binding, and failure leaves the prior binding. A first Send with an unloaded restored selection invokes load and then sends once. At capacity one, an active inference request finishes before another instance loads. An alternate-model helper can use the one slot between the parent's calls; the parent reloads before resuming. A limit of two keeps Gemma and Qwen resident when memory allows. Per-model `--parallel` remains separate.
4. **Access and presentation.** A conversation-aware preview includes current Windows grant, selected window identity, worker availability, model readiness and compatibility; dispatch repeats the check. `+` groups optional capabilities, while a separate shield selects Ask or Full. Plan is a removable pill and backend-enforced mode. Main agent and model are adjacent selectors. Child activity is projected from Deep Agents namespaces into an expandable rail, with approvals/questions still reachable in Chat.
5. **Cutover.** Safely stop any old owned per-model process through the existing owner before installing the router lifecycle. Reconcile old deployment records as stopped, never claim an unknown PID, and discard obsolete app chats, projects, agent setups and model configurations instead of reading legacy setup shapes. Rebuild default configurations for installed bundles and set Dave's limit to two. Preserve GGUFs, companion files, verified bundle identities and external project files. Keep unrelated product data unless it is an incompatible app record.

## Risks / Trade-offs

- **Two models may not fit a chosen context/GPU setup** → validate both installed models with real generation, save tested configurations when needed, and show an actual launch failure without silent fallback.
- **Router state can lag a successful load request** → wait for model-specific loaded status and properties before committing a chat selection.
- **A preset edit can unload a busy instance** → gate preset regeneration/reload with current consumers and expected revisions; preserve an immutable launch snapshot until safe.
- **A grant expires after preview** → repeat authorization at dispatch and the tool boundary; never use a preview as permission.
- **Old process identity differs from router identity** → stop through the old safe path before cutover, then reconcile rather than killing by guessed PID.

## Migration Plan

Validate on an isolated product-data root using the installed weights by path. Before updating the established local installation, confirm and safely stop old owned managed processes. Apply the intentional development-data reset for incompatible app records while retaining model files and external folders. Install and verify the router-backed build, save Dave's two-model limit, and exercise Gemma/Qwen in Chat and as helpers. If validation fails, leave the previous usable build and model files in place and report the failing step.
