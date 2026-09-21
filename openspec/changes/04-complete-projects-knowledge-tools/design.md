# Design: Complete projects, knowledge and external tools

## Technical Approach

Extend the existing effective-setup resolver, harness/backend, knowledge/retrieval services, tool catalogue and Project/Knowledge/Chat configuration panels. Reusable agent setups reference existing profiles, tools and knowledge; they do not become another model or settings store. Compose ordinary instruction layers in the agreed order while enforcing access separately.

Keep project storage, retained originals, extracted source views and framework scratch distinct. Use official `memory=` and `skills=` integration for selected content, with protected instructions in composed system instructions. Refresh supported middleware state and only obsolete derived resources at turn boundaries; never reset the thread or delete framework history. Full skill packages include safe relative resources, not only SKILL.md. Moving an authorized resource to an execution environment is separate from loading it in a virtual backend.

Choose compatible local parsers for text/code, CSV, JSON, text-bearing PDF and DOCX. Preserve actual source ranges and parser versions; do not add a hosted extraction dependency. Existing derived retrieval remains opt-in and must validate real embeddings. Ordinary document reading does not depend on indexing.

After `migrate-local-agent-interaction` is implemented and verified, reuse its shared `@langchain/react` projections/subscriptions for common message, tool and run presentation. Keep configuration, connection and selection controls in the existing application-owned shared views, resolving the same versioned setup and authorization records. Use the repository's supported official LangChain MCP adapter and one shared async harness driver. This change owns migration of invocation/streaming, all middleware hooks, saver/state access, resume, cancellation and shutdown as one compatible path. Retain the public synchronous `stream_events` path in the prerequisite if compatibility is proven; if that proof requires a complete async foundation, move that foundation coherently rather than split or duplicate drivers. Reuse the existing checkpointer database and public APIs; keep long-lived loop-bound resources on their owning loop. Ordinary Chat and Lab must still work without MCP.

Implement one concrete public web search plus page-reading integration; choose and document the provider/authentication/limits without assuming a paid account or substituting a documentation MCP. Preserve external content as untrusted task data. No second permission gate is required merely to use supplied content through tools already authorized for that task.

## Failure and migration handling

Preserve real user scope/version identities and compatible existing threads. Expose unsupported checkpoint/session/client behaviour rather than deleting state or inventing compatibility. Record remote tool errors separately from transport/conversion failures. Imported packages, document text and discovered tools cannot authorize themselves. Extend the shared deletion/manual-backup contract for every new record family.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [Deep Agents integration guide](https://docs.langchain.com/oss/python/deepagents/overview)
