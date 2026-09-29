# Tasks

## 1. Desktop doors

- [x] 1.1 Replace the shared starter with loadSavedModelSetup and applyChatStartupOverrides, delete the unused deployment and profile client twins, and verify no screen still calls the removed methods.
- [x] 1.2 Label Models Load and Load saved for managed start, add Reload for the reload route, label idle chat tuning Apply this chat's settings, and verify the three call sites use the shared override helper.

## 2. Binding checks

- [x] 2.1 Add a screen-to-endpoint check and update the existing Reload assertions, then verify `pnpm run build` from apps/desktop passes.
- [x] 2.2 Validate the change with `openspec validate --all` from the repository root.
