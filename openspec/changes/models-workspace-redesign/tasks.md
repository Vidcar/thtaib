# Tasks

## 1. Import and cleanup contracts

- [x] 1.1 Separate obvious MTP auxiliary GGUF files in repository inspection and primary-selection validation; verify mixed, split and auxiliary selection tests.
- [x] 1.2 Make terminal discard delete its job record after safe cleanup, including old discarded jobs, while rejecting active/complete work; verify ownership and shared-staging tests.
- [x] 1.3 Regenerate the shared API contract and verify its freshness check passes.

## 2. Models workspace

- [x] 2.1 Build My models, Add models and Downloads tabs with shared import progress, preserved search state and completion refresh; verify tab behavior in the desktop.
- [x] 2.2 Replace the variant select with an accessible grouped table, quantization hints, bit filters, size sorting and explicit projector choice; verify unknown and narrow-layout states.
- [x] 2.3 Expose the requested model controls in a responsive editor with effective sources, saved/loaded distinction and existing safe actions; verify configuration persistence and reload behavior.
- [x] 2.4 Redesign Downloads rows and storage placement; verify long names, legacy discarded cleanup and retained shared files.

## 3. Delivery

- [x] 3.1 Run desktop, backend, integration, contract and OpenSpec checks; fix failures and verify the change strictly.
- [x] 3.2 Validate the Windows UI, isolated download and real model settings flow; clear the three old discarded records safely and update the everyday deployment.
- [ ] 3.3 Refresh the handover, review the diff, commit, push and deliver the change through the repository's Git workflow.
