"""Scripted LangChain chat model for harness unit tests. Not an inference engine."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, ClassVar

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

# Module-level hold survives LangChain/Pydantic copies of the model instance.
GENERATE_HOLD: threading.Event | None = None
# Set when _next_message begins waiting on the installed hold.
GENERATE_HOLD_ENTERED: threading.Event | None = None
# Flattened model-bound prompts. Survives LangChain copies of the instance.
RECEIVED_PROMPTS: list[str] = []
# Optional HTTP-capture sink. Appended during _generate so Issue #57
# per-call observation sees the payload for this model call.
CAPTURE_SINK: list[dict[str, Any]] | None = None
CAPTURE_PAYLOAD: dict[str, Any] | None = None


def reset_received_prompts() -> None:
    RECEIVED_PROMPTS.clear()


def set_capture_sink(
    sink: list[dict[str, Any]] | None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Install or clear the generate-time HTTP capture used by LangChain copies."""

    global CAPTURE_SINK, CAPTURE_PAYLOAD
    CAPTURE_SINK = sink
    CAPTURE_PAYLOAD = payload


def _message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def set_generate_hold(hold: threading.Event | None) -> None:
    """Install or clear the generate hold used by LangChain copies."""

    global GENERATE_HOLD, GENERATE_HOLD_ENTERED
    GENERATE_HOLD = hold
    ScriptedChatModel.generate_hold = hold
    GENERATE_HOLD_ENTERED = threading.Event() if hold is not None else None


def wait_for_generate_hold(*, timeout: float = 10.0) -> None:
    """Block until the scripted model is waiting on the installed generate hold."""

    entered = GENERATE_HOLD_ENTERED
    if entered is None:
        raise RuntimeError("set_generate_hold() must be installed before waiting")
    if not entered.wait(timeout=timeout):
        raise TimeoutError("scripted model did not enter generate hold")


def _resolve_generate_hold(instance_hold: threading.Event | None) -> threading.Event | None:
    """Prefer a hold that is still blocking; ignore leftover already-set events."""

    candidates = (GENERATE_HOLD, ScriptedChatModel.generate_hold, instance_hold)
    unset = next((item for item in candidates if item is not None and not item.is_set()), None)
    if unset is not None:
        return unset
    return next((item for item in candidates if item is not None), None)


class ScriptedChatModel(BaseChatModel):
    """Returns a fixed sequence of AI messages, including optional tool calls."""

    generate_hold: ClassVar[threading.Event | None] = None

    _script: list[AIMessage] = PrivateAttr(default_factory=list)
    _index: int = PrivateAttr(default=0)
    _delay_s: float = PrivateAttr(default=0.0)
    _hold: threading.Event | None = PrivateAttr(default=None)
    _bound_tools: list[Any] = PrivateAttr(default_factory=list)

    def __init__(
        self,
        script: list[AIMessage],
        *,
        delay_s: float = 0.0,
        hold: threading.Event | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._script = list(script)
        self._index = 0
        self._delay_s = delay_s
        self._hold = hold
        self._bound_tools = []

    @property
    def bound_tools(self) -> list[Any]:
        return self._bound_tools

    @property
    def _llm_type(self) -> str:
        return "scripted-workbench"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> ScriptedChatModel:
        self._bound_tools = list(tools)
        return self

    def _next_message(self) -> AIMessage:
        hold = _resolve_generate_hold(self._hold)
        if hold is not None:
            entered = GENERATE_HOLD_ENTERED
            if entered is not None:
                entered.set()
            hold.wait(timeout=30)
        if self._delay_s:
            time.sleep(self._delay_s)
        if self._index >= len(self._script):
            return AIMessage(content="done")
        message = self._script[self._index]
        self._index += 1
        return message

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        RECEIVED_PROMPTS.append("\n".join(_message_text(item) for item in messages))
        if CAPTURE_SINK is not None and CAPTURE_PAYLOAD is not None:
            CAPTURE_SINK.append(dict(CAPTURE_PAYLOAD))
        message = self._next_message()
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return await asyncio.to_thread(self._generate, messages, stop=stop, run_manager=run_manager, **kwargs)
