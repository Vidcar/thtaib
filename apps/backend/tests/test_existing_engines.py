"""Lock the existing Deep Agents engines for tasks 2.1 through 2.5."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import build_run_backend, host_shell_requested
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ServerProperties
from workbench_backend.inference.telemetry import current_request_purpose
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run


FILE_TOOLS = ("ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete")
JOB_TOOLS = ("start_command", "command_status", "stop_command")
SKILL_BODY = (
    "---\nname: review-checklist\n"
    "description: Use the review checklist before answering.\n---\n\n"
    "Use the review checklist before answering.\n"
)


def _tool_names(tools: list[Any]) -> list[str]:
    names: list[str] = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
        if isinstance(name, str):
            names.append(name)
    return names


def _shell_defaults(middleware: list[Any]) -> list[Any]:
    found = []
    for item in middleware:
        backend = getattr(item, "backend", None)
        default = getattr(backend, "default", None)
        if isinstance(default, LocalShellBackend):
            found.append(default)
    return found


class ExistingEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root / "data")
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel([AIMessage(content="done")])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
            managed_commands=self.app.state.managed_commands,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "existing-engines"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _install(self, script: list[AIMessage]) -> ScriptedChatModel:
        self.scripted = ScriptedChatModel(script)
        model = self.scripted

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return model

        self.app.state.harness._model_factory = factory
        return model

    def _set_context(self, n_ctx: int) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_deployment(deployment.model_copy(update={
            "server_props": ServerProperties(
                fetched=utc_now(),
                source_url="http://127.0.0.1:9/props",
                n_ctx=n_ctx,
            ),
        }))

    def _start(self, **extra: Any):
        payload = {"deployment_id": self.deployment_id, "task": "Say done.", **extra}
        return self.client.post("/v1/agent-runs", json=payload)

    def _knowledge(self, kind: str, content: str) -> dict[str, Any]:
        created = self.client.post("/v1/knowledge/entries", json={
            "scope": "user",
            "kind": kind,
            "content": content,
            "display_name": f"{kind}-engines",
            "provenance": {"actor": "human", "note": "existing-engines"},
        })
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()

    def test_one_summarizer_uses_its_fractions_and_live_context(self) -> None:
        self._set_context(8192)
        calls: list[dict[str, Any]] = []
        from deepagents import graph as deepagents_graph
        original = deepagents_graph.create_agent

        def spy(*args: Any, **kwargs: Any):
            calls.append({
                "middleware": list(kwargs.get("middleware") or []),
                "tools": list(kwargs.get("tools") or []),
            })
            return original(*args, **kwargs)

        with patch("deepagents.graph.create_agent", spy), patch(
            "workbench_backend.agents.harness.create_summarization_middleware",
            wraps=__import__(
                "deepagents.middleware.summarization",
                fromlist=["create_summarization_middleware"],
            ).create_summarization_middleware,
        ) as factory:
            started = self._start(task="Short reply.", presented_tools=[])
            self.assertEqual(started.status_code, 200, started.text)
            finished = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(factory.call_count, 1)
        self.assertNotIn("trigger", factory.call_args.kwargs)
        self.assertNotIn("keep", factory.call_args.kwargs)
        middleware = calls[0]["middleware"]
        summarizers = [
            item for item in middleware
            if getattr(item, "name", None) == "SummarizationMiddleware"
            or "summar" in type(item).__name__.lower()
        ]
        self.assertEqual(len(summarizers), 1)
        self.assertEqual(sum(isinstance(item, SummarizationMiddleware) for item in middleware), 1)
        summary = summarizers[0]
        self.assertEqual(summary._lc_helper.trigger, ("fraction", 0.85))
        self.assertEqual(summary._lc_helper.keep, ("fraction", 0.10))
        self.assertEqual(summary.model.profile["max_input_tokens"], 8192)
        self.assertEqual(finished["context_observation"]["capacity_tokens"], 8192)

        self._set_context(64)
        oversized = self._start(task="x" * 2000, presented_tools=[])
        self.assertEqual(oversized.status_code, 200, oversized.text)
        rejected = wait_for_run(self.client, oversized.json()["id"])
        self.assertEqual(rejected["status"], "failed", rejected.get("error"))
        self.assertEqual(rejected["failure"]["code"], "context_capacity_exceeded")

    def test_overflow_keeps_the_chat_and_offers_no_branch(self) -> None:
        self._set_context(32768)
        self._install([
            AIMessage(content="first retained"),
            AIMessage(content="internal summary"),
        ])
        created = self.client.post("/v1/chat/conversations", json={"deployment_id": self.deployment_id})
        self.assertEqual(created.status_code, 200, created.text)
        conversation_id = created.json()["id"]
        marker = "overflow-marker-stay"
        first = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": marker, "presented_tools": []},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(wait_for_run(self.client, first.json()["current_run_id"])["status"], "completed")
        self._set_context(512)
        model = self.scripted
        original = type(model)._generate

        def native_rejection(instance, messages, *args, **kwargs):
            if current_request_purpose() == "work":
                raise ContextOverflowError("Native fixture cannot fit this work request.")
            return original(instance, messages, *args, **kwargs)

        with patch.object(type(model), "_generate", native_rejection):
            second = self.client.post(
                f"/v1/chat/conversations/{conversation_id}/start",
                json={"task": "Continue briefly.", "presented_tools": []},
            )
            self.assertEqual(second.status_code, 200, second.text)
            failed = wait_for_run(self.client, second.json()["current_run_id"])
        self.assertEqual(failed["failure"]["code"], "context_capacity_exceeded")
        self.assertEqual(failed["failure"]["recovery_action"], "change_limit")
        stayed = self.client.get(f"/v1/chat/conversations/{conversation_id}")
        self.assertEqual(stayed.status_code, 200, stayed.text)
        body = stayed.json()
        self.assertEqual(body["id"], conversation_id)
        self.assertEqual(body["current_run_id"], failed["id"])
        self.assertIn(marker, json.dumps(body["transcript"]))
        listed = self.client.get("/v1/chat/conversations").json()
        self.assertEqual([item["id"] for item in listed], [conversation_id])
        actions = self.client.get(
            f"/v1/chat/conversations/{conversation_id}/replies/{failed['id']}/actions",
        )
        self.assertEqual(actions.status_code, 200, actions.text)
        self.assertFalse(actions.json()["branch_available"])
        branched = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/branches",
            json={"source_run_id": failed["id"]},
        )
        self.assertEqual(branched.status_code, 409, branched.text)
        self.assertEqual(branched.json()["code"], "branch_unavailable")
        self.assertEqual([item["id"] for item in self.client.get("/v1/chat/conversations").json()], [conversation_id])

    def test_file_tools_and_library_middleware_stay_single_copies(self) -> None:
        memory = self._knowledge("memory", "MEM-ENGINES-TOKEN")
        skill = self._knowledge("skill", SKILL_BODY)
        calls: list[dict[str, Any]] = []
        from deepagents import graph as deepagents_graph
        original = deepagents_graph.create_agent

        def spy(*args: Any, **kwargs: Any):
            calls.append({
                "middleware": list(kwargs.get("middleware") or []),
                "tools": list(kwargs.get("tools") or []),
            })
            return original(*args, **kwargs)

        with patch("deepagents.graph.create_agent", spy):
            started = self._start(
                task="Look once.",
                project_path=str(self.project),
                approval_mode="full_access",
                presented_tools=[*FILE_TOOLS, "apply_edits", "execute", *JOB_TOOLS],
                input_policy={"tool_loading": "always"},
                memory_version_refs=[memory["current_version_id"]],
                skill_version_refs=[skill["current_version_id"]],
            )
            self.assertEqual(started.status_code, 200, started.text)
            finished = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(len(calls), 1)
        middleware = calls[0]["middleware"]
        extra = _tool_names(calls[0]["tools"])
        filesystems = [item for item in middleware if getattr(item, "name", None) == "FilesystemMiddleware"]
        self.assertEqual(len(filesystems), 1)
        self.assertEqual(sum(isinstance(item, FilesystemMiddleware) for item in middleware), 1)
        self.assertEqual(sum(getattr(item, "name", None) == "MemoryMiddleware" for item in middleware), 1)
        self.assertEqual(sum(isinstance(item, MemoryMiddleware) for item in middleware), 1)
        self.assertEqual(sum(getattr(item, "name", None) == "SkillsMiddleware" for item in middleware), 1)
        self.assertEqual(sum(isinstance(item, SkillsMiddleware) for item in middleware), 1)
        native = _tool_names(filesystems[0].tools)
        self.assertEqual(native.count("edit_file"), 1)
        self.assertEqual(native.count("delete"), 1)
        delete = next(tool for tool in filesystems[0].tools if tool.name == "delete")
        self.assertEqual(delete.func.__module__, "deepagents.middleware.filesystem")
        self.assertIn("_create_delete_tool", delete.func.__qualname__)
        self.assertEqual(extra.count("apply_edits"), 1)
        self.assertNotIn("edit_file", extra)
        self.assertNotIn("delete", extra)
        self.assertNotIn("execute", extra)
        for name in JOB_TOOLS:
            self.assertEqual(extra.count(name), 1)
        self.assertEqual(len(extra), len(set(extra)))
        self.assertEqual(len(native), len(set(native)))
        self.assertFalse(set(extra) & set(native))
        shells = _shell_defaults(middleware)
        self.assertEqual({id(item) for item in shells}, {id(shells[0])})
        self.assertIsInstance(filesystems[0].backend, CompositeBackend)
        self.assertIsInstance(filesystems[0].backend.default, LocalShellBackend)
        self.assertEqual(filesystems[0].backend.default.cwd, self.project.resolve())

    def test_project_free_command_starts_in_the_user_profile(self) -> None:
        home = Path.home().resolve()
        calls: list[dict[str, Any]] = []
        from deepagents import graph as deepagents_graph
        original = deepagents_graph.create_agent

        def spy(*args: Any, **kwargs: Any):
            calls.append({"middleware": list(kwargs.get("middleware") or []), "tools": list(kwargs.get("tools") or [])})
            return original(*args, **kwargs)

        self._install([
            AIMessage(
                content="",
                tool_calls=[{"name": "execute", "args": {"command": "cd"}, "id": "call_cwd"}],
            ),
            AIMessage(content="Printed the starting folder."),
        ])
        with patch("deepagents.graph.create_agent", spy):
            started = self._start(
                task="Print the starting folder.",
                approval_mode="full_access",
                presented_tools=["execute", *JOB_TOOLS],
                input_policy={"tool_loading": "always"},
            )
            self.assertEqual(started.status_code, 200, started.text)
            body = started.json()
            self.assertTrue(body["host_shell"]["available"])
            self.assertEqual(body["host_shell"]["cwd"], str(home))
            finished = wait_for_run(self.client, body["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        output = finished["tool_outcomes"]["call_cwd"]["result"]
        self.assertEqual(Path(output.splitlines()[0].strip()).resolve(), home)
        self.assertEqual(len(calls), 1)
        extra = _tool_names(calls[0]["tools"])
        self.assertEqual(extra.count("execute"), 0)
        for name in JOB_TOOLS:
            self.assertEqual(extra.count(name), 1)
        shells = _shell_defaults(calls[0]["middleware"])
        self.assertEqual({id(item) for item in shells}, {id(shells[0])})
        self.assertEqual(shells[0].cwd, home)
        self.assertFalse((home / "host-shell-approved.txt").exists())

    def test_project_free_job_starts_in_the_user_profile(self) -> None:
        home = Path.home().resolve()
        run = SimpleNamespace(
            id="run_profile_job",
            thread_id="thread_profile_job",
            parent_run_id=None,
            project_path=None,
            status="running",
            work_mode="work",
            tool_mode="live-tool",
            presented_tools=["start_command", "command_status", "stop_command"],
        )
        service = self.app.state.managed_commands
        tools = service.tools_for_run(run)
        self.assertEqual([tool.name for tool in tools], list(JOB_TOOLS))
        launch = service.start(run, [sys._base_executable, "-c", "import os; print(os.getcwd())"], 30)
        status = service.status(run, launch["command_id"], wait_seconds=10)
        self.assertEqual(status["state"], "completed", status)
        self.assertEqual(status["exit_code"], 0)
        self.assertEqual(Path(status["preview"].strip()).resolve(), home)

    def test_skill_script_without_a_project_fails(self) -> None:
        blocked = self._start(
            task="Run a skill script.",
            presented_tools=["execute_skill_script"],
            input_policy={"tool_loading": "always"},
        )
        self.assertEqual(blocked.status_code, 400, blocked.text)
        self.assertEqual(blocked.json()["code"], "shell_requires_project")
        self.assertEqual(blocked.json()["tools"], ["execute_skill_script"])

    def test_projectless_file_tools_and_preview_still_fail(self) -> None:
        files = self._start(
            task="Write.",
            presented_tools=["write_file"],
            input_policy={"tool_loading": "always"},
        )
        self.assertEqual(files.status_code, 400, files.text)
        self.assertEqual(files.json()["code"], "filesystem_requires_project")
        preview = self._start(
            task="Preview.",
            presented_tools=["start_preview"],
            input_policy={"tool_loading": "always"},
        )
        self.assertEqual(preview.status_code, 400, preview.text)
        self.assertEqual(preview.json()["code"], "shell_requires_project")
        self.assertEqual(preview.json()["tools"], ["start_preview"])

    def test_projectless_run_without_execute_stays_off_the_host_shell(self) -> None:
        paths = WorkbenchPaths(self.root / "scratch").ensure()
        run = SimpleNamespace(
            id="run_state",
            thread_id="thread_state",
            parent_run_id=None,
            project_path=None,
            tool_mode="live-tool",
            presented_tools=["echo"],
            memory_version_refs=[],
            skill_version_refs=[],
        )
        self.assertFalse(host_shell_requested(run))
        backend = build_run_backend(run, paths)
        self.assertIsInstance(backend, CompositeBackend)
        self.assertIsInstance(backend.default, StateBackend)


if __name__ == "__main__":
    unittest.main()
