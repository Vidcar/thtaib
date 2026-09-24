"""Pinned Deep Agents 0.7.16-0.7.18 behavior used by Workbench."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deepagents.backends import FilesystemBackend, StateBackend
from deepagents.backends.protocol import ExecuteResponse
from deepagents.backends.sandbox import _parse_capture_execute_output
from deepagents.backends.utils import create_file_data
from deepagents.middleware.filesystem import FilesystemMiddleware, _scrub_unsupported_multimodal_content
from deepagents.middleware.subagents import TaskToolSchema
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from pydantic import ValidationError


class DeepAgentsReleaseBehaviorTests(unittest.TestCase):
    def test_parallel_mutations_to_one_file_reject_the_later_call(self) -> None:
        calls = [
            {"name": "write_file", "args": {"file_path": "/notes.txt", "content": "first"}, "id": "first"},
            {"name": "edit_file", "args": {"file_path": "/notes.txt", "old_string": "first", "new_string": "second"}, "id": "second"},
        ]
        state = {"messages": [AIMessage(content="", tool_calls=calls)]}
        middleware = FilesystemMiddleware(tool_token_limit_before_evict=None)
        executed: list[str] = []

        def handler(request: ToolCallRequest) -> ToolMessage:
            executed.append(request.tool_call["id"])
            return ToolMessage(content="done", tool_call_id=request.tool_call["id"])

        results = [
            middleware.wrap_tool_call(ToolCallRequest(tool_call=call, tool=None, state=state, runtime=None), handler)
            for call in calls
        ]
        self.assertEqual(executed, ["first"])
        self.assertEqual(results[1].status, "error")
        self.assertIn("parallel file mutations", str(results[1].content))

    def test_task_rejects_unknown_arguments_instead_of_losing_instructions(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            TaskToolSchema.model_validate(
                {"subagent_type": "general-purpose", "description": "Short label", "prompt": "Actual instructions"}
            )
        self.assertIn("Unexpected argument 'prompt'", str(raised.exception))

    def test_missing_capture_metadata_preserves_backend_exit_status(self) -> None:
        backend_result = ExecuteResponse(output="command failed without wrapper metadata", exit_code=7)
        with self.assertLogs("deepagents.backends.sandbox", level="WARNING"):
            parsed = _parse_capture_execute_output(backend_result)
        self.assertFalse(parsed.offloaded)
        self.assertEqual(parsed.response.exit_code, 7)
        self.assertEqual(FilesystemMiddleware._execute_artifact(parsed.response), {"exit_code": 7})

    def test_large_result_preview_discloses_omitted_and_clipped_lines(self) -> None:
        long_line = "X" * 1200
        output = "\n".join([long_line, *(f"line-{number}" for number in range(15))])
        with tempfile.TemporaryDirectory() as directory:
            backend = FilesystemBackend(root_dir=Path(directory))
            middleware = FilesystemMiddleware(backend=backend, tool_token_limit_before_evict=1)
            call = {"name": "echo", "args": {}, "id": "large"}
            request = ToolCallRequest(tool_call=call, tool=None, state={"messages": []}, runtime=None)
            preview = middleware.wrap_tool_call(request, lambda _: ToolMessage(content=output, tool_call_id="large"))
            self.assertIn("omitted lines in the middle", preview.content)
            self.assertIn("lines longer than 1000 characters", preview.content)
            self.assertIn("... [6 lines truncated] ...", preview.content)
            self.assertNotIn(long_line, preview.content)
            self.assertTrue((Path(directory) / "large_tool_results" / "large").is_file())

    def test_inline_file_blocks_require_supported_mime_type(self) -> None:
        pdf = {"type": "file", "mime_type": "application/pdf", "base64": "JVBERi0="}
        archive = {"type": "file", "mime_type": "application/zip", "base64": "UEs="}
        source = ToolMessage(content=[pdf, archive], tool_call_id="read-document", additional_kwargs={"read_file_path": "/notes.zip"})
        scrubbed = _scrub_unsupported_multimodal_content([source], model=None)[0]
        self.assertEqual(scrubbed.content_blocks[0]["mime_type"], "application/pdf")
        self.assertEqual(scrubbed.content_blocks[1]["type"], "text")
        self.assertIn("application/zip", scrubbed.content_blocks[1]["text"])

    def test_state_file_sizes_are_utf8_bytes(self) -> None:
        backend = StateBackend()
        content = "Aé🧠"
        files = {"/unicode.txt": create_file_data(content)}
        with patch.object(backend, "_read_files", return_value=files):
            listing = backend.ls("/")
            matches = backend.glob("*.txt")
        size = len(content.encode("utf-8"))
        self.assertEqual(listing.entries[0]["size"], size)
        self.assertEqual(matches.matches[0]["size"], size)


if __name__ == "__main__":
    unittest.main()
