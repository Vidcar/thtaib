"""Native compaction recovers retained-image pressure using canonical indices."""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import FileData, ReadResult
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.context import BudgetedSummarizationMiddleware, token_counter_for_model
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.probes import _image_fixture
from workbench_backend.inference.telemetry import current_request_purpose


class VisualContextCompactionTests(unittest.TestCase):
    def test_native_compaction_recovers_aggregate_image_pressure_sync_and_async(self) -> None:
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                self._exercise(asynchronous=asynchronous)

    def _exercise(self, *, asynchronous: bool) -> None:
        paths = ["/captures/asset_" + digit * 32 + ".png" for digit in ("a", "b")]
        images = [_image_fixture(colour).partition(",")[2] for colour in ("red", "blue")]
        image_limit = max(len(base64.b64decode(image)) for image in images) + 3
        self.assertGreater(sum(len(image) * 3 // 4 for image in images), image_limit)
        reads: list[str] = []

        class CaptureBackend:
            image_inputs_allowed = True

            def read(self, path: str) -> ReadResult:
                reads.append(path)
                index = [saved.removeprefix("/captures") for saved in paths].index(path)
                return ReadResult(file_data=FileData(content=images[index], encoding="base64"))

        class InspectModel(ScriptedChatModel):
            seen: ClassVar[list[tuple[str, list]]] = []

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                type(self).seen.append((current_request_purpose(), list(messages)))
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        captures = iter(paths)

        @tool
        def browser_take_screenshot() -> str:
            """Capture an immutable page image and return its retained reference."""
            return "Screenshot captured.\nSaved screenshot: " + next(captures)

        now = utc_now()
        model = InspectModel([
            AIMessage(content="", tool_calls=[{"name": "browser_take_screenshot", "args": {}, "id": "shot-one"}]),
            AIMessage(content="", tool_calls=[{"name": "browser_take_screenshot", "args": {}, "id": "shot-two"}]),
            AIMessage(content="Earlier capture retained at " + paths[0]),
            AIMessage(content="DONE"),
        ], profile={"image_inputs": True, "image_tool_message": True, "max_input_tokens": 90000})
        scratch = Path(__file__).resolve().parents[3] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="visual-compaction-", dir=scratch) as directory:
            backend = FilesystemBackend(root_dir=directory, virtual_mode=True)
            run = AgentRun(id="visual-compaction", deployment_id="visual-fixture", task="Inspect two captures",
                enabled_tools=["browser_take_screenshot"], presented_tools=["browser_take_screenshot"],
                project_path=directory, capture_routes_enabled=True, created_at=now, updated_at=now)
            workbench = WorkbenchHarnessMiddleware(run, capture_backend=CaptureBackend())
            summarization = BudgetedSummarizationMiddleware(model=model, backend=backend,
                allowed_tools={"browser_take_screenshot"}, trigger=("tokens", 100000), keep=("messages", 2),
                token_counter=token_counter_for_model(model, message_projection=workbench.tool_image_messages_for_count),
                request_preparer=workbench._with_outline, trim_tokens_to_summarize=None)
            agent = create_deep_agent(model=model, tools=[browser_take_screenshot], backend=backend,
                system_prompt="Inspect each capture.", middleware=[summarization, workbench], checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "visual-compaction"}}
            payload = {"messages": [HumanMessage(content="Capture two pages, then finish.")]}

            async def exercise():
                result = await agent.ainvoke(payload, config=config)
                return result, (await agent.aget_state(config)).values

            with patch("workbench_backend.agents.middleware.MAX_TOOL_IMAGE_BYTES_PER_REQUEST", image_limit):
                if asynchronous:
                    result, checkpoint = asyncio.run(exercise())
                else:
                    result = agent.invoke(payload, config=config)
                    checkpoint = agent.get_state(config).values

            event = checkpoint["_summarization_event"]
            self.assertEqual(event["cutoff_index"], 3)
            canonical = checkpoint["messages"]
            self.assertEqual(canonical[3].tool_calls[0]["id"], "shot-two")
            self.assertEqual(canonical[4].tool_call_id, "shot-two")
            retained = [message for message in canonical if isinstance(message, ToolMessage)]
            self.assertEqual([message.tool_call_id for message in retained], ["shot-one", "shot-two"])
            self.assertTrue(all(path in message.content for path, message in zip(paths, retained, strict=True)))
            self.assertEqual(result["messages"][-1].content, "DONE")
            summary_calls = [messages for purpose, messages in InspectModel.seen if purpose == "summary"]
            work_calls = [messages for purpose, messages in InspectModel.seen if purpose == "work"]
            self.assertEqual(len(summary_calls), 1)
            self.assertEqual(len(work_calls), 3, "Rejected hydration must not dispatch a fourth work request")
            self.assertIn(paths[0], json.dumps([message.model_dump() for message in summary_calls[0]]))
            self.assertNotIn(paths[1], json.dumps([message.model_dump() for message in summary_calls[0]]))
            final_images = [block["base64"] for message in work_calls[-1] for block in message.content_blocks
                            if block["type"] == "image"]
            self.assertEqual(final_images, [images[1]])
            serialized_checkpoint = json.dumps(checkpoint, default=str)
            self.assertTrue(all(image not in serialized_checkpoint for image in images))
            self.assertEqual(sum(isinstance(message, HumanMessage) for message in canonical), 1,
                             "Derived visual messages must not shift canonical checkpoint indices")
            offloaded = backend.download_files([event["file_path"]])[0]
            self.assertIsNone(offloaded.error)
            self.assertIn(paths[0], offloaded.content.decode())
            self.assertTrue(all(image not in offloaded.content.decode() for image in images))


if __name__ == "__main__":
    unittest.main()
