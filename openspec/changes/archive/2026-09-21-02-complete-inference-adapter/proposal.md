# Complete the shared llama-server adapter

## Why

Every agent surface needs the same faithful request, response, context and capability boundary before higher-level features are added.

## What Changes

Complete request serialization, sync/async streaming, tool/reasoning conversion, structured results, context preflight and setup-specific probes.

## Capabilities

### Modified Capabilities

- `models`: Extend the existing deployment-to-LangChain adapter without moving inference lifecycle into it.

## Impact

Work order **02 of 08**. Change 01 must be implemented and verified first. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No new inference engine, second agent/compaction loop, full media UI, cloud fallback or full MCP driver migration.
