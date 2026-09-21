# Design: Complete the shared llama-server adapter

## Technical Approach

Extend `inference/adapter.py::chat_model_for_deployment()` and `agents/effective_setup.py`. Keep an initialized LangChain model against the existing chat-completions endpoint; resolve its actual model identifier. Do not use a provider string that bypasses the selected deployment or switch to Responses API implicitly.

Test actual serialized JSON. Keep supported standard sampling controls in client parameters and llama-specific controls in the endpoint extension body; constructor names alone do not prove the wire key. Preserve `AIMessage.tool_calls` and `ToolMessage.tool_call_id`, indexed streamed arguments, finish reasons and supplied usage. Add only the narrow conversion extension needed by the installed integration to carry returned reasoning and supported replay; private converter functions are version-sensitive.

Use the existing Deep Agents `response_format` seam with explicit native or tool-based strategy, retaining `structured_response` independently from answer text. Formatting repair is bounded and cannot rerun an effectful task. Configure the initialized model's supported context profile and the existing summarisation middleware together, including its own model request. Do not add a separate compaction loop.

Provide request-owned sync and async client/capture/cancellation paths now. Change 04 owns the full harness/saver async migration. Structured current-user content is the shared input seam; file intake remains change 03 and production image/audio intake change 08.

## Failure and verification

A known capability mismatch fails before dispatch; unknown support stays explicitly unverified rather than universally blocked. Compare request/wire response/message conversion with bounded, redacted capture. A live tiny-model check proves plumbing, not general tool, reasoning or vision competence.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output)
