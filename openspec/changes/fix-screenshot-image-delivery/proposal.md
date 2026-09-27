# Proposal

## Why

The first screenshot on an untested vision setup exposes internal red/blue capability-test replies in Chat. Although those tests pass and the correct screenshot is retained, the active agent's stale model profile causes upstream media filtering to replace the real image with an unsupported-content notice.

## What Changes

- Keep internal capability-probe reasoning, answers and synthetic tool calls out of the user-facing Chat stream while retaining probe evidence.
- Apply the current setup's verified image capabilities to the active model before the same screenshot's next model request is filtered.
- Preserve failed/inconclusive checks, tool-call pairing, selected request settings, retained captures and ordinary agent streaming.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: clarify that automatic vision checks remain internal and that a successful check enables screenshot delivery in the active request.

## Impact

Backend capability probes, inference model-profile resolution, the existing Deep Agents harness and focused regression tests. Reuse pinned LangGraph stream suppression and Deep Agents media filtering; no dependency, wire-schema or desktop changes are planned.
