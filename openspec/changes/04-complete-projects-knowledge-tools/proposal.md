# Complete projects, knowledge and external tools

## Why

Projects, reusable agents and external tools need one scoped configuration and persistence path that works in ordinary continued conversations.

## What Changes

Complete project/setup management, composed instructions, reviewable file and memory changes, full skill packages, local document extraction, optional retrieval, public web tools and real MCP execution on the shared async driver.

## Capabilities

### Modified Capabilities

- `agents-workflows`: Resolve reusable agent setups and refresh selected knowledge without replacing threads.
- `state-recovery`: Extend versioned knowledge, projects, documents, skills and derived retrieval.
- `environments-tools`: Complete shared tool/connection lifecycle, web access, MCP and async ownership.

## Impact

Work order **04 of 08**. Changes 03 and `migrate-local-agent-interaction` must be implemented and verified first. Consume the verified shared `@langchain/react` interaction/presentation boundary for messages, tools and scoped run observation; keep configuration, connection and selection controls in the existing application-owned shared views. This change owns the full common async harness/saver/middleware/resume/cancel/recovery transition. Only move that complete foundation into the prerequisite if its compatibility proof establishes that the public synchronous `stream_events` path cannot support the verified SDK interaction; never create competing drivers or split lifecycle ownership. SDK integration does not complete the project, knowledge, tool or MCP tasks below. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No second knowledge store or agent loop; no required OCR, isolated worker platform, relevant-tool selector, interpreter, MCP Apps or background memory consolidation. Such extensions remain optional and must not weaken existing policy.
