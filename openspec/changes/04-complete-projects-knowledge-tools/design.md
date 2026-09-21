# Design: Complete projects, knowledge and external tools

## Technical Approach

Extend the existing effective-setup resolver, harness/backend, knowledge/retrieval services, tool catalogue and Project/Knowledge/Chat configuration panels. Reusable agent setups reference existing profiles, tools and knowledge; they do not become another model or settings store. Compose ordinary instruction layers in the agreed order while enforcing access separately.

Keep project storage, retained originals, extracted source views and framework scratch distinct. Use official `memory=` and `skills=` integration for selected content, with protected instructions in composed system instructions. Refresh supported middleware state and only obsolete derived resources at turn boundaries; never reset the thread or delete framework history. Full skill packages include safe relative resources, not only SKILL.md. Moving an authorized resource to an execution environment is separate from loading it in a virtual backend.

Choose compatible local parsers for text/code, CSV, JSON, text-bearing PDF and DOCX. Preserve actual source ranges and parser versions; do not add a hosted extraction dependency. Existing derived retrieval remains opt-in and must validate real embeddings. Ordinary document reading does not depend on indexing.

After `migrate-local-agent-interaction` is implemented and verified, reuse its shared `@langchain/react` projections/subscriptions for common message, tool and run presentation. Keep configuration, connection and selection controls in the existing application-owned shared views, resolving the same versioned setup and authorization records. Use the repository's supported official LangChain MCP adapter and one shared async harness driver. This change owns migration of invocation/streaming, all middleware hooks, saver/state access, resume, cancellation and shutdown as one compatible path. The completed prerequisite proved public synchronous `stream_events` and retained that driver. Implement the complete async transition here, preserving the verified interaction boundary rather than splitting or duplicating drivers. Reuse the existing checkpointer database and public APIs; keep long-lived loop-bound resources on their owning loop. Ordinary Chat and Lab must still work without MCP.

Implement one concrete public web search plus page-reading integration; choose and document the provider/authentication/limits without assuming a paid account or substituting a documentation MCP. Preserve external content as untrusted task data. No second permission gate is required merely to use supplied content through tools already authorized for that task.

## UX presentation

Follow the shared UX contract in `../03-complete-shared-chat/design.md#shared-ux-contract`. This change owns the everyday workspace presentation for reusable agent setups, project controls, scoped Knowledge, file previews/diffs, proposal review and connection management. The primary journey must be understandable without raw JSON, internal identifiers or backend terminology; technical evidence, provenance, parser details, dependency records and backend diagnostics remain available in expandable details.

Expose reusable setups through the **Agents** destination while keeping the active setup selectable from the conversation controls defined by change 03. Project identity stays in the fixed conversation area and header; changing project area starts or opens a different conversation rather than detaching an existing one. File previews, diffs, changed-file review, document source inspection, memory proposals and tool activity use the shared right-hand panel and Library/retention records instead of separate stores. Connection add/edit/test/disconnect, saved permissions, appearance, notifications and manual backup/restore belong in **Settings**.

Technical verification and Dave's UX acceptance are separate completion records. Everyday workspace UX acceptance is currently pending, not accepted. It covers a built Windows journey at full-window and half-screen sizes, Windows display scaling, keyboard navigation, long content, and at least one failure/recovery state across a project file task, document-backed answer, memory proposal, skill resource read, connection lifecycle and ordinary Chat after the async transition. UX acceptance remains pending until Dave accepts the built journey or explicitly defers it.

## Failure and migration handling

Preserve real user scope/version identities and compatible existing threads. Expose unsupported checkpoint/session/client behaviour rather than deleting state or inventing compatibility. Record remote tool errors separately from transport/conversion failures. Imported packages, document text and discovered tools cannot authorize themselves. Extend the shared deletion/manual-backup contract for every new record family.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [Deep Agents integration guide](https://docs.langchain.com/oss/python/deepagents/overview)
