"""MOD-005: narrow LangChain adapter to a model-manager deployment endpoint.

The adapter talks to an existing OpenAI-compatible chat endpoint. It does
not load weights and does not start, stop, or supervise an inference
process. llama.cpp owns tokenisation, templates and actual context.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from langchain_openai import ChatOpenAI

from workbench_backend.errors import HarnessError
from workbench_backend.inference.schemas import Deployment, SettingsBag

# Transport timeout only — not a product task budget (AGT-003).
DEFAULT_ADAPTER_TIMEOUT = 120.0

DIRECT_CHAT_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "stop",
)

EXTRA_BODY_KEYS = (
    "top_k",
    "min_p",
    "typical_p",
    "repeat_penalty",
)


class RecordingTransport(httpx.BaseTransport):
    """Records the chat-completions JSON the adapter actually sends."""

    def __init__(
        self,
        sink: list[dict[str, Any]],
        inner: httpx.BaseTransport | None = None,
    ) -> None:
        self.sink = sink
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            self.sink.append(
                {
                    "url": str(request.url),
                    "method": request.method,
                    "body": _decode_body(request.content),
                }
            )
        return self.inner.handle_request(request)


def chat_model_for_deployment(
    deployment: Deployment,
    *,
    capture_sink: list[dict[str, Any]] | None = None,
    timeout: float = DEFAULT_ADAPTER_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> ChatOpenAI:
    """Return a LangChain chat model aimed only at ``deployment.endpoint``.

    Raises if the deployment has no endpoint. Never starts a managed
    llama-server or any other inference process.
    """

    endpoint = (deployment.endpoint or "").rstrip("/")
    if not endpoint:
        raise HarnessError(
            "Deployment has no OpenAI-compatible endpoint. Start or attach "
            "a deployment first; the adapter does not start inference.",
            code="no_endpoint",
            status_code=409,
        )

    per_request = deployment.settings.per_request
    kwargs = _direct_kwargs(per_request)
    extra_body = _extra_body(per_request)
    model_name = str(deployment.applied_startup.get("alias") or "local")
    client = http_client
    if client is None and capture_sink is not None:
        client = httpx.Client(
            transport=RecordingTransport(capture_sink),
            timeout=timeout,
        )
    elif client is None:
        client = httpx.Client(timeout=timeout)

    return ChatOpenAI(
        model=model_name,
        base_url=endpoint,
        api_key="not-required",
        use_responses_api=False,
        http_client=client,
        extra_body=extra_body or None,
        **kwargs,
    )


def adapter_target(deployment: Deployment) -> dict[str, Any]:
    """Describe the adapter target without creating a model or a process."""

    return {
        "deployment_id": deployment.id,
        "endpoint": deployment.endpoint,
        "starts_inference": False,
        "engine_owner": "llama.cpp / connected OpenAI-compatible endpoint",
        "adapter": "langchain-openai ChatOpenAI chat-completions",
        "unsupported": list(deployment.settings.per_request.unsupported),
        "unverified": list(deployment.settings.per_request.unverified),
    }


def _direct_kwargs(bag: SettingsBag) -> dict[str, Any]:
    return {key: bag.applied[key] for key in DIRECT_CHAT_KEYS if key in bag.applied}


def _extra_body(bag: SettingsBag) -> dict[str, Any]:
    return {key: bag.applied[key] for key in EXTRA_BODY_KEYS if key in bag.applied}


def _decode_body(content: bytes) -> Any:
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"_raw": content.decode("utf-8", errors="replace")}
