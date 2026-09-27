# Proposal

## Why

Chat currently rejects authorized project reads whenever knowledge search adds a retrieved-evidence route. The model can list valid files but receives a misleading framework-only restriction when it reads them.

## What Changes

- Keep selected file reading available alongside knowledge search.
- Limit the automatically supplied reader to saved results, conversation history and selected retrieved evidence.
- Align the model-facing reader description with its effective permissions.
- Verify access boundaries and two successive real-model Chat turns.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environments-tools`: clarify coexistence of selected file reading and restricted result reading under ENV-020.

## Impact

Backend harness assembly, middleware authorization and existing reader/retrieval tests. No public API, schema, dependency, UI or model-setting changes. Delivery includes an idle backend refresh with existing model processes and settings preserved.
