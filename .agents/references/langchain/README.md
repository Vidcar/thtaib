# LangChain upstream references for Workbench development

These are local copies for **agents working on this repository**. They are not Workbench runtime skills, memories, model context, or product requirements. [AGENTS.md](../../../AGENTS.md) and [OpenSpec](../../../openspec/specs/) define local requirements; these upstream documents explain framework behavior. Check the locked package version and installed source before relying on an API detail.

Pinned-source refresh 2026-09-26; rendered Python guide snapshot remains 2026-09-24. `apps/backend/uv.lock` targets Deep Agents 0.7.19, LangChain 1.4.2, LangGraph 1.2.11, and `langchain-openai` 1.6.2. `apps/desktop/package.json` pins `@langchain/react` 1.1.1 and `@langchain/langgraph-sdk` 1.11.1. The Deep Agents architecture and threat model and the JavaScript documents below come from those **exact release tags**. The rendered Python guides were downloaded from the official docs site on the snapshot date and are **not versioned**. Check the lock and installed source before relying on a version-sensitive API detail.

### Deep Agents 0.7.15 to 0.7.19 integration notes

- **0.7.16**: `skills_metadata=None` requests a skill scan on the **next graph run**; `[]` means an already loaded empty skill set. Set it for a new user turn, including deselection, and leave a paused checkpoint untouched while resuming. The built-in filesystem middleware also rejects simultaneous edits to the same path within one assistant response. [Skills source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/middleware/skills.py).
- **0.7.17**: shell results preserve the backend's real exit status when capture metadata is absent; only supported MIME types are inlined as file blocks. [Changelog](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/CHANGELOG.md).
- **0.7.18**: large tool previews have explicit truncation notices, unknown `task` arguments are rejected, and file size reports UTF-8 bytes. [Changelog](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/CHANGELOG.md).
- `MemoryMiddleware` skips loading whenever the `memory_contents` state key exists, even if its value is `None`. Pass the exact selected version contents as the native map on each new turn, including `{}` on deselection; leave interrupt resumes unchanged. Do not expect changed file paths to refresh an already loaded checkpoint. [Memory source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/middleware/memory.py).
- Native HITL has a typed `respond` decision for a tool call within the same ordered interrupt batch as approve/reject. Preserve Workbench's answer validation and run/checkpoint identity. The one Deep Agents summarizer keeps its native trigger, retention, offload and retry mechanisms. Workbench supplies canonical outbound counting, the already-reserved input capacity, request-purpose attribution and terminal failure evidence; it must not subtract the output reservation twice. [LangChain HITL source](https://github.com/langchain-ai/langchain/blob/langchain==1.4.2/libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py), [summarization source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/middleware/summarization.py).

- **0.7.19**: rejected `read_file` media can recover, multimodal filtering is separate middleware, and large-tool offload paths are bounded. [Release](https://github.com/langchain-ai/deepagents/releases/tag/deepagents==0.7.19).
- Native `PatchToolCallsMiddleware.before_agent` closes unanswered valid and invalid tool-call identities with error messages; it does not replay tools or establish whether an external effect happened. Preserve independently settled sibling results and inspect uncertain effects before the next turn. [Pinned source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/middleware/patch_tool_calls.py).
- Native summarization recognizes `ContextOverflowError`, uses one configured token counter for trigger and reduction checks, and preserves offloaded history through the backend. Count the canonical outbound message representation; native reasoning blocks, replay metadata and tool-call representations can describe the same tokens. The adapter guard must run after native reduction and raise a recognizable overflow. Internal summary calls need separate purpose/usage attribution. [Pinned source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/middleware/summarization.py).
- Native filesystem edits normalize CRLF and bare CR in existing text and both replacement strings, then write UTF-8 without platform newline translation. File-effect evidence must use those same semantics. [Pinned source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/backends/filesystem.py).

## Deep Agents: harness, tools, and context

| Work area | Local copy | Upstream source |
| --- | --- | --- |
| Ownership layers, construction, middleware ordering | [Architecture](deepagents/ARCHITECTURE.md) | [0.7.19 source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/ARCHITECTURE.md) |
| SDK threat boundaries, untrusted tool output, host access | [Threat model](deepagents/THREAT_MODEL.md) | [0.7.19 source](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/THREAT_MODEL.md) |
| `create_deep_agent`, profiles, middleware | [Customization](deepagents/customization.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/customization.md) |
| Filesystem and shell backend routing | [Backends](deepagents/backends.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/backends.md) |
| Filesystem policy | [Permissions](deepagents/permissions.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/permissions.md) |
| `interrupt_on`, approval and resume | [Human in the loop](deepagents/human-in-the-loop.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop.md) |
| Memory files and injection timing | [Memory](deepagents/memory.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/memory.md) |
| Runtime skill loading | [Skills](deepagents/skills.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/skills.md) |
| Child agent configuration and inheritance | [Subagents](deepagents/subagents.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/subagents.md) |
| Summarization and context offloading | [Context engineering](deepagents/context-engineering.md) | [Official guide](https://docs.langchain.com/oss/python/deepagents/context-engineering.md) |

Start from Workbench's [`harness.py`](../../../apps/backend/src/workbench_backend/agents/harness.py), [`harness_backend.py`](../../../apps/backend/src/workbench_backend/agents/harness_backend.py), [`host_shell.py`](../../../apps/backend/src/workbench_backend/agents/host_shell.py), [`memory_skills.py`](../../../apps/backend/src/workbench_backend/agents/memory_skills.py), and [`context.py`](../../../apps/backend/src/workbench_backend/agents/context.py). For a disputed API detail, inspect the [tagged `create_deep_agent` implementation](https://github.com/langchain-ai/deepagents/blob/bb49cf50d3450a3bbebe8d25240cb7ef6379bd0d/libs/deepagents/deepagents/graph.py) or the installed package.

## LangGraph and LangChain: state, events, messages

| Work area | Local copy | Upstream source |
| --- | --- | --- |
| Thread IDs, saver lifecycle, checkpoint history | [Checkpointers](langgraph/checkpointers.md) | [Official guide](https://docs.langchain.com/oss/python/langgraph/checkpointers.md) |
| Pause and same-thread resume | [Interrupts](langgraph/interrupts.md) | [Official guide](https://docs.langchain.com/oss/python/langgraph/interrupts.md) |
| Native `stream_events` and event parts | [Event streaming](langgraph/event-streaming.md) | [Official guide](https://docs.langchain.com/oss/python/langgraph/event-streaming.md) |
| Model, tool, and content-block shapes | [Messages](langchain/messages.md) | [Official guide](https://docs.langchain.com/oss/python/langchain/messages.md) |

Workbench's [`checkpointer.py`](../../../apps/backend/src/workbench_backend/state/checkpointer.py), [`branches.py`](../../../apps/backend/src/workbench_backend/chat/branches.py), and [`interaction/service.py`](../../../apps/backend/src/workbench_backend/interaction/service.py) own the local integration. For model-adapter changes, see [`adapter.py`](../../../apps/backend/src/workbench_backend/inference/adapter.py) and the [ChatOpenAI API reference](https://reference.langchain.com/python/langchain-openai/langchain_openai/chat_models/base/ChatOpenAI); its standard OpenAI behavior does not automatically cover llama.cpp-specific fields.

## React interaction SDK and stream protocol

These copies match both installed JavaScript package tags at commit [`ec67d5d`](https://github.com/langchain-ai/langgraphjs/tree/ec67d5d70dc26341e92a0962d9d2f4018c310b39). Workbench also carries a local [SDK patch](../../../apps/desktop/patches/@langchain__langgraph-sdk@1.11.1.patch), so inspect it when stream behavior differs.

| Work area | Local copy | Upstream source |
| --- | --- | --- |
| Hook lifecycle, stop, disconnect, respond | [`useStream`](react/use-stream.md) | [1.1.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk-react/docs/use-stream.md) |
| Stock HTTP adapter for a custom backend | [Custom transport](react/custom-transport.md) | [1.1.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk-react/docs/custom-transport.md) |
| Scoped message and tool projections | [Selectors](react/selectors.md) | [1.1.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk-react/docs/selectors.md) |
| Frontend interrupt state | [Interrupts](react/interrupts.md) | [1.1.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk-react/docs/interrupts.md) |
| Queued follow-ups | [Submission queue](react/submission-queue.md) | [1.1.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk-react/docs/submission-queue.md) |
| Chat branch UI | [Fork from checkpoint](react/fork-from-checkpoint.md) | [1.1.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk-react/docs/fork-from-checkpoint.md) |
| Event protocol, replay and ordering | [Streaming](protocol/streaming.md) | [1.11.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk/docs/streaming.md) |
| Protocol interrupt events | [Streaming interrupts](protocol/streaming-interrupts.md) | [1.11.1 source](https://github.com/langchain-ai/langgraphjs/blob/ec67d5d70dc26341e92a0962d9d2f4018c310b39/libs/sdk/docs/streaming-interrupts.md) |

Local entry points: [`InteractionStream.tsx`](../../../apps/desktop/src/renderer/InteractionStream.tsx), [`interactionResume.ts`](../../../apps/desktop/src/renderer/interactionResume.ts), and the backend [`interaction/routes.py`](../../../apps/backend/src/workbench_backend/interaction/routes.py). The backend's durable application cursor remains its own authority; native SDK event sequence numbers are not a substitute.

The copied docs retain their upstream wording. Cross-links to pages in this set point to local copies; other links point to the official docs site or pinned GitHub source. License notices: [LangChain docs](licenses/docs-LICENSE), [Deep Agents](licenses/deepagents-LICENSE), and [LangGraph.js](licenses/langgraphjs-LICENSE) (MIT). Refresh a copy from its linked source when changing the corresponding integration, then recheck `uv.lock`, `package.json`, and the installed source.
