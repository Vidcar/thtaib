"""MOD-005: narrow LangChain adapter to a model-manager deployment endpoint.

The adapter talks to an existing OpenAI-compatible chat endpoint. It does
not load weights and does not start, stop, or supervise an inference
process. llama.cpp owns tokenisation, templates and actual context.
"""

from __future__ import annotations

import json
import asyncio
import contextvars
import re
from collections.abc import Sequence
from typing import Any, Callable

import httpx
from langchain_core.language_models.model_profile import ModelProfile
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import PrivateAttr

from workbench_backend.errors import HarnessError
from workbench_backend.inference.configuration_options import reasoning_history_descriptor, validate_model_reasoning
from workbench_backend.inference.schemas import Deployment, GgufRuntimeMetadata, SettingsBag
from workbench_backend.inference.settings import normalize_on_off_auto
from workbench_backend.inference.telemetry import RequestTelemetry

# Transport timeout only — not a product task budget (AGT-003).
DEFAULT_ADAPTER_TIMEOUT = 120.0
CAPTURE_TEXT_LIMIT = 240
CAPTURE_EVENT_LIMIT = 64
DEFAULT_OUTPUT_RESERVATION = 512
TOKEN_MARGIN_RATIO = 0.08
_stream_chunk_count: contextvars.ContextVar[int] = contextvars.ContextVar("adapter_stream_chunk_count", default=0)
_request_telemetry: contextvars.ContextVar[RequestTelemetry | None] = contextvars.ContextVar("adapter_request_telemetry", default=None)
_async_observer: contextvars.ContextVar[_AsyncObservation | None] = contextvars.ContextVar("adapter_async_observer", default=None)
_SECRET_TEXT_RE = re.compile(r"\bsk-[A-Za-z0-9_-]+\b")
_SECRET_KEYS = {"api_key", "authorization", "token", "access_token", "refresh_token", "secret", "password"}
_pending_async_closes: set[asyncio.Task[None]] = set()


class _AsyncObservation:
    """Keep bounded measurement publication off the graph/saver loop.

    RequestTelemetry already limits updates to four per second. Chain these
    callbacks in order and drain them before finishing the model call, so final
    measurements cannot race lifecycle publication or the next request's reset.
    """

    def __init__(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self.callback = callback
        self.pending: asyncio.Task[None] | None = None

    def __call__(self, sample: dict[str, Any]) -> None:
        previous = self.pending
        async def publish() -> None:
            if previous is not None:
                await previous
            await asyncio.to_thread(self.callback, sample)
        self.pending = asyncio.create_task(publish())

    async def flush(self) -> None:
        if self.pending is not None:
            await asyncio.shield(self.pending)

DIRECT_CHAT_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "stop",
    "reasoning_effort",
)

EXTRA_BODY_KEYS = (
    "top_k",
    "min_p",
    "typical_p",
    "repeat_penalty",
    "reasoning_format",
    "logit_bias",
)


class RecordingTransport(httpx.BaseTransport):
    """Records each chat-completions request and transport outcome."""

    def __init__(
        self,
        sink: list[dict[str, Any]],
        inner: httpx.BaseTransport | None = None,
    ) -> None:
        self.sink = sink
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        record: dict[str, Any] | None = None
        if request.url.path.endswith("/chat/completions"):
            record = {
                "url": str(request.url),
                "method": request.method,
                "body": _redact_body(_decode_body(request.content)),
                "response_received": False,
            }
            self.sink.append(record)
        try:
            response = self.inner.handle_request(request)
        except Exception as exc:
            if record is not None:
                record["transport_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            raise
        if record is not None:
            record["response_received"] = True
            record["response_status_code"] = response.status_code
        return response

    def close(self) -> None:
        self.inner.close()


class AsyncRecordingTransport(httpx.AsyncBaseTransport):
    """Async variant of :class:`RecordingTransport` for owned async clients."""

    def __init__(
        self,
        sink: list[dict[str, Any]],
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.sink = sink
        self.inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        record: dict[str, Any] | None = None
        if request.url.path.endswith("/chat/completions"):
            record = {
                "url": str(request.url),
                "method": request.method,
                "body": _redact_body(_decode_body(request.content)),
                "response_received": False,
            }
            self.sink.append(record)
        try:
            response = await self.inner.handle_async_request(request)
        except Exception as exc:
            if record is not None:
                record["transport_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            raise
        if record is not None:
            record["response_received"] = True
            record["response_status_code"] = response.status_code
        return response

    async def aclose(self) -> None:
        await self.inner.aclose()


class WorkbenchChatOpenAI(ChatOpenAI):
    """ChatOpenAI subclass with llama.cpp chat-completions fidelity fixes."""

    _owned_http_client: httpx.Client | None = PrivateAttr(default=None)
    _owned_async_http_client: httpx.AsyncClient | None = PrivateAttr(default=None)
    _prefer_max_tokens: bool = PrivateAttr(default=False)
    _reasoning_replay_supported: bool = PrivateAttr(default=False)
    _capture_sink: list[dict[str, Any]] | None = PrivateAttr(default=None)
    _context_guard: Callable[[dict[str, Any]], None] | None = PrivateAttr(default=None)
    _generation_observer: Callable[[dict[str, Any]], None] | None = PrivateAttr(default=None)

    def set_adapter_ownership(
        self,
        *,
        http_client: httpx.Client | None,
        async_http_client: httpx.AsyncClient | None,
        prefer_max_tokens: bool,
        reasoning_replay_supported: bool,
        capture_sink: list[dict[str, Any]] | None,
    ) -> None:
        self._owned_http_client = http_client
        self._owned_async_http_client = async_http_client
        self._prefer_max_tokens = prefer_max_tokens
        self._reasoning_replay_supported = reasoning_replay_supported
        self._capture_sink = capture_sink

    def set_context_guard(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._context_guard = callback

    def set_generation_observer(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._generation_observer = callback

    def invoke(self, *args: Any, **kwargs: Any) -> BaseMessage:
        result = super().invoke(*args, **kwargs)
        _clear_openai_provider_tag(result)
        return result

    async def ainvoke(self, *args: Any, **kwargs: Any) -> BaseMessage:
        result = await super().ainvoke(*args, **kwargs)
        _clear_openai_provider_tag(result)
        return result

    def close(self) -> None:
        if self._owned_http_client is not None:
            self._owned_http_client.close()
            self._owned_http_client = None
        if self._owned_async_http_client is not None:
            _close_async_client_safely(self._owned_async_http_client)
            self._owned_async_http_client = None

    async def aclose(self) -> None:
        if self._owned_http_client is not None:
            self._owned_http_client.close()
            self._owned_http_client = None
        if self._owned_async_http_client is not None:
            await self._owned_async_http_client.aclose()
            self._owned_async_http_client = None

    def _get_request_payload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = super()._get_request_payload(*args, **kwargs)
        if payload.get("tools") == []:
            payload.pop("tools")
            payload.pop("tool_choice", None)
        if self._prefer_max_tokens and "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        if self._reasoning_replay_supported and args:
            _add_reasoning_replay(payload, args[0])
        if self._context_guard is not None:
            self._context_guard(payload)
        observer = _async_observer.get() or self._generation_observer
        _request_telemetry.set(RequestTelemetry(observer) if observer else None)
        return payload

    def _create_chat_result(
        self,
        response: dict | Any,
        generation_info: dict | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        response_dict = response if isinstance(response, dict) else response.model_dump(warnings=False)
        telemetry = _request_telemetry.get()
        if telemetry is not None:
            telemetry.receive(response_dict)
            telemetry.finish()
        for generation, choice in zip(result.generations, response_dict.get("choices", []), strict=False):
            message = choice.get("message") or {}
            _attach_reasoning(generation.message, message)
            _clear_openai_provider_tag(generation.message)
            _capture_converted_message(self._capture_sink, generation, choice)
        return result

    def _stream(self, *args: Any, **kwargs: Any) -> Any:
        token = _stream_chunk_count.set(0)
        telemetry_token = _request_telemetry.set(None)
        combined: ChatGenerationChunk | None = None
        telemetry: RequestTelemetry | None = None
        try:
            for chunk in super()._stream(*args, **kwargs):
                telemetry = _request_telemetry.get()
                combined = chunk if combined is None else combined + chunk
                yield chunk
            _raise_for_invalid_completed_tool_calls(combined)
            if telemetry is not None:
                telemetry.finish()
        except BaseException as exc:
            if telemetry is not None:
                telemetry.finish(interrupted=True)
            _capture_stream_error(self._capture_sink, exc, _stream_chunk_count.get())
            raise
        finally:
            _reset_context_token(token)
            _reset_context_token(telemetry_token)

    async def _astream(self, *args: Any, **kwargs: Any) -> Any:
        observer = _AsyncObservation(self._generation_observer) if self._generation_observer else None
        observer_token = _async_observer.set(observer)
        token = _stream_chunk_count.set(0)
        telemetry_token = _request_telemetry.set(None)
        combined: ChatGenerationChunk | None = None
        telemetry: RequestTelemetry | None = None
        try:
            async for chunk in super()._astream(*args, **kwargs):
                telemetry = _request_telemetry.get()
                combined = chunk if combined is None else combined + chunk
                if observer is not None:
                    await observer.flush()
                yield chunk
            _raise_for_invalid_completed_tool_calls(combined)
            if telemetry is not None:
                telemetry.finish()
        except BaseException as exc:
            if telemetry is not None:
                telemetry.finish(interrupted=True)
            _capture_stream_error(self._capture_sink, exc, _stream_chunk_count.get())
            raise
        finally:
            try:
                if observer is not None:
                    await observer.flush()
            finally:
                _reset_context_token(observer_token)
                _reset_context_token(token)
                _reset_context_token(telemetry_token)

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        observer = _AsyncObservation(self._generation_observer) if self._generation_observer else None
        observer_token = _async_observer.set(observer)
        try:
            return await super()._agenerate(*args, **kwargs)
        finally:
            try:
                if observer is not None:
                    await observer.flush()
            finally:
                _reset_context_token(observer_token)

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        if telemetry := _request_telemetry.get():
            telemetry.receive(chunk)
        generation = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        if generation is None:
            return None
        choices = chunk.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            _attach_reasoning(generation.message, delta)
        _clear_openai_provider_tag(generation.message)
        _stream_chunk_count.set(_stream_chunk_count.get() + 1)
        _capture_converted_chunk(self._capture_sink, generation, chunk)
        return generation


def _reset_context_token(token: contextvars.Token[Any]) -> None:
    try:
        token.var.reset(token)
    except ValueError:
        # Python may finalize a partially-consumed async generator in a fresh
        # cleanup Context. Its original token has no state to restore there.
        # The stream's captured telemetry still belongs to its original call.
        pass


def chat_model_for_deployment(
    deployment: Deployment,
    *,
    per_request: SettingsBag | None = None,
    capture_sink: list[dict[str, Any]] | None = None,
    timeout: float = DEFAULT_ADAPTER_TIMEOUT,
    http_client: httpx.Client | None = None,
    http_async_client: httpx.AsyncClient | None = None,
) -> WorkbenchChatOpenAI:
    """Return a LangChain chat model aimed only at ``deployment.endpoint``.

    ``per_request`` is the resolved applied bag for this call (selected
    profile when one was resolved). The deployment bag is used only when
    no resolved bag is supplied. Raises if the deployment has no endpoint.
    Never starts a managed llama-server or any other inference process.
    """

    endpoint = (deployment.endpoint or "").rstrip("/")
    if not endpoint:
        raise HarnessError(
            "Deployment has no OpenAI-compatible endpoint. Start or attach "
            "a deployment first; the adapter does not start inference.",
            code="no_endpoint",
            status_code=409,
        )

    per_request = per_request if per_request is not None else deployment.settings.per_request
    validate_model_reasoning(deployment, per_request)
    kwargs = _direct_kwargs(per_request)
    extra_body = _extra_body(per_request)
    generation_defaults = deployment.server_props.default_generation_settings if deployment.server_props else {}
    native_params = generation_defaults.get("params", generation_defaults)
    if deployment.scope == "managed" or (isinstance(native_params, dict) and "timings_per_token" in native_params):
        # These extensions belong to llama.cpp, not arbitrary compatible APIs.
        extra_body.update(timings_per_token=True, return_progress=True)
    client = http_client
    async_client = http_async_client
    owned_client: httpx.Client | None = None
    owned_async_client: httpx.AsyncClient | None = None
    if client is None and capture_sink is not None:
        client = httpx.Client(
            transport=RecordingTransport(capture_sink),
            timeout=timeout,
        )
        owned_client = client
    elif client is None:
        client = httpx.Client(timeout=timeout)
        owned_client = client
    if async_client is None and capture_sink is not None:
        async_client = httpx.AsyncClient(
            transport=AsyncRecordingTransport(capture_sink),
            timeout=timeout,
        )
        owned_async_client = async_client
    elif async_client is None:
        async_client = httpx.AsyncClient(timeout=timeout)
        owned_async_client = async_client
    try:
        model_name = _resolve_model_name(deployment, endpoint, client)
        reasoning_replay_supported = _reasoning_replay_supported(deployment)
        profile = _model_profile(deployment, per_request)

        model = WorkbenchChatOpenAI(
            model=model_name,
            profile=profile,
            base_url=endpoint,
            api_key="not-required",
            use_responses_api=False,
            http_client=client,
            http_async_client=async_client,
            stream_usage=True,
            max_retries=0,
            extra_body=extra_body or None,
            **kwargs,
        )
    except Exception:
        if owned_client is not None:
            owned_client.close()
        if owned_async_client is not None:
            _close_async_client_safely(owned_async_client)
        raise
    model.set_adapter_ownership(
        http_client=owned_client,
        async_http_client=owned_async_client,
        prefer_max_tokens="max_tokens" in kwargs,
        reasoning_replay_supported=reasoning_replay_supported,
        capture_sink=capture_sink,
    )
    return model


def adapter_target(deployment: Deployment) -> dict[str, Any]:
    """Describe the adapter target without creating a model or a process."""

    return {
        "deployment_id": deployment.id,
        "endpoint": deployment.endpoint,
        "starts_inference": False,
        "engine_owner": "llama.cpp / connected OpenAI-compatible endpoint",
        "adapter": "langchain-openai ChatOpenAI chat-completions",
        "model": _model_name_from_props(deployment),
        "max_input_tokens": (_model_profile(deployment, deployment.settings.per_request) or {}).get("max_input_tokens"),
        "reasoning_replay_supported": _reasoning_replay_supported(deployment),
        "unsupported": list(deployment.settings.per_request.unsupported),
        "unverified": list(deployment.settings.per_request.unverified),
    }


def _direct_kwargs(bag: SettingsBag) -> dict[str, Any]:
    return {
        key: bag.applied[key] for key in DIRECT_CHAT_KEYS if key in bag.applied
        and not (key == "reasoning_effort" and bag.applied[key] == "default")
    }


def _extra_body(bag: SettingsBag) -> dict[str, Any]:
    body = {key: bag.applied[key] for key in EXTRA_BODY_KEYS if key in bag.applied}
    if "reasoning" in bag.applied:
        thinking = normalize_on_off_auto(bag.applied["reasoning"], allow_auto=True)
        if thinking is None:
            raise HarnessError(
                "Thinking must be On, Off, or Model default.",
                code="invalid_reasoning_setting", status_code=422,
            )
        if thinking != "auto":
            # llama.cpp merges these per-request keys into its startup template
            # defaults. Send only the override so tool/template defaults survive.
            body["chat_template_kwargs"] = {"enable_thinking": thinking == "on"}
    return body


def _close_async_client_safely(client: httpx.AsyncClient) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(client.aclose())
        return
    task = loop.create_task(client.aclose())
    _pending_async_closes.add(task)
    task.add_done_callback(_pending_async_closes.discard)


def _decode_body(content: bytes) -> Any:
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"_raw": content.decode("utf-8", errors="replace")}


def _model_name_from_props(deployment: Deployment) -> str | None:
    props = deployment.server_props
    if props is not None and props.model_alias:
        return props.model_alias
    return None


def _resolve_model_name(deployment: Deployment, endpoint: str, client: httpx.Client) -> str:
    observed = _model_name_from_props(deployment)
    if observed:
        return observed
    try:
        response = client.get(f"{endpoint}/models")
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise HarnessError(
            "Deployment model identity is unavailable. The adapter needs an "
            "observed server model alias or one unambiguous endpoint /models entry.",
            code="model_identity_unavailable",
            status_code=409,
            details={"error": type(exc).__name__},
        ) from exc
    identities = _model_identities(payload)
    if len(identities) == 1:
        return identities[0]
    if identities:
        raise HarnessError(
            "Deployment endpoint exposes multiple model identities. Select or "
            "record one concrete deployment model before dispatch.",
            code="ambiguous_model_identity",
            status_code=409,
            details={"models": identities},
        )
    raise HarnessError(
        "Deployment endpoint did not expose a usable model identity.",
        code="model_identity_unavailable",
        status_code=409,
    )


def _model_identities(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        raw_items = payload.get("models")
    identities: list[str] = []
    if not isinstance(raw_items, list):
        return identities
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        value = item.get("id") or item.get("model") or item.get("name")
        if isinstance(value, str) and value.strip() and value.strip() not in identities:
            identities.append(value.strip())
    return identities


def _reasoning_replay_supported(deployment: Deployment) -> bool:
    props = deployment.server_props
    caps = props.chat_template_caps if props is not None else {}
    if caps.get("supports_preserve_reasoning") is not True:
        return False
    explicit = deployment.applied_startup.get("reasoning_preserve")
    if explicit is not None:
        return explicit is True
    descriptor = reasoning_history_descriptor(GgufRuntimeMetadata(), deployment)
    return descriptor.default_value is True


def _model_profile(deployment: Deployment, per_request: SettingsBag) -> ModelProfile:
    capacity = deployment.server_props.n_ctx if deployment.server_props is not None else None
    if not isinstance(capacity, int) or capacity <= 0:
        return ModelProfile()
    reservation = per_request.applied.get("max_tokens")
    if not isinstance(reservation, int) or reservation <= 0:
        reservation = DEFAULT_OUTPUT_RESERVATION
    margin = int(capacity * TOKEN_MARGIN_RATIO)
    max_input_tokens = max(0, capacity - reservation - margin)
    return ModelProfile(max_input_tokens=max_input_tokens)


def _add_reasoning_replay(payload: dict[str, Any], input_: Any) -> None:
    messages = payload.get("messages")
    source = _source_messages(input_)
    if not isinstance(messages, list) or source is None:
        return
    for outbound, original in zip(messages, source, strict=False):
        if not isinstance(outbound, dict) or not isinstance(original, AIMessage):
            continue
        reasoning = original.additional_kwargs.get("reasoning_content")
        if reasoning is None:
            reasoning = original.additional_kwargs.get("reasoning")
        if reasoning not in (None, ""):
            outbound["reasoning_content"] = reasoning


def _source_messages(input_: Any) -> Sequence[BaseMessage] | None:
    if (
        isinstance(input_, Sequence)
        and not isinstance(input_, str)
        and all(isinstance(message, BaseMessage) for message in input_)
    ):
        return input_
    return None


def _attach_reasoning(message: Any, payload: dict[str, Any]) -> None:
    if not isinstance(message, AIMessage):
        return
    reasoning = payload.get("reasoning_content")
    if reasoning is None:
        reasoning = payload.get("reasoning")
    if reasoning in (None, ""):
        return
    message.additional_kwargs["reasoning_content"] = reasoning
    message.response_metadata["reasoning_content"] = reasoning


def _clear_openai_provider_tag(message: Any) -> None:
    """Let local OpenAI-compatible output use LangChain's generic block projection.

    ChatOpenAI stamps `model_provider="openai"` on messages and chunks. That is
    correct for OpenAI responses, but local llama.cpp-compatible servers may
    return `reasoning_content`, which LangChain's OpenAI-specific content-block
    translator ignores. Removing only the provider tag keeps the raw reasoning
    metadata for replay while allowing the public generic projection to expose
    reasoning blocks in native event streams.
    """

    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict) and metadata.get("model_provider") == "openai":
        metadata.pop("model_provider", None)


def _raise_for_invalid_completed_tool_calls(chunk: ChatGenerationChunk | None) -> None:
    if chunk is None:
        return
    message = chunk.message
    if getattr(message, "invalid_tool_calls", None):
        raise HarnessError(
            "The endpoint returned a malformed streamed tool call.",
            code="adapter_invalid_tool_call",
            status_code=502,
        )
    for tool_chunk in getattr(message, "tool_call_chunks", None) or []:
        args = tool_chunk.get("args") if isinstance(tool_chunk, dict) else getattr(tool_chunk, "args", None)
        if isinstance(args, str) and args.strip():
            try:
                json.loads(args)
            except json.JSONDecodeError as exc:
                raise HarnessError(
                    "The endpoint returned an incomplete streamed tool call.",
                    code="adapter_incomplete_tool_call",
                    status_code=502,
                ) from exc


def _capture_converted_message(
    sink: list[dict[str, Any]] | None,
    generation: Any,
    choice: dict[str, Any],
) -> None:
    if sink is None:
        return
    record = _last_request_record(sink)
    if record is None:
        return
    message = generation.message
    observations = _observations(record)
    observations["latest_finish_reason"] = choice.get("finish_reason")
    observations["latest_usage"] = getattr(message, "usage_metadata", None)
    _append_bounded(
        observations,
        "converted_messages",
        {
            "event": "converted_message",
            "content_preview": _preview(_redact_media(message.content)),
            "finish_reason": choice.get("finish_reason"),
            "tool_call_count": len(getattr(message, "tool_calls", []) or []),
            "invalid_tool_call_count": len(getattr(message, "invalid_tool_calls", []) or []),
            "has_reasoning": bool(message.additional_kwargs.get("reasoning_content")),
            "usage": getattr(message, "usage_metadata", None),
        },
    )


def _capture_converted_chunk(
    sink: list[dict[str, Any]] | None,
    generation: ChatGenerationChunk,
    chunk: dict[str, Any],
) -> None:
    if sink is None:
        return
    record = _last_request_record(sink)
    if record is None:
        return
    message = generation.message
    choices = chunk.get("choices") or []
    choice = choices[0] if choices else {}
    observations = _observations(record)
    observations["chunks_seen"] = int(observations.get("chunks_seen", 0)) + 1
    observations["latest_finish_reason"] = choice.get("finish_reason") or observations.get("latest_finish_reason")
    observations["latest_usage"] = getattr(message, "usage_metadata", None) or observations.get("latest_usage")
    _append_bounded(
        observations,
        "converted_chunks",
        {
            "event": "converted_chunk",
            "content_preview": _preview(_redact_media(message.content)),
            "finish_reason": choice.get("finish_reason"),
            "tool_call_chunk_count": len(getattr(message, "tool_call_chunks", []) or []),
            "has_reasoning": bool(message.additional_kwargs.get("reasoning_content")),
            "usage": getattr(message, "usage_metadata", None),
        },
    )


def _capture_stream_error(
    sink: list[dict[str, Any]] | None,
    exc: BaseException,
    converted_chunks: int,
) -> None:
    if sink is None:
        return
    record = _last_request_record(sink)
    if record is None:
        return
    observations = _observations(record)
    observations["stream_error"] = {
        "event": "stream_error",
        "error_type": type(exc).__name__,
        "message_preview": _preview(str(exc)),
        "converted_chunks": converted_chunks,
    }


def _last_request_record(sink: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(sink):
        if "body" in item and "url" in item:
            return item
    return None


def _observations(record: dict[str, Any]) -> dict[str, Any]:
    observations = record.setdefault("observations", {})
    return observations if isinstance(observations, dict) else {}


def _append_bounded(container: dict[str, Any], key: str, value: dict[str, Any]) -> None:
    items = container.setdefault(key, [])
    if not isinstance(items, list):
        return
    if len(items) < CAPTURE_EVENT_LIMIT:
        items.append(value)
    else:
        container[f"{key}_dropped_count"] = int(container.get(f"{key}_dropped_count", 0)) + 1


def _redact_body(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    redacted = {key: _redact_value(key, item) for key, item in value.items() if key != "messages"}
    messages = value.get("messages")
    if isinstance(messages, list):
        redacted["messages"] = [_redact_message(message) for message in messages]
    return redacted


def _redact_message(message: Any) -> Any:
    if not isinstance(message, dict):
        return {"type": type(message).__name__}
    redacted: dict[str, Any] = {"role": message.get("role")}
    if "name" in message:
        redacted["name"] = message.get("name")
    if "tool_call_id" in message:
        redacted["tool_call_id"] = message.get("tool_call_id")
    if "content" in message:
        redacted["content_preview"] = _preview(_redact_media(message.get("content")))
        if message.get("role") == "system":
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text")
            if isinstance(content, str):
                from workbench_backend.knowledge.redaction import redact_structured
                redacted["content"] = redact_structured(content[:32768], "redact_secrets")[0]
    if "reasoning_content" in message:
        redacted["reasoning_content_preview"] = _preview_redacted(message.get("reasoning_content"))
    if "tool_calls" in message and isinstance(message["tool_calls"], list):
        redacted["tool_calls"] = [
            {
                "id": call.get("id"),
                "type": call.get("type"),
                "function": {
                    "name": (call.get("function") or {}).get("name")
                    if isinstance(call.get("function"), dict)
                    else None,
                    "arguments_preview": _preview_redacted((call.get("function") or {}).get("arguments"))
                    if isinstance(call.get("function"), dict)
                    else None,
                },
            }
            for call in message["tool_calls"]
            if isinstance(call, dict)
        ]
    return redacted


def _redact_value(key: str, value: Any) -> Any:
    if key.lower() in _SECRET_KEYS:
        return "<redacted>"
    value = _redact_media(value)
    if isinstance(value, str):
        return _preview(value)
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value[:20]]
    if isinstance(value, dict):
        return {child_key: _redact_value(child_key, child_value) for child_key, child_value in value.items()}
    return value


def _preview_redacted(value: Any) -> str:
    return _preview(_redact_preview_value(value))


def _redact_preview_value(value: Any) -> Any:
    value = _redact_media(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            from workbench_backend.knowledge.redaction import redact_structured

            redacted = redact_structured(value, "redact_secrets")[0]
            return _SECRET_TEXT_RE.sub("[REDACTED]", redacted)
        return _redact_preview_value(parsed)
    if isinstance(value, list):
        return [_redact_preview_value(item) for item in value[:20]]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            if key.lower() in _SECRET_KEYS:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_preview_value(child)
        return redacted
    return value


def _redact_media(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("data:image/") or value.startswith("data:audio/") or value.startswith("data:video/"):
            return "<embedded-media-redacted>"
        return value
    if isinstance(value, list):
        return [_redact_media(item) for item in value]
    if isinstance(value, dict):
        if value.get("type") in {"image", "image_url", "audio", "input_audio", "video"}:
            redacted = {key: _redact_media(child) for key, child in value.items() if key not in {"image_url", "data", "image", "audio", "video"}}
            redacted["media"] = "<embedded-media-redacted>"
            return redacted
        redacted = {}
        for key, child in value.items():
            if key in {"url", "data"} and isinstance(child, str) and child.startswith("data:"):
                redacted[key] = "<embedded-media-redacted>"
            elif key in {"image_url", "image", "audio", "video"}:
                redacted[key] = "<embedded-media-redacted>"
            else:
                redacted[key] = _redact_media(child)
        return redacted
    return value


def _preview(value: Any) -> str:
    if value is None:
        return ""
    value = _redact_preview_value(value)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, default=str)
    if len(text) <= CAPTURE_TEXT_LIMIT:
        return text
    return f"{text[:CAPTURE_TEXT_LIMIT]}..."
