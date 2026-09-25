"""One native media result is retained before state and attached only to its next request."""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from deepagents import create_deep_agent
from deepagents.backends.protocol import FileData, ReadResult
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL
from workbench_backend.agents.harness_backend import BoundedImageFilesystemBackend
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.probes import _image_fixture


class _Assets:
    def __init__(self) -> None:
        self.calls = []

    def retain_tool_image(self, run, content, **kwargs):
        self.calls.append((run.id, content, kwargs))
        return (SimpleNamespace(id="asset_" + "a" * 32, sha256="fixed-hash"),
            "/captures/asset_" + "a" * 32 + ".png")


class _CaptureBackend:
    def __init__(self, image_data: str) -> None:
        self.image_data = image_data
        self.reads = []

    def read(self, path: str) -> ReadResult:
        self.reads.append(path)
        return ReadResult(file_data=FileData(content=self.image_data, encoding="base64"))


def _run() -> AgentRun:
    now = utc_now()
    return AgentRun(id="visual-run", deployment_id="vision-model", task="Inspect an image",
        enabled_tools=["read_file"], presented_tools=["read_file"],
        source_surface="chat", project_path="C:/fixture-project",
        capture_routes_enabled=True, created_at=now, updated_at=now)


class VisualMiddlewareTests(unittest.TestCase):
    def _setup(self):
        encoded = _image_fixture("red").partition(",")[2]
        assets = _Assets()
        captures = _CaptureBackend(encoded)
        middleware = WorkbenchHarnessMiddleware(_run(), asset_service=assets,
            capture_backend=captures)
        result = ToolMessage(content_blocks=[{"type": "image", "base64": encoded,
            "mime_type": "image/png"}], name="read_file", tool_call_id="image-call",
            additional_kwargs={"read_file_path": "/view.png",
                "read_file_media_type": "image/png"})
        call = SimpleNamespace(tool_call={"name": "read_file", "args": {"file_path": "/view.png"},
            "id": "image-call"})
        return encoded, assets, captures, middleware, result, call

    def test_offload_preserves_tool_pair_and_rehydrates_only_current_batch(self) -> None:
        encoded, assets, captures, middleware, original, call = self._setup()
        retained = middleware.wrap_tool_call(call, lambda _: original)
        self.assertEqual(retained.tool_call_id, "image-call")
        self.assertEqual(retained.additional_kwargs["capture_path"],
            "/captures/asset_" + "a" * 32 + ".png")
        self.assertNotIn(encoded, json.dumps(retained.model_dump()))
        self.assertEqual(assets.calls[0][0], "visual-run")
        preceding = [
            HumanMessage(content="Inspect this."),
            AIMessage(content="", tool_calls=[
                {"name": "read_file", "args": {"file_path": "/view.png"}, "id": "image-call"},
                {"name": "echo", "args": {"text": "done"}, "id": "text-call"},
            ]),
            retained,
            ToolMessage(content="done", name="echo", tool_call_id="text-call"),
        ]
        request = ModelRequest(model=ScriptedChatModel([AIMessage(content="red")]),
            messages=preceding, tools=[], model_settings={})
        projected = middleware._with_current_tool_images(request)
        self.assertEqual(projected.messages[:-1], preceding)
        self.assertEqual(projected.messages[-1].content_blocks[-1]["type"], "image")
        self.assertEqual(projected.messages[-1].content_blocks[-1]["base64"], encoded)
        self.assertEqual(captures.reads, ["/asset_" + "a" * 32 + ".png"])
        next_turn = request.override(messages=[*preceding, HumanMessage(content="Continue")])
        self.assertEqual(middleware._with_current_tool_images(next_turn).messages,
            next_turn.messages)

    def test_async_tool_hook_offloads_before_return(self) -> None:
        encoded, assets, _, middleware, original, call = self._setup()

        async def exercise() -> ToolMessage:
            async def handler(_):
                return original
            return await middleware.awrap_tool_call(call, handler)

        retained = asyncio.run(exercise())
        self.assertNotIn(encoded, json.dumps(retained.model_dump()))
        self.assertEqual(len(assets.calls), 1)

    def test_worker_tool_hooks_carry_capture_call_id(self) -> None:
        _, _, _, middleware, _, _ = self._setup()
        call = SimpleNamespace(tool_call={"name": "browser_take_screenshot", "args": {}, "id": "call_shot"})
        self.assertEqual(middleware._wrap_tool_call(call, lambda _: CURRENT_TOOL_CALL.get()), "call_shot")
        self.assertEqual(CURRENT_TOOL_CALL.get(), "")

        async def exercise():
            async def handler(_):
                return CURRENT_TOOL_CALL.get()
            return await middleware._awrap_tool_call(call, handler)

        self.assertEqual(asyncio.run(exercise()), "call_shot")
        self.assertEqual(CURRENT_TOOL_CALL.get(), "")

    def test_rehydrated_images_have_an_aggregate_request_bound(self) -> None:
        _, _, _, middleware, original, call = self._setup()
        retained = middleware.wrap_tool_call(call, lambda _: original)
        request = ModelRequest(model=ScriptedChatModel([AIMessage(content="red")]),
            messages=[
                AIMessage(content="", tool_calls=[
                    {"name": "read_file", "args": {"file_path": "/view.png"}, "id": "image-call"},
                ]),
                retained,
            ], tools=[], model_settings={})
        with patch("workbench_backend.agents.middleware.MAX_TOOL_IMAGE_BYTES_PER_REQUEST", 1):
            with self.assertRaises(HarnessError) as raised:
                middleware._with_current_tool_images(request)
        self.assertEqual(raised.exception.code, "tool_images_too_large")

    def test_native_graph_checkpoint_keeps_reference_and_next_model_sees_image(self) -> None:
        encoded, assets, captures, middleware, _, _ = self._setup()
        class InspectModel(ScriptedChatModel):
            seen: ClassVar[list] = []
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                type(self).seen.append(list(messages))
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "view.png").write_bytes(base64.b64decode(encoded))
            middleware.run.project_path = directory
            model = InspectModel([
                AIMessage(content="", tool_calls=[{"name": "read_file",
                    "args": {"file_path": "/view.png"}, "id": "image-call"}]),
                AIMessage(content="red"),
            ], profile={"image_inputs": True, "image_tool_message": True})
            agent = create_deep_agent(model=model, system_prompt="Inspect the project image.",
                backend=BoundedImageFilesystemBackend(root_dir=directory,
                    virtual_mode=True, image_inputs_allowed=True),
                middleware=[middleware], checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "checkpoint-image-test"}}
            result = agent.invoke({"messages": [HumanMessage(content="Inspect /view.png")]}, config=config)
            checkpoint = agent.get_state(config).values
        self.assertEqual(result["messages"][-1].content, "red")
        self.assertEqual(len(assets.calls), 1)
        retained = [message for message in checkpoint["messages"]
            if isinstance(message, ToolMessage) and message.name == "read_file"]
        self.assertEqual(len(retained), 1)
        self.assertIn("/captures/asset_", retained[0].content)
        self.assertNotIn(encoded, json.dumps(checkpoint, default=str))
        self.assertEqual(captures.reads, ["/asset_" + "a" * 32 + ".png"])
        self.assertEqual(len(InspectModel.seen), 2)
        second_request = InspectModel.seen[1]
        self.assertEqual(second_request[-2].tool_call_id, "image-call")
        self.assertIsInstance(second_request[-1], HumanMessage)
        self.assertEqual(second_request[-1].content_blocks[-1]["base64"], encoded)
