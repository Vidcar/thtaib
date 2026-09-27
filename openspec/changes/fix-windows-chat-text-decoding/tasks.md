# Tasks

## 1. Startup and native decoding

- [x] 1.1 Enable UTF-8 shortcut and guarded shared-entrypoint bootstrap; verify both real entrypoints, forwarded arguments/environment/exit status and Restart/Quit.
- [x] 1.2 Preserve Windows host-command locale decoding; verify captured non-ASCII output under UTF-8 mode.
- [x] 1.3 Cover native Unicode search across filesystem, host-shell and framework routes; verify exact matches, paths, caps and truncation using actual ripgrep.

## 2. Recoverable tool failures

- [x] 2.1 Convert only grep/read_file UnicodeDecodeError into identity-preserving errors; verify sync/async recovery with a successful sibling and retained results, plus negative tests for writes, cancellation and persistence failures.

## 3. Validation and delivery

- [x] 3.1 Pass backend default/integration suites, OpenSpec and whitespace checks; reproduce the original search and complete a real-model isolated agent Chat without changing model settings.
- [ ] 3.2 Sync contracts, prepare validated Git/PR delivery, refresh the established backend without replaying failed work, and update the handover with verified results; archive the completed change before merging.
