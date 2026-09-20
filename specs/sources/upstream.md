# Upstream reference register

## How to use these references

The original links below were extracted from the supplied revision 0.5 document. They are documentation entry points, **not a pinned dependency manifest and not revalidated compatibility claims**. Read the documentation corresponding to the version actually selected in the repository. Record version/commit-specific evidence with the affected integration rather than treating a moving `latest` or `master` page as fixed behaviour.

Never let an upstream example silently replace application ownership, permissions, persistence or lifecycle requirements. The source explicitly identifies these as application implementation responsibilities.

## Links preserved from revision 0.5

- <https://huggingface.co/docs/huggingface_hub/guides/download>
- <https://docs.langchain.com/oss/python/deepagents/overview>
- <https://docs.langchain.com/oss/python/langgraph/overview>
- <https://docs.langchain.com/oss/python/langchain/overview>
- <https://fastapi.tiangolo.com/>
- <https://docs.pydantic.dev/latest/concepts/json_schema/>
- <https://www.electronjs.org/docs/latest/>
- <https://docs.comfy.org/development/comfyui-server/comms_routes>
- <https://docs.docker.com/compose/intro/features-uses/>
- <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- <https://github.com/ggml-org/llama.cpp/tree/master/gguf-py>
- <https://docs.langchain.com/oss/python/deepagents/models>
- <https://docs.langchain.com/oss/python/langgraph/use-subgraphs>
- <https://docs.langchain.com/oss/python/deepagents/subagents>
- <https://docs.langchain.com/oss/python/langgraph/checkpointers>
- <https://docs.langchain.com/oss/python/langchain/mcp>
- <https://inspect.aisi.org.uk/agents.html>
- <https://reactflow.dev/learn>
- <https://github.com/modelcontextprotocol/python-sdk>
- <https://github.com/ggml-org/llama.cpp/tree/master/tools/llama-bench>
- <https://docs.langchain.com/oss/python/deepagents/backends>
- <https://github.com/ggml-org/llama.cpp/tree/master/tools/server>
- <https://docs.langchain.com/oss/python/langchain/middleware/custom>
- <https://docs.langchain.com/oss/python/deepagents/memory>
- <https://docs.langchain.com/oss/python/deepagents/skills>
- <https://docs.langchain.com/oss/python/deepagents/rubric>
- <https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT>
- <https://docs.langchain.com/oss/python/deepagents/interpreters>
- <https://docs.langchain.com/oss/python/langchain/middleware/built-in>
- <https://docs.pydantic.dev/latest/>
- <https://reactflow.dev/>
- <https://docs.langchain.com/oss/python/langgraph/persistence>
- <https://inspect.aisi.org.uk/>
- <https://docs.docker.com/compose/>
- <https://docs.langchain.com/oss/python/langgraph/use-time-travel>
- <https://inspect.aisi.org.uk/datasets.html>
- <https://inspect.aisi.org.uk/scorers.html>
- <https://modelcontextprotocol.io/extensions/apps/overview>

## Product reset integration check (2026-09-20)

The lockfile and installed Windows environment agree: `huggingface-hub==1.32.0`, `deepagents==0.7.15`, `langchain==1.4.2`, `langchain-core==1.6.3`, `langchain-openai==1.6.2`, `langgraph==1.2.11`. No dependency upgrade is part of this reset.

- **Hugging Face:** inspected installed `hf_api.py` and `_snapshot_download.py`, and [v1.32.0 source](https://github.com/huggingface/huggingface_hub/blob/v1.32.0/src/huggingface_hub/_snapshot_download.py). `model_info(files_metadata=True)` supplies revision, relative filenames and sizes. `snapshot_download` owns filtering, local-directory metadata and interrupted transfer recovery. Application code groups candidate GGUF shards, requires one variant and an explicit projector choice, records the resolved commit, and preserves paths. Filename grouping is not architectural or projector compatibility evidence. Cards/config files remain untrusted reference data; they are not executable setup instructions. Live metadata lookup of Qwen2.5-0.5B returned nine variants without downloading weights.
- **llama.cpp:** the installed managed Windows CUDA binary reports build 11045, commit `2b1847030`. Its `--help` and the [b11045 server reference](https://github.com/ggml-org/llama.cpp/blob/b11045/tools/server/README.md) agree on model-derived context (`0`), fitting, KV-cache types, batching, template/reasoning and speculative controls. The app no longer inserts a universal 65,536 context; explicit saved values remain explicit. The adapter maps supported startup controls as argument arrays. Reasoning effort names are runtime controls, not evidence that a particular model implements levels. MTP and draft decoding require suitable model/runtime prerequisites; emitted flags do not establish speed or observed behavior.
- **Planning and delegation:** installed `deepagents/graph.py` creates a general-purpose subagent, but does not include `TodoListMiddleware`. The app now adds the official `langchain.agents.middleware.TodoListMiddleware` when `write_todos` is selected. Its checkpointed state and tool results stay upstream-owned ([middleware reference](https://docs.langchain.com/oss/python/langchain/middleware/built-in)). The application's parent tool-selection middleware is not automatically inherited by the default child. Delegation therefore still needs explicit child policy/capture wiring and denied-access tests before exposing `task`; this is an integration gap, not a permanent product exclusion.
- **MCP:** installed `langchain/mcp` and distribution metadata confirm the existing `langchain.mcp.MCPAdapter` direction and optional `mcp` extra. The application has not wired it yet. The standalone historical adapter example is not the appropriate basis for this pin (see [MCP findings](#langchain-mcp)).

No changed setting or small probe promotes a catalogue requirement to fully verified. Effective startup, sent requests and runtime observations remain distinct; missing structured capability probes are recorded in [the delivery order](../../docs/delivery-feature-map.md#next-path).

<a id="langchain-retrieval"></a>
## LangChain / Deep Agents retrieval (OQ-006)

Consulted 2026-09-19 against the pinned backend lock (`deepagents==0.7.15`, `langchain==1.4.2`, `langchain-core==1.6.3`, `langchain-openai==1.6.2`) and llama.cpp b11045. Moving `docs.langchain.com` pages are not version-pinned evidence; record the pin with the implementation.

- [Retrieval Augmented Generation with Deep Agents](https://docs.langchain.com/oss/python/deepagents/rag) — retrieve, offload to `/retrieved/`, optional subagent analysis.
- [LangChain retrieval](https://docs.langchain.com/oss/python/langchain/retrieval) — 2-step vs agentic vs hybrid RAG.
- [Build a semantic search engine](https://docs.langchain.com/oss/python/langchain/knowledge-base) — loaders, splitters, embeddings, vector stores.
- [`InMemoryVectorStore`](https://reference.langchain.com/python/langchain-core/vectorstores/in_memory/InMemoryVectorStore/).
- [`OpenAIEmbeddings`](https://reference.langchain.com/python/langchain-openai/embeddings/base/OpenAIEmbeddings/) — `base_url` + `check_embedding_ctx_length=False` for OpenAI-compatible servers.
- [Deep Agents memory](https://docs.langchain.com/oss/python/deepagents/memory) and [skills](https://docs.langchain.com/oss/python/deepagents/skills) — always-load / progressive disclosure, not query-time RAG (see also the 2026-09-20 pin-checked note below).
- [llama-server embeddings](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) — `POST /v1/embeddings`, `--embedding`, `--pooling`.

<a id="deepagents-memory-skills"></a>
## Deep Agents memory and skills (OQ-006 / AGT-004)

Consulted 2026-09-20 against the pinned backend lock (`deepagents==0.7.15`). Live `docs.langchain.com` pages are not the pin. The 0.7.15 wheel was read for `create_deep_agent` (`deepagents/graph.py`), `MemoryMiddleware` (`deepagents/middleware/memory.py`), `SkillsMiddleware` (`deepagents/middleware/skills.py`) and `CompositeBackend` routing (`deepagents/backends/composite.py`). Cross-checked with:

- [Memory](https://docs.langchain.com/oss/python/deepagents/memory) — `memory=` file paths; `MemoryMiddleware` always-loads via `backend.download_files`; default fragment treats files as untrusted data and encourages `edit_file` on the hot path. Official durable example is `StoreBackend`; this product write-throughs those official file writes into STATE-005 instead.
- [Skills](https://docs.langchain.com/oss/python/deepagents/skills) — `skills=` directory sources; progressive disclosure of `SKILL.md` YAML `name` / `description`; a path that points at one skill directory is not loaded; invalid frontmatter is skipped.
- [`create_deep_agent`](https://reference.langchain.com/python/deepagents/graph/create_deep_agent) — `memory=` and `skills=` kwargs; `MemoryMiddleware` is tail middleware (after caller middleware); `SkillsMiddleware` is base middleware.

`StoreBackend` and background consolidation appear on the live memory page as optional platform patterns. They are not adopted here as a knowledge owner ([OQ-006](../open-questions.md#oq-006), [OQ-009](../open-questions.md#oq-009)). Agent memory durability is official `edit_file` / `write_file` plus application write-through to STATE-005.

<a id="langchain-mcp"></a>
## LangChain MCP adapter (OQ-009 / ENV-007)

Consulted 2026-09-20 against the pinned backend lock (`langchain==1.4.2`, `deepagents==0.7.15`). Live `docs.langchain.com` pages are not the pin. PyPI 1.4.2 extra `mcp` requires `fastmcp>=4.0.1,<5`. The `langchain.mcp` namespace is beta. Cross-checked with:

- [Model Context Protocol (MCP)](https://docs.langchain.com/oss/python/langchain/mcp) — `MCPAdapter`, transport inference, `langchain[mcp]>=1.4.0`.
- [Connections](https://docs.langchain.com/oss/python/langchain/mcp/connections) — lifecycle, `MCPConfig`, `ClientGroup`, hold-open vs reentrant tools, protocol eras.
- [Tools](https://docs.langchain.com/oss/python/langchain/mcp/tools) — `list_tools()`, metadata annotations, HITL via `interrupt_on`, elicitation as LangGraph interrupt.
- [Authentication](https://docs.langchain.com/oss/python/langchain/mcp/auth) — bearer, OAuth, per-server `Client`.
- [Migrate from langchain-mcp-adapters](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters) — `MultiServerMCPClient` is replaced; do not add that package on this pin.
- [MCPAdapter reference](https://reference.langchain.com/python/langchain/mcp/adapter/MCPAdapter).
- Official first servers: [Playwright MCP](https://github.com/microsoft/playwright-mcp) (`@playwright/mcp`) and [GitHub MCP Server](https://github.com/github/github-mcp-server) (remote `https://api.githubcopilot.com/mcp/`).

Live Deep Agents customisation pages still show `langchain-mcp-adapters`. That is stale relative to `langchain==1.4.2`. Implementation must call `langchain.mcp.MCPAdapter`, not the standalone package. Prompts, resources, sampling, roots, and MCP Apps are out of [ENV-007](../modules/environments-tools.md#env-007).

<a id="fastapi-sse"></a>
## FastAPI Server-Sent Events

Consulted 2026-09-19 for the pinned FastAPI 0.141 line (SSE added in 0.135.0):

- [Server-Sent Events (SSE)](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — `EventSourceResponse`, `ServerSentEvent`, `Last-Event-ID`, automatic keep-alive comments.
- [SSE reference](https://fastapi.tiangolo.com/reference/sse/).

LangGraph `stream_mode="updates"` (pinned `langgraph>=1.0,<2`) remains the harness ingest path ([streaming](https://docs.langchain.com/oss/python/langgraph/streaming)); the application maps those updates to `AgentEvent` and SSE publishes the application events.

<a id="contract-generation"></a>
## Additional contract-generation references

The following official references were consulted on 18 September 2026 for the proposed authoring mechanism, not to select runtime package versions:

- [Pydantic JSON Schema generation](https://docs.pydantic.dev/latest/concepts/json_schema/).
- [FastAPI client/SDK generation from OpenAPI](https://fastapi.tiangolo.com/advanced/generate-clients/).

The selected OpenAPI→TS generator for [ADR-0002](../decisions/ADR-0002-contract-authoring.md) is [openapi-typescript 7.13.0](https://github.com/openapi-ts/openapi-typescript/releases/tag/openapi-typescript%407.13.0), pinned in `apps/desktop/package.json`. A moving npm `latest` tag is not the pin.

## Additional governance references

Official references consulted on 18 September 2026:

- [AGENTS.md open instruction format](https://agents.md/).
- [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).
- [GitHub protected branches and required reviews/checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

The removed GitHub workflows used these upstream release commits (historical references only; GitHub CI was disabled on 2026-09-20):

- [actions/checkout v7.0.1](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1).
- [actions/setup-python v7.0.0](https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97).
- [actions/setup-node v7.0.0](https://github.com/actions/setup-node/commit/820762786026740c76f36085b0efc47a31fe5020).
- [astral-sh/setup-uv v10.0.1](https://github.com/astral-sh/setup-uv/commit/20cfd1bf945f4377ade1205e4dbc17946fc9a30d).
- [pnpm/action-setup v4.3.0](https://github.com/pnpm/action-setup/commit/b906affcce14559ad1aafd4ab0e942779e9f58b1).
- [actions/cache v6.1.0](https://github.com/actions/cache/commit/55cc8345863c7cc4c66a329aec7e433d2d1c52a9) (real-model smoke asset cache only).

The real-model smoke tier consumes the Linux x64 CPU asset of the same pinned llama.cpp release ([b11045 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11045), `llama-b11045-bin-ubuntu-x64.tar.gz`) and [Qwen/Qwen2.5-0.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) at the revision pinned in `apps/backend/tests_integration/assets.py`. The tiny model is a plumbing fixture, not a capability reference.

These historical pins concerned CI runners only. They do not pin application dependencies or imply that GitHub checks remain enabled.
