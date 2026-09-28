# Design

## Context

The approved discovery decisions govern ownership and behaviour. The previous compact shell delivery left saved-record editors and several cross-surface controls incomplete. Existing backend resolution already supplies values, provenance, parent defaults, template defaults and exact deployment selection. Use those facts; HTML and generated images are visual guides only.

## Goals / Non-Goals

Complete Chat, Models, Agents, Knowledge and Library presentation and the identified control regressions. Preserve model defaults, Chat thinking/context tuning, agent tools/knowledge, immutable accepted-message settings, revision guards and safe reload. Preserve native skill source/resources and retained-file identity. No new runtime, public endpoint, dependencies or storage authority; Lab/Workflows feature development remains separate.

## Decisions

- Shared controls render the effective value without writing it into requested settings. Parent configuration and underlying model defaults remain separate reset targets. Unknown values remain unknown; only genuine engine-selected modes say Automatic.
- Models previews use the existing conversation resolution boundary with no project/agent selection so model/configuration/draft input participates. Application defaults remain approval/access only. Unsaved source labels are presentation changes only.
- Use one shared searchable catalogue/detail frame with an accessible narrow selector. Keep visited saved-record editors mounted in the shell, hidden while inactive, to retain local draft state; pause active-only polling where needed. Record repair navigation uses an optional id/request token.
- Chat consumes resolver-selected deployment identity for readiness. Tuning preview and Apply share one candidate; preview races cannot validate a newer draft with an older result, and editing stays available during checking.
- One preferred dock width is seeded from Files. Displayed width is independently clamped to current space; browser viewport resolution remains backend-owned. Conversation view state retains local filters, folders, selected helpers and reading position; hidden Browser stops frame viewing while retaining its owned session.
- Knowledge keeps operational policy/capture controls in compact secondary disclosures. Independent catalogue/settings/proposal loads fail independently. Capture partial updates merge only provided fields inside the existing service lock; explicit null retains its clearing meaning.
- Library selects exactly one All/Project/Chat scope through existing APIs, resolves recognizable names independently, and removes only its global reuse handoff. Chat retained-file/context/attachment reuse stays in scope.

## Risks / Trade-offs

- Keeping visited editors mounted consumes modest local state: only saved-record workspaces are retained, hidden surfaces suspend active work and preserve current backend ownership.
- Effective values can be stale during a draft request: keep editing available, distinguish checking/error state, and gate Apply/Save on the matching validated candidate.
- Estimates may be incomplete: retain unknown components/device boundaries, never block valid selections or reduce requested settings, and bypass caching only for a manual Refresh request.
- Existing tests encode some old labels/layouts: replace those assertions with meaningful value, behaviour and ownership checks without weakening lifecycle/permission coverage.

## Delivery

Verify focused resolver, capture, draft, picker, dock, import and retained-file regressions; then run backend default/integration, desktop build/regressions, generated-contract freshness, OpenSpec and whitespace gates. Inspect the Windows product with isolated test data at full/half width and both themes/scales. Sync/archive the completed follow-up, update the concise handover, and complete established Git/local delivery.
