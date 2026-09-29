"""Canonical capture references reconstruct stable active visual context."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import tempfile
import unittest
import zlib
import httpx
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from deepagents import create_deep_agent
from deepagents.backends.protocol import FileData, ReadResult
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.effective_setup import EffectiveSetup
from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.context import token_counter_for_model
from workbench_backend.agents.harness_backend import BoundedImageFilesystemBackend
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.errors import HarnessError
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.adapter import chat_model_for_deployment
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.image_validation import CANNOT_READ_IMAGE
from workbench_backend.inference.probes import _image_fixture
from workbench_backend.inference.schemas import Deployment, ServerProperties
from workbench_backend.inference.settings import resolve_bags


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
    def assert_tool_image_response(self, message, encoded):
        self.assertIsInstance(message, HumanMessage)
        blocks = message.content_blocks
        self.assertEqual(blocks[0], {"type": "text", "text": "<tool_response>\n"})
        self.assertEqual(blocks[-1], {"type": "text", "text": "\n</tool_response>"})
        images = [block for block in blocks if block["type"] == "image"]
        self.assertEqual(len(images), 1, "Only the requested image is delivered")
        self.assertEqual(images[0]["base64"], encoded)
        self.assertEqual(images[0]["mime_type"], "image/png")

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

    def test_offload_preserves_tool_pair_and_rehydrates_historical_batches(self) -> None:
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
        self.assert_tool_image_response(projected.messages[-1], encoded)
        self.assertNotIn(encoded, json.dumps([message.model_dump() for message in preceding]))
        self.assertEqual(captures.reads, ["/asset_" + "a" * 32 + ".png"])
        next_turn = request.override(messages=[*preceding, HumanMessage(content="Continue")])
        self.assertEqual(middleware._with_current_tool_images(next_turn).messages,
            [*projected.messages, next_turn.messages[-1]])

        continued = request.override(messages=[*preceding,
            AIMessage(content="red", tool_calls=[{"name": "echo", "args": {}, "id": "next"}]),
            ToolMessage(content="continued", name="echo", tool_call_id="next")])
        self.assertEqual(middleware._with_current_tool_images(continued).messages,
            [*projected.messages, *continued.messages[len(preceding):]])

    def test_native_counter_hydrates_actual_visual_input_without_probing_or_checkpoint_bytes(self) -> None:
        encoded, _, captures, middleware, original, call = self._setup()
        retained = middleware.wrap_tool_call(call, lambda _: original)
        messages = [HumanMessage(content="Inspect the retained image"),
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "image-call"}]), retained]
        checkpoint = [message.model_dump() for message in messages]
        counts, generations = [], []
        def respond(request):
            body = json.loads(request.content)
            if request.url.path.endswith("/chat/completions/input_tokens"):
                counts.append(body)
                return httpx.Response(200, json={"input_tokens": 317})
            self.assertTrue(request.url.path.endswith("/chat/completions"))
            generations.append(body)
            return httpx.Response(200, json={"id": "visual-count", "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "red"}, "finish_reason": "stop"}]})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        now = utc_now()
        deployment = Deployment(id="vision-model", display_name="Vision count fixture", scope="managed", status="running",
            endpoint="http://127.0.0.1:9/v1", created_at=now, updated_at=now,
            server_props=ServerProperties(fetched=now, source_url="fixture", model_alias="vision-model", n_ctx=4096))
        model = chat_model_for_deployment(deployment, http_client=client)
        middleware.tool_image_preparer = lambda: self.fail("Counting cannot run capability inference")
        try:
            count = token_counter_for_model(model, message_projection=middleware.tool_image_messages_for_count)
            self.assertEqual(count(messages, tools=[]), 317)
            self.assertEqual(model.input_count_basis, "native")
            self.assertEqual(captures.reads, ["/asset_" + "a" * 32 + ".png"])
            self.assertEqual(generations, [], "Counting must not run model generation or a capability probe")
            self.assertEqual(len(counts), 1)
            body = counts[0]
            self.assertEqual(body["messages"][2]["tool_call_id"], "image-call")
            self.assertEqual(body["messages"][3]["role"], "user")
            images = [block for block in body["messages"][3]["content"] if block["type"] == "image_url"]
            self.assertEqual(images, [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}}])
            actual_messages = middleware.tool_image_messages_for_count(messages)
            self.assertEqual(model.invoke(actual_messages).content, "red")
            wire = {**generations[0], "stream": False}
            wire.pop("stream_options", None)
            self.assertEqual(body, wire, "Native counting must use the same hydrated input that generation sends")
            self.assertEqual([message.model_dump() for message in messages], checkpoint)
            self.assertNotIn(encoded, json.dumps(checkpoint))
            self.assertEqual(middleware.tool_image_messages_for_count([HumanMessage(content="Compacted history")]),
                [HumanMessage(content="Compacted history")])
        finally:
            model.close()
            client.close()

    def test_disabled_capture_context_cannot_probe_historical_images(self) -> None:
        _, _, _, middleware, original, call = self._setup()
        retained = middleware.wrap_tool_call(call, lambda _: original)
        request = ModelRequest(model=ScriptedChatModel([]), messages=[retained], tools=[], model_settings={})
        middleware.tool_image_preparer = lambda: self.fail("Disabled capture routes ran a probe")
        middleware.run.capture_routes_enabled = False
        self.assertIs(middleware._with_current_tool_images(request), request)
        middleware.run.capture_routes_enabled = True
        middleware.capture_backend = None
        self.assertIs(middleware._with_current_tool_images(request), request)

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
        self.assert_tool_image_response(second_request[-1], encoded)
        self.assertEqual([message.content for message in checkpoint["messages"]
            if isinstance(message, HumanMessage)], ["Inspect /view.png"],
            "Synthetic tool-image context must not become a retained user turn")

    def _exercise_late_screenshot_probe(self, *, asynchronous: bool, status: str, desktop: bool = False) -> None:
        # A green/yellow capture is distinct from both red/blue probe fixtures.
        def chunk(kind: bytes, content: bytes) -> bytes:
            return (struct.pack(">I", len(content)) + kind + content
                + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff))
        image = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\xff\x00\xff\xff\x00"))
            + chunk(b"IEND", b""))
        encoded = base64.b64encode(image).decode()
        path = "/captures/asset_" + "a" * 32 + ".png"
        page_text = (json.dumps({"path": path, "width": 2, "height": 1}) if desktop else
            "Screenshot captured from https://news.example.\n" + '- heading "City news"\n' + f"Saved screenshot: {path}")
        tool_name = "desktop_screenshot" if desktop else "browser_take_screenshot"
        now = utc_now()
        deployment = Deployment(id="vision-model", display_name="Vision fixture",
            scope="connected", status="running", endpoint="http://127.0.0.1:9/v1",
            settings=resolve_bags(per_request={"temperature": 0.8, "max_tokens": 11}),
            server_props=ServerProperties(fetched=now,
                source_url="http://127.0.0.1:9/props", modalities={"vision": True}, n_ctx=4096),
            created_at=now, updated_at=now)
        selected = resolve_bags(per_request={"temperature": 0.2, "max_tokens": 37})
        run = _run()
        run.presented_tools = run.enabled_tools = [tool_name]
        run.effective_setup = EffectiveSetup(selected_deployment_id=deployment.id,
            loaded_deployment_id=deployment.id, bags=selected, system_prompt="Inspect the page.")
        setup_before = run.effective_setup.model_dump(mode="json")
        manager = SimpleNamespace(get_deployment=lambda _id: deployment.model_copy(deep=True))
        harness = HarnessService(lambda: manager)
        captures = _CaptureBackend(encoded)
        probe_calls = []

        def record_probe(_manager, deployment_id, request):
            self.assertIs(_manager, manager)
            self.assertEqual(deployment_id, deployment.id)
            self.assertEqual(request.per_request, selected.per_request.applied,
                "Capability evidence must apply to the selected request settings")
            probe_calls.append(request.capability)
            deployment.capability_evidence.append({"capability": request.capability,
                "status": status, "fingerprint": setup_fingerprint(deployment, request.per_request)})

        class InspectModel(ScriptedChatModel):
            seen: ClassVar[list] = []
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                type(self).seen.append(list(messages))
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        initial_profile = {"image_inputs": False, "image_tool_message": False,
            "max_input_tokens": 17777, "max_output_tokens": 37, "tool_calling": True}
        model = InspectModel([
            AIMessage(content="", tool_calls=[{"name": tool_name,
                "args": {}, "id": "fresh-shot"}]), AIMessage(content="Page inspected."),
        ], profile=initial_profile.copy())

        @tool(tool_name)
        def browser_take_screenshot() -> str:
            """Capture the current browser page and return its retained path."""
            return page_text

        def images_allowed():
            from workbench_backend.inference.adapter import image_model_profile
            profile = image_model_profile(manager.get_deployment(deployment.id), selected.per_request)
            return profile["image_inputs"] and profile["image_tool_message"]

        captures.image_inputs_allowed = images_allowed
        middleware = WorkbenchHarnessMiddleware(run, capture_backend=captures,
            tool_image_preparer=lambda: harness.prepare_screenshot_reading(run, model=model))
        agent = create_deep_agent(model=model, system_prompt="Inspect the page.",
            tools=[browser_take_screenshot], middleware=[middleware], checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "fresh-screenshot"}}
        payload = {"messages": [HumanMessage(content="Inspect the current page.")]}

        async def exercise():
            result = await agent.ainvoke(payload, config=config)
            return result, (await agent.aget_state(config)).values

        with patch("workbench_backend.inference.probes.run_capability_probe", side_effect=record_probe):
            if asynchronous:
                result, checkpoint = asyncio.run(exercise())
            else:
                result = agent.invoke(payload, config=config)
                checkpoint = agent.get_state(config).values
        self.assertEqual(result["messages"][-1].content, "Page inspected.")
        self.assertEqual(len(InspectModel.seen), 2)
        first_request, second_request = InspectModel.seen
        self.assertFalse(any(block["type"] == "image" for message in first_request
            for block in message.content_blocks))
        self.assertEqual(second_request[-2].tool_call_id, "fresh-shot")
        self.assertEqual(second_request[-2].content, page_text)
        if status == "passed":
            self.assertEqual(probe_calls, ["image", "tool_image"])
            self.assert_tool_image_response(second_request[-1], encoded)
            self.assertEqual(captures.reads, ["/asset_" + "a" * 32 + ".png"])
        else:
            self.assertEqual(probe_calls, ["image"])
            self.assertIn(CANNOT_READ_IMAGE, str(second_request[-1].content))
            self.assertFalse(any(block["type"] == "image" for message in second_request
                for block in message.content_blocks))
            self.assertEqual(captures.reads, [])
        expected_profile = {**initial_profile, "image_inputs": status == "passed",
            "image_tool_message": status == "passed"}
        self.assertEqual(model.profile, expected_profile,
            "Only media fields change; the active context budget and other capabilities survive")
        self.assertEqual(run.effective_setup.model_dump(mode="json"), setup_before)
        retained = [message for message in checkpoint["messages"] if isinstance(message, ToolMessage)]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].tool_call_id, "fresh-shot")
        self.assertEqual(retained[0].content, page_text)
        self.assertNotIn(encoded, json.dumps(checkpoint, default=str))
        self.assertEqual([message.content for message in checkpoint["messages"]
            if isinstance(message, HumanMessage)], ["Inspect the current page."],
            "Request-only screenshot context must not become a retained user turn")

    def test_fresh_screenshot_probe_refreshes_same_sync_graph_request(self) -> None:
        self._exercise_late_screenshot_probe(asynchronous=False, status="passed")

    def test_fresh_screenshot_probe_refreshes_same_async_graph_request(self) -> None:
        self._exercise_late_screenshot_probe(asynchronous=True, status="passed")

    def test_deferred_windows_capture_json_runs_native_image_probe_and_hydrates(self) -> None:
        self._exercise_late_screenshot_probe(asynchronous=True, status="passed", desktop=True)

    def test_failed_or_inconclusive_probe_keeps_page_text_through_native_graph(self) -> None:
        for asynchronous in (False, True):
            for status in ("failed", "inconclusive"):
                with self.subTest(asynchronous=asynchronous, status=status):
                    self._exercise_late_screenshot_probe(asynchronous=asynchronous, status=status)

    def test_unverified_screenshot_keeps_page_text_and_withholds_pixels(self) -> None:
        encoded, _, captures, middleware, _, _ = self._setup()
        path = "/captures/asset_" + "a" * 32 + ".png"
        captures.image_inputs_allowed = False
        middleware.tool_image_preparer = lambda: False
        shot = ToolMessage(
            content=f"Screenshot captured from https://news.example.\n- heading \"City news\"\nSaved screenshot: {path}",
            name="browser_take_screenshot", tool_call_id="shot",
        )
        request = ModelRequest(model=ScriptedChatModel([AIMessage(content="ok")]),
            messages=[
                AIMessage(content="", tool_calls=[{"name": "browser_take_screenshot", "args": {}, "id": "shot"}]),
                shot,
            ], tools=[], model_settings={})
        projected = middleware._with_current_tool_images(request)
        self.assertEqual(projected.messages[-2], shot)
        self.assertEqual(projected.messages[-1].content, f"<tool_response>\n{CANNOT_READ_IMAGE}\n</tool_response>")
        self.assertFalse(any(block["type"] == "image" for message in projected.messages
            for block in message.content_blocks))
        self.assertNotIn(encoded, json.dumps([message.model_dump() for message in projected.messages]))
        self.assertNotIn("probe", projected.messages[-1].content)
        self.assertEqual(captures.reads, [])
        state = {"ready": False}
        captures.image_inputs_allowed = lambda: state["ready"]
        middleware.tool_image_preparer = lambda: state.__setitem__("ready", True) or True
        delivered = middleware._with_current_tool_images(request)
        self.assert_tool_image_response(delivered.messages[-1], encoded)
        self.assertEqual(delivered.messages[-2], shot, "Original page text and capture reference remain paired")
        self.assertEqual(captures.reads, ["/" + path.removeprefix("/captures/")])
