"""Saved-template and catalogue journeys for the agent-tool audit corrections."""
from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from workbench_backend.agents.execution_policy import PLAN_TOOLS
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.tool_results import OwnedToolResults, continuation_notice, result_reader_tool
from workbench_backend.agents.tools import OPT_IN_TOOL_NAMES, catalogue_projection, standard_context_key
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

    def test_projectless_document_research_without_a_skill_or_project_tools(self) -> None:
        setup = self._save_template()
        self.assertEqual(setup["configuration"]["skill_entry_ids"], [])
        chat = self._chat(agent_setup_id=setup["id"], work_mode="plan")
        asset = RetainedAssetService(self.app.state.app_store).retain_upload(RetainedUploadRequest(
            session_id=chat["id"], filename="source.md", content_type="text/markdown",
            content_base64=base64.b64encode(b"DOC_RECEIPT_77").decode()))
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "read_attachment", "args": {"asset_id": asset.id}, "id": "read-doc"}]),
            AIMessage(content="Cited the document."),
        ])
        started = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Read the attached source.", "attachment_ids": [asset.id]})
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, chat["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        presented = set(run["presented_tools"])
        self.assertIn("read_attachment", presented)
        self.assertIn("read_tool_result", presented)
        self.assertFalse(presented & {"ls", "glob", "grep", "execute", "delete"})
        diagnostic = self.client.get(f"/v1/agent-runs/{finished['current_run_id']}", params={"view": "diagnostic"})
        self.assertIn("DOC_RECEIPT_77", str(diagnostic.json()))

    def test_installed_research_skill_does_not_add_project_filesystem(self) -> None:
        installed = self.client.post("/v1/knowledge/skills/bundled/evidence-research/install", json={})
        self.assertEqual(installed.status_code, 200, installed.text)
        setup = self._save_template()
        self.assertEqual(setup["configuration"]["skill_entry_ids"], [installed.json()["id"]])
        chat = self._chat(agent_setup_id=setup["id"])
        asset = RetainedAssetService(self.app.state.app_store).retain_upload(RetainedUploadRequest(
            session_id=chat["id"], filename="source.md", content_type="text/markdown",
            content_base64=base64.b64encode(b"SKILL_RECEIPT_77").decode()))
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "read_attachment", "args": {"asset_id": asset.id}, "id": "read-doc"}]),
            AIMessage(content="Cited the skilled document."),
        ])
        started = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={
            "task": "Read the attached source with the research skill.", "attachment_ids": [asset.id]})
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, chat["id"])
        admitted = finished["current_run"]
        self.assertEqual(admitted["status"], "completed", admitted.get("error"))
        self.assertIn("read_attachment", admitted["presented_tools"])
        self.assertIn("read_tool_result", admitted["presented_tools"])
        self.assertFalse(set(admitted["presented_tools"]) & {"glob", "grep", "execute", "delete"})
        self.assertIn("SKILL_RECEIPT_77", str(self.client.get(
            f"/v1/agent-runs/{finished['current_run_id']}", params={"view": "diagnostic"}).json()))

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

    def test_project_bound_research_keeps_project_reads(self) -> None:
        setup = self._save_template()
        run = self._finish(self._chat(agent_setup_id=setup["id"], project_path=str(self.project), work_mode="plan"))
        presented = set(run["presented_tools"])
        self.assertTrue({"ls", "read_file", "glob", "grep", "read_tool_result"} <= presented)
        self.assertNotIn("execute", presented)
        self.assertNotIn("delete", presented)


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
            if item["id"] not in {"browser-validator", "windows-validator"}]
        self.assertGreaterEqual(len(templates), 4)
        for template in templates:
            pins = template["configuration"]["input_policy"]["pinned_tools"]
            self.assertIn("read_tool_result", template["configuration"]["presented_tools"])
            if template["id"] in {"guarded-project-builder", "trusted-project-builder"}:
                self.assertNotIn("read_tool_result", pins)
            else:
                self.assertIn("read_tool_result", pins)
            setup = self._save(template["name"] + " retained", template["configuration"])
            extra = {"project_path": str(self.project)} if template["configuration"].get("requires_project") else {}
            chat = self._chat(agent_setup_id=setup["id"], **extra)
            seeded = self._seed(chat["thread_id"])
            read = self._read(chat, seeded["path"])
            self.assertIn("read_tool_result", read["run"]["presented_tools"])
            self.assertIn("LATE_MARKER", str(read["diagnostic"]))
            calls = [call.get("name") for request in read["diagnostic"].get("model_requests") or []
                for message in request.get("messages") or [] for call in message.get("tool_calls") or []]
            self.assertEqual(calls, ["read_tool_result"])

    def test_browser_and_windows_templates_compile_the_reader(self) -> None:
        for template_id, codes in (
            ("browser-validator", {"browser_unavailable", "browser_worker_missing"}),
            ("windows-validator", {"desktop_grant_required", "desktop_unavailable", "desktop_runtime_unavailable"}),
        ):
            template = next(item for item in self.client.get("/v1/agent-setup-templates").json() if item["id"] == template_id)
            self.assertIn("read_tool_result", template["configuration"]["presented_tools"])
            self.assertIn("read_tool_result", template["configuration"]["input_policy"]["pinned_tools"])
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

    def test_exclusion_tools_off_owner_mismatch_and_read_file_fallback(self) -> None:
        self.assertIn("no accepted reader", continuation_notice(SimpleNamespace(presented_tools=[])))
        self.assertIn("Discovery cannot", continuation_notice(SimpleNamespace(presented_tools=[])))
        self.assertIn("cannot search inside one long line", continuation_notice(SimpleNamespace(presented_tools=["read_file"])))
        self.assertIn("read_tool_result", continuation_notice(SimpleNamespace(presented_tools=["read_tool_result", "read_file"])))

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
        off_calls = [call.get("name") for request in self.client.get(
            f"/v1/agent-runs/{off_run['id']}", params={"view": "diagnostic"}).json().get("model_requests") or []
            for message in request.get("messages") or [] for call in message.get("tool_calls") or []]
        self.assertEqual(off_calls, [])

        owned = self._save("Owner", {"presented_tools": ["read_tool_result"]})
        owner_chat = self._chat(agent_setup_id=owned["id"])
        other = self._seed("another-owner")
        mismatch = self._read(owner_chat, other["path"])
        outcome = mismatch["diagnostic"]["tool_outcomes"]["read-kept"]
        self.assertEqual(outcome["outcome"], "failed")
        self.assertIn("another owner", outcome["result"])
        self.assertNotIn("LATE_MARKER", outcome["result"])
