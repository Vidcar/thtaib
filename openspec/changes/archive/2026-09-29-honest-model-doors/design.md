# Design

## Context

See proposal.md for why the labels and routes disagree. Managed start, deployment start, and deployment reload are already three backend operations. The desktop currently funnels Load, chat model choice, chat tuning, and main-agent changes through one client method that can also invent a GPU startup object when the caller omits one.

## Goals / Non-Goals

**Goals:**

- One desktop method for loading a saved setup, and one desktop method for applying a chat's startup overrides. Both post managed start and require an explicit startup object.
- Models shows Load or Load saved, and a separate Reload only for the reload route.
- Chat tuning says what it does. Chat, Lab, and Agent run share the override method because they share the tuning control. Main-agent selection uses that same method.
- Remove desktop client methods that no screen calls and that duplicate a deployment or profile operation.

**Non-Goals:**

- Changing backend routes, llama.cpp, or Deep Agents.
- Collapsing setup resolution flags, folder-busy errors, or the stopped-record prepare path.
- Silent-catch cleanup, god-component moves, local import, quant labels, or the Thinking retest.
- Deleting other unused client methods that are not deployment or profile twins. Those stay recorded for a later slice: paths, recipe configuration creation, model configuration listing, agent-run and chat interrupt decisions, chat start, transcript replace, workspace listing, lab cases, and knowledge create/edit/remove.

## Decisions

1. **Two named client methods, one private post.** `loadSavedModelSetup(bundleId, profileId)` sends `startup: {}` and `auto_start: true`. `applyChatStartupOverrides(bundleId, profileId, startup)` sends that startup object and `auto_start: true`. A private poster always receives the startup object, so a missing argument cannot fall back to a GPU default. Delete `DEFAULT_GPU_STARTUP` with the old starter. Callers keep their own gates: model choice and main-agent selection skip a healthy running match; tuning always applies when the chat is idle because context changes the startup identity.

2. **Reload is a second Models control.** It renders when the selected setup has a managed deployment that is not failed. It calls the existing reload client method. Its title says it stops that record, restores a failed settings change, and starts the same record. Load stays on managed start and is labelled Load, or Load saved when the form is dirty. Both can be visible together. Load snapshot stays on deployment start.

3. **Chat label.** Idle tuning says "Apply this chat's settings". A running reply or queue still says "Stage for next message" and does not start a model. Help text matches. Send stays Send. Admission on send continues to use the backend managed-start function. The desktop does not add a second start before send.

4. **Screen binding test.** A desktop script renders the Models lifecycle controls and the chat tuning control, clicks them, and asserts method and path: Load and Load saved post managed start with the saved profile and `startup: {}`; Reload posts `/v1/deployments/{id}/reload`; Load snapshot posts `/v1/deployments/{id}/start`; Apply this chat's settings posts managed start with that chat's startup overrides; Save posts the bundle configuration route and not managed start. A mocked failed load still surfaces the error. Existing checks that clicked Reload and expected managed start are updated to the new labels. They keep the assertion that the click hit the claimed route.

## Risks / Trade-offs

- [Reload stops a live model and can take as long as a start] → The control is explicit, disabled while another Models action is busy, and shows the backend error, including a refusal while a run still holds the model.
- [Load stays disabled while the selected managed deployment is not healthy] → That matches today's start gate. Reload remains available for that record.
- [A refresh after a failed start can still hide the start error if refresh itself throws] → Left for the failure-visibility slice. This slice does not change that sequence.

## Migration Plan

Desktop-only. Rebuild the desktop and reload the existing window. No product-data migration. Rollback is reverting the desktop client and the two labels.

## Open Questions

None.
