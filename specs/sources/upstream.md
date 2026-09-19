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

The supplied workflows pin actions to these verified upstream release commits:

- [actions/checkout v7.0.1](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1).
- [actions/setup-python v7.0.0](https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97).
- [actions/setup-node v7.0.0](https://github.com/actions/setup-node/commit/820762786026740c76f36085b0efc47a31fe5020).
- [astral-sh/setup-uv v10.0.1](https://github.com/astral-sh/setup-uv/commit/20cfd1bf945f4377ade1205e4dbc17946fc9a30d).
- [pnpm/action-setup v4.3.0](https://github.com/pnpm/action-setup/commit/b906affcce14559ad1aafd4ab0e942779e9f58b1).
- [actions/cache v6.1.0](https://github.com/actions/cache/commit/55cc8345863c7cc4c66a329aec7e433d2d1c52a9) (real-model smoke asset cache only).

The real-model smoke tier consumes the Linux x64 CPU asset of the same pinned llama.cpp release ([b11045 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11045), `llama-b11045-bin-ubuntu-x64.tar.gz`) and [Qwen/Qwen2.5-0.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) at the revision pinned in `apps/backend/tests_integration/assets.py`. The tiny model is a plumbing fixture, not a capability reference.

These pins concern CI runners only. They do not pin application dependencies or imply every workflow has run in the user's repository. Review updates to the actions and runner compatibility like other dependency changes. The actual action references in the workflows are the executable source of truth.
