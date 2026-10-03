# Proposal

## Why

The supplied 20-second animation prompt produced its HTML successfully, but Workbench aborted the first browser navigation and then reported a lost session. Isolated native reproduction confirms that concurrent observation reads incomplete Chrome startup state and the backend closes a healthy owned browser.

## What Changes

- Make the first Chrome launch safe to observe concurrently, retaining one owned context and the existing no-replay recovery boundary.
- Correct recovery guidance where Close/start can preserve the conversation profile; Reset remains the explicit profile-clearing operation.
- Deliver each browser handoff observation once through native checkpointed context, clearly marking its origin and any newer browser result; preserve the real user-turn boundary and reasoning replay.
- Align discovery with advertised labels and common browser actions, while retaining accepted-tool authority, bounded schema loading and one copy of each returned description.
- Refine built-in question guidance to use sensible defaults and ask only for essential missing information. Preserve authored instructions and ordinary answer/result message handling.
- Preserve the native browser MCP content/artifact split so absent or separate artifact data is not fabricated as response text.
- Supply the actual host operating system in initial accepted context, consistently with preview and helper composition, rather than withholding it until shell-schema discovery.
- Clear an obsolete generic unhealthy-model banner when the same bound deployment's current catalogue confirms healthy running state, retaining real binding and readiness errors.
- Exercise all six supplied prompts verbatim through the available Qwen and production harness with Full access, appropriate tools and helpers. Independently inspect outputs and distinguish application defects, model mistakes and missing inputs.
- Fix any further supported application defects from those journeys, with focused regressions and reviewed local delivery.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `environments-tools`: clarify ENV-030's first-launch observation and non-destructive lost-session recovery scenarios.
- `agents-workflows`: clarify AGT-001's handoff context timing and AGT-005's discoverable label contract.

## Impact

Browser worker/startup, browser lifecycle/recovery, native model middleware/checkpoint state, tool metadata/disclosure and focused regressions. The existing backend, MCP adapter, Deep Agents loop, permissions and persistent profile remain the owners. No new dependency, scheduler, replay mechanism, model limit or public wire-shape change is planned. Live test data and prompts/results remain under ignored `.scratch/prompt-uats/`; model weights and original setups remain intact.
