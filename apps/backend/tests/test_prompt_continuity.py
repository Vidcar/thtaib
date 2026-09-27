"""Run-start outline stability and native context counting boundaries."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from deepagents.middleware.summarization import SUMMARIZATION_EVENT_KEY

from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.context import ContextObservation, BudgetedSummarizationMiddleware, count_context_tokens
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.inference.ids import utc_now


class _ContextModel(ScriptedChatModel):
    def project_context_payload(self, messages, **kwargs):
        return {"messages": messages}


class PromptContinuityTests(unittest.TestCase):
    def test_outline_survives_edit_pressure_and_reconstructed_run(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "workbench_backend.agents.project_outline.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=b""),
        ):
            path = Path(directory) / "main.py"
            path.write_text("def original():\n    return 1\n")
            run = AgentRun(id="outline", deployment_id="model", task="Read main.py",
                project_path=directory, enabled_tools=["read_file"], presented_tools=["read_file"],
                context_observation=ContextObservation(usable_input_tokens=10000),
                created_at=utc_now(), updated_at=utc_now())
            model = _ContextModel([])
            request = ModelRequest(model=model, messages=[HumanMessage(content="Read main.py")],
                system_message=SystemMessage(content="Stable instructions"), tools=[], model_settings={})
            middleware = WorkbenchHarnessMiddleware(run)
            first = middleware._with_outline(request)
            self.assertIn("original", first.system_message.content)
            self.assertIn("Initial project snapshot", first.system_message.content)
            path.write_text("def renamed():\n    return 2\n")
            middleware.outline_cache.invalidate(directory)
            pressure = request.override(messages=[*request.messages, AIMessage(content="x" * 60000)])
            with patch.object(middleware.outline_cache, "build", side_effect=AssertionError("Snapshot rebuilt")):
                self.assertEqual(middleware._with_outline(pressure).system_message, first.system_message)
            restored = WorkbenchHarnessMiddleware(AgentRun.model_validate_json(run.model_dump_json()))
            self.assertEqual(restored._with_outline(pressure).system_message, first.system_message)
            self.assertLessEqual(run.project_outline["estimated_tokens"], 1024)
            fresh_run = run.model_copy(update={"project_outline": None}, deep=True)
            fresh = WorkbenchHarnessMiddleware(fresh_run)._with_outline(request)
            self.assertIn("renamed", fresh.system_message.content)
            self.assertNotIn("original", fresh.system_message.content)

    def test_native_budget_sees_initial_outline_without_duplicate_insertion(self):
        run = AgentRun(id="outline", deployment_id="model", task="Read", project_outline={
            "snapshot_text": "Initial project snapshot\nmain.py: original", "included": True},
            enabled_tools=[], presented_tools=[],
            created_at=utc_now(), updated_at=utc_now())
        workbench = WorkbenchHarnessMiddleware(run)
        model = ScriptedChatModel([], profile={"max_input_tokens": 10000})
        native = BudgetedSummarizationMiddleware(model=model, backend=lambda _: None,
            token_counter=count_context_tokens, request_preparer=workbench._with_outline)
        request = ModelRequest(model=model, messages=[HumanMessage(content="Read")],
            system_message=SystemMessage(content="Instructions"), tools=[], model_settings={})
        prepared = native._selected_request(request)
        self.assertIn("main.py", prepared.system_message.content)
        self.assertEqual(workbench._with_outline(prepared).system_message, prepared.system_message)

    def test_new_outline_admission_counts_active_summary_instead_of_raw_history(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "workbench_backend.agents.project_outline.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=b""),
        ):
            (Path(directory) / "main.py").write_text("def current(): pass\n")
            run = AgentRun(id="follow-up", deployment_id="model", task="Read main.py", project_path=directory,
                enabled_tools=["read_file"], presented_tools=["read_file"],
                context_observation=ContextObservation(usable_input_tokens=1000),
                created_at=utc_now(), updated_at=utc_now())
            model = _ContextModel([], profile={"max_input_tokens": 1000})
            workbench = WorkbenchHarnessMiddleware(run)
            native = BudgetedSummarizationMiddleware(model=model, backend=lambda _: None,
                token_counter=count_context_tokens, request_preparer=workbench._with_outline)
            raw = [HumanMessage(content="x"*6000), AIMessage(content="Old answer"), HumanMessage(content="Read main.py")]
            state = {SUMMARIZATION_EVENT_KEY: {"cutoff_index": 2,
                "summary_message": HumanMessage(content="Old work summarized"), "file_path": None}}
            request = ModelRequest(model=model, messages=raw, state=state,
                system_message=SystemMessage(content="Instructions"), tools=[], model_settings={})
            prepared = native._selected_request(request)
            self.assertIn("current", prepared.system_message.content)
            self.assertEqual(prepared.messages, raw)
            self.assertEqual(prepared.state[SUMMARIZATION_EVENT_KEY]["cutoff_index"], 2)


if __name__ == "__main__":
    unittest.main()
