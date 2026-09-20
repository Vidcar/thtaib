# thtaib — Product Vision and Integration Boundaries

thtaib is a local-first AI workspace for beginners and experienced users to **use, explore and understand models, agents and workflows**. It should make powerful capabilities approachable through a polished interface—not hide them behind simplified functionality.

The following describes the intended product, not its current implementation status.

## Chat — Use models your way

Chat should let users choose models, switch configurations and adjust supported reasoning controls, context size, generation settings and advanced runtime options.

When a change requires reloading a model or changing llama.cpp startup flags, thtaib should handle that process and clearly show what is actually applied, including any effect on other active sessions.

The aim is an approachable conversational and coding experience, inspired by applications such as ChatGPT and Codex, with a local-model focus and greater visibility into configuration and behaviour.

**Projects, coding, internet access, tools, MCP, plugins, voice and image generation all belong in the product vision.** Deliver these through existing integrations, with clear capability requirements and user-controlled access—not by rebuilding each underlying technology.

## Models — Find, download and configure

Models should help users browse Hugging Face, understand their options and download complete model bundles, including the chosen quantisation, required shards and companion files such as vision projectors where applicable.

Explain intended use, hardware requirements, recommended settings and available capabilities while preserving user choice. Clearly distinguish publisher claims, locally verified behaviour and anything still unverified.

Model files must be associated with their appropriate runtime or integration; downloading a model does not establish that it can run through llama.cpp. Saved configurations and capability evidence should carry into Chat, Lab and Workflows.

## Lab — Understand performance and capability

Lab should help users understand how models and configurations behave on their own hardware.

Tests should compare models, quantisations, context sizes and supported options such as multi-token prediction (MTP). Present understandable measurements for **prefill speed**—processing input—and **decode speed**—generating output—alongside memory use, responsiveness and the impact of running multiple simultaneous sessions.

Reasoning, tool-use and vision tests should show actual outputs, failures and evidence, not just scores. Record the configuration used so results remain meaningful and useful settings can be reused elsewhere. Expand the test catalogue over time.

## Workflows — Build and inspect agent processes

Workflows, currently labelled **Agent runs**, should become a visual node editor for simple and complex processes: sequences, branches, loops, parallel tasks and reusable workflows.

Connections should explain each node’s inputs, outputs and requirements. Keep **configuration connections**—models, tools and settings—distinct from **execution connections**—what runs next and what data passes between steps. Validate known incompatibilities before execution.

Chat and workflow nodes should reuse the same agent implementation, tools and model profiles rather than becoming separate systems.

## Which component provides what?

The upstream features below are existing capabilities to integrate. The thtaib responsibilities describe how the application should use them.

| Component | Existing capabilities to reuse | Responsibility within thtaib |
|---|---|---|
| **Hugging Face Hub + `huggingface_hub`** | Model repositories, revision-specific file downloads and caching. [Documentation](https://huggingface.co/docs/huggingface_hub/guides/download) | Provide model selection, resolve complete bundles and maintain installation records. |
| **llama.cpp + llama-server** | Inference for supported models, tokenisation, chat templates, runtime controls, supported multimodal processing and model APIs. [Documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) | Configure and supervise inference, expose supported settings and connect model responses to the application. |
| **LangChain** | Model, message and tool interfaces, integrations and agent-building components. [Documentation](https://docs.langchain.com/oss/python/langchain/overview) | Connect model endpoints and tools to the selected agent stack. Do not create an additional competing agent loop. |
| **Deep Agents** | An agent harness with tool execution, context management, memory, skills, subagents and configurable planning. Built on LangChain and LangGraph. [Documentation](https://docs.langchain.com/oss/python/deepagents/overview) | Provide the shared agent behaviour used by Chat and agent workflow steps, with configured tools and execution backends. |
| **LangGraph** | Stateful orchestration, durable execution, streaming, checkpoints and human intervention. [Documentation](https://docs.langchain.com/oss/python/langgraph/overview) | Execute user-defined workflows around agent steps; also provide Deep Agents’ underlying runtime. |
| **React Flow** | Visual node editing and interactive connections. [Documentation](https://reactflow.dev/) | Provide the workflow canvas. thtaib validates its definitions and translates them into backend execution—not execution inside the canvas. |
| **MCP + LangChain’s MCP integration** | A standard connection to tools exposed by MCP servers. [Documentation](https://docs.langchain.com/oss/python/langchain/mcp) | Provide connection setup, access controls and visible results. Actual capabilities depend on the connected tools. |
| **ComfyUI** | Media-generation workflows with APIs for submission, progress, queues and results. [Documentation](https://docs.comfy.org/development/comfyui-server/comms_routes) | Expose image generation through a shared integration usable from Chat, agents and workflow nodes. ComfyUI executes its own media graph. |
| **Whisper or an equivalent speech-recognition integration** | Speech-to-text transcription. Whisper is not a speech-generation engine. [Documentation](https://github.com/openai/whisper) | Provide voice input. Spoken replies require a separate text-to-speech integration; that choice remains open. |
| **llama-bench + Inspect AI** | Engine-performance measurements from llama-bench; task-evaluation building blocks from Inspect AI. [llama-bench documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md) | Build Lab comparisons around these tools, adding live concurrency tests and evaluating the same agents used elsewhere in thtaib. |

## Integration rules

**Reuse overlapping capabilities deliberately.** llama.cpp already offers Hugging Face downloading, while LangChain and Inspect also offer agent functionality. Their availability does not require separate download managers or agent implementations: use one managed model inventory and Deep Agents as the shared application harness.

**Build the workspace, not replacement engines.** thtaib should own the interface, shared configurations, lifecycle coordination, permissions, integration contracts and understandable results. Existing projects should perform the underlying inference, agent execution, workflow orchestration and media processing. Add custom implementations only where a verified product requirement is not already covered upstream.
