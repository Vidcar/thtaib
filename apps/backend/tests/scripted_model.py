"""Scripted LangChain chat model for harness unit tests. Not an inference engine."""

from __future__ import annotations

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
        hold = GENERATE_HOLD or ScriptedChatModel.generate_hold or self._hold
        if hold is not None:
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
        message = self._next_message()
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
