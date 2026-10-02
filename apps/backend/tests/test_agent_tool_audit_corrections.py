"""Saved-template and catalogue journeys for the agent-tool audit corrections."""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from workbench_backend.agents.execution_policy import PLAN_TOOLS
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.tool_disclosure import always_skill_dependencies
from workbench_backend.errors import HarnessError
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.setup_schemas import AgentInputPolicy
from workbench_backend.agents.tool_results import OwnedToolResults, continuation_notice, result_reader_tool
from workbench_backend.agents.tools import FILESYSTEM_TOOL_NAMES, OPT_IN_TOOL_NAMES, catalogue_projection, standard_context_key
from workbench_backend.app import create_app
from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.connections.service import namespaced
from workbench_backend.inference.ids import utc_now

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import wait_for_chat


OPT_IN = set(OPT_IN_TOOL_NAMES)
DISCLOSURE = {"find_tools", "read_reference", "task"}


class AuditHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "notes.md").write_text("project note", encoding="utf-8")
        self.app = create_app(data_root=self.root / "data")
        self.scripted = ScriptedChatModel([AIMessage(content="Done.")])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.app.state.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post("/v1/deployments/connected", json={
            "endpoint": "http://127.0.0.1:9/v1", "display_name": "audit-fixture",
        }).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _save(self, name: str, configuration: dict) -> dict:
        saved = self.client.post("/v1/agent-setups", json={"name": name, "role": "Research", "configuration": configuration})
        self.assertEqual(saved.status_code, 200, saved.text)
        reloaded = self.client.get(f"/v1/agent-setups/{saved.json()['id']}")
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        return reloaded.json()

    def _chat(self, **extra: Any) -> dict:
        payload = {"deployment_id": self.deployment_id, "approval_mode": "full_access", **extra}
        created = self.client.post("/v1/chat/conversations", json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()

    def _finish(self, chat: dict, task: str = "Look this up.", script: list[AIMessage] | None = None) -> dict:
        self.scripted = ScriptedChatModel(script or [AIMessage(content="Done.")])
        started = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": task})
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, chat["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        return run

    def _assert_closed(self, admitted: list[str], saved: list[str]) -> None:
        self.assertTrue(set(saved) <= set(admitted))
        self.assertTrue(set(admitted) <= set(saved) | DISCLOSURE)
        self.assertFalse(set(admitted) & (OPT_IN - set(saved)))


class CatalogueSelectionTests(AuditHarnessTests):
    def test_projectless_standard_edit_does_not_opt_in(self) -> None:
        projection = catalogue_projection()
        key = standard_context_key(project_bound=False)
        base = list(projection["defaults"][key])
        saved_names = [name for name in base if name != "time_now"]
        setup = self._save("Projectless standard", {"presented_tools": saved_names})
        self.assertEqual(setup["configuration"]["presented_tools"], saved_names)
        self.assertEqual(setup["configuration"].get("connection_ids") or [], [])
        self.assertIsNone(setup["configuration"].get("desktop_access"))
        run = self._finish(self._chat(agent_setup_id=setup["id"]))
        self._assert_closed(run["presented_tools"], saved_names)
        self.assertNotIn("delete", run["presented_tools"])
        self.assertNotIn("start_command", run["presented_tools"])
        self.assertNotIn("echo", run["presented_tools"])
        self.assertEqual(self.client.get("/v1/connections").json(), [])

    def test_project_standard_edit_keeps_file_tools_and_leaves_opt_in_off(self) -> None:
        projection = catalogue_projection()
        key = standard_context_key(project_bound=True)
        saved_names = [name for name in projection["defaults"][key] if name != "time_now"]
        setup = self._save("Project standard", {"presented_tools": saved_names, "requires_project": True})
        self.assertEqual(self.client.get(f"/v1/agent-setups/{setup['id']}").json()["configuration"]["presented_tools"], saved_names)
        run = self._finish(self._chat(agent_setup_id=setup["id"], project_path=str(self.project)))
        self._assert_closed(run["presented_tools"], saved_names)
        self.assertIn("read_file", run["presented_tools"])
        self.assertNotIn("delete", run["presented_tools"])
        self.assertNotIn("execute", run["presented_tools"])
        self.assertNotIn("browser_network_request", run["presented_tools"])
        self.assertNotIn("browser_emulate_media", run["presented_tools"])

    def test_empty_inherited_and_deliberate_selections_keep_their_meaning(self) -> None:
        projection = catalogue_projection()
        inherited = self._save("Inherited", {})
        self.assertIsNone(inherited["configuration"].get("presented_tools"))
        inherited_run = self._finish(self._chat(agent_setup_id=inherited["id"]))
        standard = list(projection["defaults"][standard_context_key(project_bound=False)])
        self._assert_closed(inherited_run["presented_tools"], standard)

        empty = self._save("Tools off", {"presented_tools": []})
        empty_run = self._finish(self._chat(agent_setup_id=empty["id"]))
        self.assertEqual(empty_run["presented_tools"], [])

        deliberate = self._save("Echo only", {"presented_tools": ["echo"]})
        reloaded = self.client.get(f"/v1/agent-setups/{deliberate['id']}").json()
        self.assertEqual(reloaded["configuration"]["presented_tools"], ["echo"])
        echo_run = self._finish(self._chat(agent_setup_id=deliberate["id"]))
        self.assertIn("echo", echo_run["presented_tools"])
        self.assertNotIn("delete", echo_run["presented_tools"])
        self.assertNotIn("start_command", echo_run["presented_tools"])
        self.assertTrue(set(echo_run["presented_tools"]) <= {"echo", *DISCLOSURE})

    def test_catalogue_groups_plan_eligibility_and_browser_operations(self) -> None:
        projection = self.client.get("/v1/agent-tools").json()
        self.assertEqual(projection["plan_tools"], sorted(PLAN_TOOLS))
        self.assertEqual(projection["plan_public_web_remote_names"], ["read_web_page", "search_web"])
        by_id = {tool["id"]: tool for tool in projection["tools"]}
        for name in ("browser_network_request", "browser_emulate_media"):
            self.assertEqual(by_id[name]["group"], "browser")
            self.assertTrue(by_id[name]["opt_in"])
            self.assertNotIn(name, [item for names in projection["defaults"].values() for item in names])
        for names in projection["defaults"].values():
            self.assertFalse(set(names) & OPT_IN)


class ResearcherTemplateTests(AuditHarnessTests):
    def _template(self) -> dict:
        templates = self.client.get("/v1/agent-setup-templates").json()
        return next(item for item in templates if item["id"] == "evidence-researcher")

    def _save_template(self, **configuration: Any) -> dict:
        template = self._template()
        self.assertEqual(template["configuration"]["connection_ids"], [])
        self.assertFalse(template["configuration"]["requires_project"])
        self.assertEqual(template["configuration"]["input_policy"]["pinned_tools"], ["read_attachment", "read_tool_result"])
        config = {**template["configuration"], **configuration}
        return self._save(template["name"], config)

    def _policy(self, loading: str, **extra: Any) -> dict:
        policy = {**self._template()["configuration"]["input_policy"], "tool_loading": loading, **extra}
        return policy

    def _read_attachment(self, setup: dict, receipt: str, *, task: str) -> dict:
        chat = self._chat(agent_setup_id=setup["id"], work_mode="plan")
        asset = RetainedAssetService(self.app.state.app_store).retain_upload(RetainedUploadRequest(
            session_id=chat["id"], filename="source.md", content_type="text/markdown",
            content_base64=base64.b64encode(receipt.encode()).decode()))
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "read_attachment", "args": {"asset_id": asset.id}, "id": "read-doc"}]),
            AIMessage(content="Cited the document."),
        ])
        started = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": task, "attachment_ids": [asset.id]})
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, chat["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertIn(receipt, str(self.client.get(f"/v1/agent-runs/{finished['current_run_id']}", params={"view": "diagnostic"}).json()))
        return run

    def test_projectless_document_research_without_a_skill_or_project_tools(self) -> None:
        saved_tools = self._template()["configuration"]["presented_tools"]
        self.assertTrue({"ls", "read_file", "glob", "grep", "read_attachment", "read_tool_result"} <= set(saved_tools))
        for loading in ("when_needed", "always"):
            with self.subTest(loading=loading):
                setup = self._save_template(input_policy=self._policy(loading))
                self.assertEqual(setup["configuration"]["skill_entry_ids"], [])
                self.assertEqual(setup["configuration"]["presented_tools"], saved_tools)
                reloaded = self.client.get(f"/v1/agent-setups/{setup['id']}").json()
                self.assertEqual(reloaded["configuration"]["presented_tools"], saved_tools)
                self.assertEqual(reloaded["configuration"]["input_policy"]["tool_loading"], loading)
                presented = set(self._read_attachment(setup, "DOC_RECEIPT_77", task="Read the attached source.")["presented_tools"])
                self.assertIn("read_attachment", presented)
                self.assertIn("read_tool_result", presented)
                self.assertFalse(presented & {"ls", "read_file", "glob", "grep", "execute", "delete"})

    def _assert_offered_reader_is_virtual(self, model: ScriptedChatModel) -> None:
        rendered: list[str] = []
        names: list[str | None] = []
        for tool in model.bound_tools:
            if isinstance(tool, dict):
                function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
                names.append(function.get("name"))
                rendered.append(json.dumps(tool))
                continue
            names.append(getattr(tool, "name", None))
            schema = getattr(tool, "args_schema", None)
            if isinstance(schema, dict):
                body = schema
            elif schema is not None and hasattr(schema, "model_json_schema"):
                body = schema.model_json_schema()
            else:
                body = {}
            rendered.append(json.dumps({
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", ""),
                "schema": body,
            }))
        self.assertIn("read_file", names, rendered)
        self.assertNotIn("glob", names)
        self.assertNotIn("grep", names)
        text = "\n".join(rendered)
        self.assertNotIn("Project-relative", text)
        self.assertNotIn("/ is the project root", text)
        self.assertIn("/skills/", text)
        self.assertIn("is not a project root", text)

    def test_installed_research_skill_does_not_add_project_filesystem(self) -> None:
        installed = self.client.post("/v1/knowledge/skills/bundled/evidence-research/install", json={})
        self.assertEqual(installed.status_code, 200, installed.text)
        for loading in ("when_needed", "always"):
            with self.subTest(loading=loading):
                setup = self._save_template(input_policy=self._policy(loading), skill_entry_ids=[installed.json()["id"]])
                self.assertEqual(setup["configuration"]["skill_entry_ids"], [installed.json()["id"]])
                self.assertIn("glob", setup["configuration"]["presented_tools"])
                admitted = self._read_attachment(setup, "SKILL_RECEIPT_77", task="Read the attached source with the research skill.")
                presented = set(admitted["presented_tools"])
                self.assertIn("read_attachment", presented)
                self.assertIn("read_tool_result", presented)
                self.assertTrue({"ls", "read_file"} <= presented)
                self.assertFalse(presented & {"glob", "grep", "execute", "delete"})
                self._assert_offered_reader_is_virtual(self.scripted)
                chat = self._chat(agent_setup_id=setup["id"], work_mode="plan")
                self.scripted = ScriptedChatModel([
                    AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "/src/secret.txt"}, "id": "project-read"}]),
                    AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "/skills/evidence-research/SKILL.md"}, "id": "skill-read"}]),
                    AIMessage(content="Reviewed the skill."),
                ])
                started = self.client.post(
                    f"/v1/chat/conversations/{chat['id']}/start",
                    json={"task": "Read the skill, not a project file."},
                )
                self.assertEqual(started.status_code, 200, started.text)
                finished = wait_for_chat(self.client, chat["id"])
                self.assertEqual(finished["current_run"]["status"], "completed", finished["current_run"].get("error"))
                diagnostic = str(self.client.get(
                    f"/v1/agent-runs/{finished['current_run_id']}", params={"view": "diagnostic"}).json())
                self.assertIn("the file was not written", diagnostic)
                self.assertIn("Choose an applicable selected source route", diagnostic)

    def test_plan_public_web_comes_only_from_the_selected_builtin_connection(self) -> None:
        created = self.client.post("/v1/connections", json={"name": "Public pages", "kind": "public_web", "transport": "builtin"})
        self.assertEqual(created.status_code, 200, created.text)
        with patch("workbench_backend.connections.public_web.search_web", new=AsyncMock(return_value="fixture")), \
             patch("workbench_backend.connections.public_web.read_web_page", new=AsyncMock(return_value="fixture")):
            tested = self.client.post(f"/v1/connections/{created.json()['id']}/test")
        self.assertEqual(tested.status_code, 200, tested.text)
        self.assertIsNone(tested.json()["last_error"])
        connection_id = tested.json()["id"]
        expected = {namespaced(connection_id, "search_web"), namespaced(connection_id, "read_web_page")}
        setup = self._save_template(connection_ids=[connection_id])
        chat = self._chat(agent_setup_id=setup["id"], work_mode="plan")
        run = self._finish(chat, task="Find a public source.")
        presented = set(run["presented_tools"])
        self.assertTrue(expected <= presented)
        self.assertFalse(any(name.startswith("cx_") and name not in expected for name in presented))
        off_setup = self._save_template(connection_ids=[connection_id], presented_tools=[])
        off = self._finish(self._chat(agent_setup_id=off_setup["id"], work_mode="plan"), task="Tools are off.")
        self.assertEqual(off["presented_tools"], [])
        always = self._save_template(connection_ids=[connection_id], input_policy=self._policy("always"))
        always_run = self._finish(self._chat(agent_setup_id=always["id"], work_mode="plan"), task="Find a public source.")
        always_presented = set(always_run["presented_tools"])
        self.assertTrue(expected <= always_presented)
        self.assertFalse(always_presented & {"glob", "grep", "ls", "execute", "delete"})

    def test_project_bound_research_keeps_project_reads(self) -> None:
        for loading in ("when_needed", "always"):
            with self.subTest(loading=loading):
                setup = self._save_template(input_policy=self._policy(loading))
                run = self._finish(self._chat(agent_setup_id=setup["id"], project_path=str(self.project), work_mode="plan"))
                presented = set(run["presented_tools"])
                self.assertTrue({"ls", "read_file", "glob", "grep", "read_tool_result"} <= presented)
                self.assertNotIn("execute", presented)
                self.assertNotIn("delete", presented)

    def test_pinned_reads_and_eager_mutation_require_a_project(self) -> None:
        pinned = self._save_template(input_policy=self._policy("always", pinned_tools=["read_attachment", "read_tool_result", "glob"]))
        self.assertIn("glob", pinned["configuration"]["presented_tools"])
        chat = self._chat(agent_setup_id=pinned["id"], work_mode="plan")
        blocked = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Search the project."})
        self.assertEqual(blocked.status_code, 400, blocked.text)
        self.assertEqual(blocked.json()["code"], "filesystem_requires_project")
        self.assertIn("glob", blocked.json()["tools"])
        mutation = self._save("Eager write", {"presented_tools": ["write_file"], "input_policy": {"tool_loading": "always"}})
        write_chat = self._chat(agent_setup_id=mutation["id"])
        write = self.client.post(f"/v1/chat/conversations/{write_chat['id']}/start", json={"task": "Write."})
        self.assertEqual(write.status_code, 400, write.text)
        self.assertEqual(write.json()["code"], "filesystem_requires_project")
        shell = self._save("Eager shell", {"presented_tools": ["execute"], "input_policy": {"tool_loading": "always"}})
        shell_chat = self._chat(agent_setup_id=shell["id"])
        command = self.client.post(f"/v1/chat/conversations/{shell_chat['id']}/start", json={"task": "Run."})
        self.assertEqual(command.status_code, 200, command.text)
        finished = wait_for_chat(self.client, shell_chat["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertTrue(run["host_shell"]["available"])
        self.assertEqual(run["host_shell"]["cwd"], str(Path.home().resolve()))

    def test_framework_reader_does_not_satisfy_a_required_project_read(self) -> None:
        run = SimpleNamespace(
            presented_tools=["echo"], framework_read_paths=["/large_tool_results/", "/conversation_history/"],
            work_mode="work", project_path=None, connection_snapshots=[],
            input_policy=AgentInputPolicy(tool_loading="always"))
        skill = SimpleNamespace(kind="skill", mode="always", required_tools=["read_file"],
            required_connections=[], requires_project=False)
        with self.assertRaises(HarnessError) as blocked:
            always_skill_dependencies(run, SimpleNamespace(references=[skill]))
        self.assertEqual(blocked.exception.code, "skill_selection_required")
        satisfied = SimpleNamespace(
            presented_tools=["read_file"], framework_read_paths=[], work_mode="work",
            project_path=str(self.project), connection_snapshots=[],
            input_policy=AgentInputPolicy(tool_loading="always"))
        self.assertEqual(always_skill_dependencies(satisfied, SimpleNamespace(references=[skill])), ({"read_file"}, set()))

    def test_skill_required_project_read_is_not_satisfied_by_the_framework_reader(self) -> None:
        created = self.client.post("/v1/knowledge/entries", json={
            "scope": "user", "kind": "skill", "display_name": "Needs project search",
            "content": "---\nname: needs-project-search\ndescription: Search project files.\nrequired-tools:\n  - glob\n---\nSearch the project.\n",
            "provenance": {"actor": "human", "note": "fixture"},
        })
        self.assertEqual(created.status_code, 200, created.text)
        skill = created.json()
        reader = self.client.post("/v1/knowledge/entries", json={
            "scope": "user", "kind": "skill", "display_name": "Needs a file reader",
            "content": "---\nname: needs-file-reader\ndescription: Read selected files.\nrequired-tools:\n  - read_file\n---\nRead a file.\n",
            "provenance": {"actor": "human", "note": "fixture"},
        })
        self.assertEqual(reader.status_code, 200, reader.text)
        for loading in ("when_needed", "always"):
            with self.subTest(loading=loading, selection="framework-only"):
                setup = self._save("Framework is not a project read", {
                    "presented_tools": ["echo"],
                    "skill_entry_ids": [reader.json()["id"]],
                    "input_policy": {"tool_loading": loading, "pinned_tools": [], "reference_loading": {reader.json()["id"]: "always"}},
                })
                self.assertEqual(setup["configuration"]["presented_tools"], ["echo"])
                created_chat = self.client.post("/v1/chat/conversations", json={
                    "deployment_id": self.deployment_id, "approval_mode": "full_access", "agent_setup_id": setup["id"]})
                self.assertEqual(created_chat.status_code, 409, created_chat.text)
                self.assertEqual(created_chat.json()["code"], "skill_selection_required")
                self.assertIn("read_file", created_chat.json()["error"])
            with self.subTest(loading=loading, selection="required-glob"):
                selected = self._save("Required search still needs a project", {
                    "presented_tools": ["glob"],
                    "skill_entry_ids": [skill["id"]],
                    "input_policy": {"tool_loading": loading, "reference_loading": {skill["id"]: "always"}},
                })
                self.assertIn("glob", selected["configuration"]["presented_tools"])
                selected_chat = self.client.post("/v1/chat/conversations", json={
                    "deployment_id": self.deployment_id, "approval_mode": "full_access", "agent_setup_id": selected["id"]})
                self.assertEqual(selected_chat.status_code, 409, selected_chat.text)
                self.assertEqual(selected_chat.json()["code"], "skill_selection_required")
                self.assertIn("glob", selected_chat.json()["error"])


class RetainedReaderTemplateTests(AuditHarnessTests):
    def _seed(self, thread_id: str) -> dict:
        owner = SimpleNamespace(id="seed", thread_id=thread_id, parent_run_id=None, presented_tools=["read_tool_result"])
        return OwnedToolResults(self.app.state.manager.paths, owner).retain(("n" * 12000) + "LATE_MARKER", source={"kind": "fixture", "acquisition_complete": True})

    def _read(self, chat: dict, result_path: str, tool: str = "read_tool_result", args: dict | None = None) -> dict:
        call_args = args or {"result_path": result_path, "query": "LATE_MARKER"}
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": tool, "args": call_args, "id": "read-kept"}]),
            AIMessage(content="Continued."),
        ])
        started = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Read the retained marker."})
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, chat["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        diagnostic = self.client.get(f"/v1/agent-runs/{run['id']}", params={"view": "diagnostic"}).json()
        return {"run": run, "diagnostic": diagnostic}

    def test_stock_templates_can_read_a_late_marker_without_shell(self) -> None:
        templates = [item for item in self.client.get("/v1/agent-setup-templates").json()
            if item["id"] not in {"browser-validator", "windows-validator"}
            and "read_tool_result" in item["configuration"]["presented_tools"]]
        self.assertGreaterEqual(len(templates), 3)
        for template in templates:
            pins = template["configuration"]["input_policy"]["pinned_tools"]
            self.assertIn("read_tool_result", template["configuration"]["presented_tools"])
            if template["id"] == "evidence-researcher":
                self.assertEqual(pins, ["read_attachment", "read_tool_result"])
            else:
                self.assertNotIn("read_tool_result", pins)
            setup = self._save(template["name"] + " retained", template["configuration"])
            # Pinned filesystem tools still need a folder when the draft does not require a project.
            needs_folder = template["configuration"].get("requires_project") or bool(set(pins) & set(FILESYSTEM_TOOL_NAMES))
            extra = {"project_path": str(self.project)} if needs_folder else {}
            chat = self._chat(agent_setup_id=setup["id"], **extra)
            seeded = self._seed(chat["thread_id"])
            read = self._read(chat, seeded["path"])
            self.assertIn("read_tool_result", read["run"]["presented_tools"])
            self.assertIn("LATE_MARKER", str(read["diagnostic"]))
            calls = [item.get("name") for item in read["run"]["tool_invocations"]]
            self.assertEqual(calls, ["read_tool_result"])
            self.assertEqual(read["diagnostic"]["model_requests"], [])

    def test_browser_and_windows_templates_compile_the_reader(self) -> None:
        for template_id, codes in (
            ("browser-validator", {"browser_unavailable", "browser_worker_missing"}),
            ("windows-validator", {"desktop_grant_required", "desktop_unavailable", "desktop_runtime_unavailable"}),
        ):
            template = next(item for item in self.client.get("/v1/agent-setup-templates").json() if item["id"] == template_id)
            self.assertIn("read_tool_result", template["configuration"]["presented_tools"])
            pins = template["configuration"]["input_policy"]["pinned_tools"]
            if template_id == "browser-validator":
                self.assertEqual(pins, ["browser_navigate", "browser_snapshot"])
            else:
                self.assertEqual(pins, ["desktop_inspect"])
            setup = self._save(template["name"], template["configuration"])
            chat = self._chat(agent_setup_id=setup["id"], work_mode="work")
            started = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Inspect."})
            if started.status_code == 200:
                seeded = self._seed(chat["thread_id"])
                read = self._read(chat, seeded["path"])
                self.assertIn("LATE_MARKER", str(read["diagnostic"]))
                continue
            self.assertIn(started.json()["code"], codes, started.text)
            seeded = self._seed(chat["thread_id"])
            run = AgentRun(id="compiled-reader", deployment_id=self.deployment_id, task="Read retained evidence",
                thread_id=chat["thread_id"], enabled_tools=template["configuration"]["presented_tools"],
                presented_tools=template["configuration"]["presented_tools"], created_at=utc_now(), updated_at=utc_now())
            result = result_reader_tool(self.app.state.manager.paths, run).invoke({"result_path": seeded["path"], "query": "LATE_MARKER"})
            self.assertIn("LATE_MARKER", str(result))
            self.assertNotIn("execute", template["configuration"]["presented_tools"] if template_id == "browser-validator" else [])

    def _owner_from(self, run: dict) -> AgentRun:
        policy = run.get("input_policy")
        return AgentRun(
            id=run["id"], deployment_id=self.deployment_id, task=run.get("task") or "Look this up.",
            thread_id=run["thread_id"], parent_run_id=run.get("parent_run_id"),
            presented_tools=list(run["presented_tools"]), enabled_tools=list(run.get("enabled_tools") or run["presented_tools"]),
            framework_read_paths=list(run.get("framework_read_paths") or []),
            work_mode=run.get("work_mode") or "work",
            input_policy=AgentInputPolicy.model_validate(policy) if policy else None,
            created_at=utc_now(), updated_at=utc_now())

    def test_browser_only_setup_reads_retained_text_with_the_framework_reader(self) -> None:
        setup = self._save("Browser only", {
            "presented_tools": ["browser_snapshot"],
            "input_policy": {"tool_loading": "when_needed", "pinned_tools": []},
        })
        self.assertEqual(setup["configuration"]["presented_tools"], ["browser_snapshot"])
        chat = self._chat(agent_setup_id=setup["id"], work_mode="work")
        first = self._finish(chat, task="Look at the page later.")
        self.assertIn("browser_snapshot", first["presented_tools"])
        self.assertNotIn("read_file", first["presented_tools"])
        self.assertNotIn("read_tool_result", first["presented_tools"])
        self.assertEqual(first["framework_read_paths"], ["/large_tool_results/", "/conversation_history/"])
        owner = self._owner_from(first)
        notice = continuation_notice(owner)
        self.assertIn("framework-only line reader", notice)
        self.assertIn("/large_tool_results/", notice)
        self.assertIn("cannot search inside one long line", notice)
        self.assertIn("not authorized", notice)
        self.assertNotIn("no accepted reader", notice)
        retained = OwnedToolResults(self.app.state.manager.paths, owner).retain(
            "LATE_MARKER\nshort retained page text", source={"kind": "fixture", "acquisition_complete": True})
        self.assertEqual(retained["notice"], notice)
        read = self._read(chat, retained["path"], tool="read_file", args={"file_path": retained["path"]})
        self.assertNotIn("read_file", read["run"]["presented_tools"])
        self.assertIn("LATE_MARKER", str(read["diagnostic"]))
        later = SimpleNamespace(
            id="later-selection", thread_id=first["thread_id"], parent_run_id=None, presented_tools=[],
            framework_read_paths=["/large_tool_results/", "/conversation_history/"], work_mode="work",
            input_policy=None, connection_snapshots=[])
        revisited = OwnedToolResults(self.app.state.manager.paths, later).read(retained["path"], query="LATE_MARKER")
        self.assertIn("framework-only line reader", revisited["result"]["notice"])
        self.assertIn("no accepted reader", revisited["reader_notice"])
        self.assertNotEqual(revisited["result"]["notice"], revisited["reader_notice"])

        excluded = self._save("Browser reader excluded", {
            "presented_tools": ["browser_snapshot"],
            "input_policy": {"tool_loading": "when_needed", "pinned_tools": [], "excluded_sources": ["tool:read_file"]},
        })
        excluded_chat = self._chat(agent_setup_id=excluded["id"], work_mode="work")
        excluded_run = self._finish(excluded_chat, task="Do not read framework files.")
        excluded_notice = continuation_notice(self._owner_from(excluded_run))
        self.assertNotIn("framework-only line reader", excluded_notice)
        self.assertIn("no accepted reader", excluded_notice)
        blocked = self._read(excluded_chat, "/large_tool_results/owned/" + "a" * 32 + ".txt", tool="read_file",
            args={"file_path": "/large_tool_results/owned/" + "a" * 32 + ".txt"})
        outcome = blocked["diagnostic"]["tool_outcomes"]["read-kept"]
        self.assertEqual(outcome["outcome"], "failed")
        self.assertIn("excluded", outcome["result"])
        self.assertNotIn("LATE_MARKER", str(outcome["result"]))

    def test_exclusion_tools_off_owner_mismatch_and_read_file_fallback(self) -> None:
        self.assertIn("read_file can also read it", continuation_notice(SimpleNamespace()))
        self.assertNotIn("framework-only", continuation_notice(SimpleNamespace()))
        self.assertIn("no accepted reader", continuation_notice(SimpleNamespace(presented_tools=[])))
        self.assertIn("Discovery cannot", continuation_notice(SimpleNamespace(presented_tools=[])))
        tools_off = SimpleNamespace(presented_tools=[], framework_read_paths=["/large_tool_results/"], work_mode="work")
        self.assertIn("no accepted reader", continuation_notice(tools_off))
        self.assertNotIn("framework-only", continuation_notice(tools_off))
        self.assertIn("cannot search inside one long line", continuation_notice(SimpleNamespace(presented_tools=["read_file"])))
        self.assertIn("read_tool_result", continuation_notice(SimpleNamespace(presented_tools=["read_tool_result", "read_file"])))
        selected_reader = SimpleNamespace(
            presented_tools=["browser_snapshot", "read_tool_result"],
            framework_read_paths=["/large_tool_results/", "/conversation_history/"], work_mode="work")
        selected_notice = continuation_notice(selected_reader)
        self.assertIn("read_tool_result", selected_notice)
        self.assertNotIn("no accepted reader", selected_notice)
        self.assertNotIn("framework-only", selected_notice)

        excluded = self._save("No reader", {"presented_tools": ["read_file", "read_tool_result"], "input_policy": {"excluded_sources": ["tool:read_tool_result"]}})
        chat = self._chat(agent_setup_id=excluded["id"], project_path=str(self.project))
        seeded = self._seed(chat["thread_id"])
        excluded_run = self._finish(chat, task="Do not use the retained reader.")
        self.assertIn("read_file", excluded_run["presented_tools"])
        self.assertNotIn("read_tool_result", excluded_run["presented_tools"])
        fallback = self._read(chat, seeded["path"], tool="read_file", args={"file_path": seeded["path"]})
        self.assertNotIn("read_tool_result", fallback["run"]["presented_tools"])
        self.assertIn(seeded["path"], str(fallback["diagnostic"]))

        off = self._save("Off", {"presented_tools": []})
        off_chat = self._chat(agent_setup_id=off["id"])
        off_run = self._finish(off_chat, task="Tools are off.")
        self.assertEqual(off_run["presented_tools"], [])
        diagnostic = self.client.get(f"/v1/agent-runs/{off_run['id']}", params={"view": "diagnostic"}).json()
        self.assertEqual(diagnostic["model_requests"], [])
        self.assertEqual(off_run["tool_invocations"], [])

        owned = self._save("Owner", {"presented_tools": ["read_tool_result"]})
        owner_chat = self._chat(agent_setup_id=owned["id"])
        other = self._seed("another-owner")
        mismatch = self._read(owner_chat, other["path"])
        outcome = mismatch["diagnostic"]["tool_outcomes"]["read-kept"]
        self.assertEqual(outcome["outcome"], "failed")
        self.assertIn("another owner", outcome["result"])
        self.assertNotIn("LATE_MARKER", outcome["result"])
