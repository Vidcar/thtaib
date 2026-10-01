"""Opt-in runtime workflows and templates stay on native selection/version paths."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.app import create_app
from workbench_backend.agents.memory_skills import plan_knowledge_materialization
from workbench_backend.agents.setup_schemas import AgentInputPolicy
from workbench_backend.knowledge.bundled_skills import SKILL_IDS
from tests.support import close_workbench_sqlite, offline_workbench_client


class BundledRuntimeSkillsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def install(self, slug, **values):
        response = self.client.post(f"/v1/knowledge/skills/bundled/{slug}/install", json=values)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_catalogue_is_inert_and_all_nine_install_native_versions(self):
        response = self.client.get("/v1/knowledge/skills/bundled")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({item["id"] for item in response.json()}, set(SKILL_IDS))
        self.assertEqual(self.app.state.knowledge.list_entries(), [])
        for slug in SKILL_IDS:
            entry = self.install(slug)
            self.assertEqual(entry["kind"], "skill")
            self.assertEqual(entry["provenance"]["actor"], "human")
            self.assertEqual(len(entry["resources"]), 1)
            self.assertTrue(entry["resources"][0]["path"].startswith("references/"))
            resource = self.client.get(f'/v1/knowledge/versions/{entry["current_version_id"]}/resource', params={"path": entry["resources"][0]["path"]}).json()
            self.assertFalse(resource["execution_available"])
        self.assertEqual(self.app.state.app_store.list_agent_setups(), [])
        self.assertEqual(self.app.state.preferences.grants(), [])

    def test_install_is_idempotent_and_preserves_user_changes(self):
        first = self.install("failure-diagnosis")
        changed = self.client.post(f'/v1/knowledge/entries/{first["id"]}/edit', json={"base_version": first["current_version_id"], "content": first["content"] + "\nUser refinement.\n"}).json()
        again = self.install("failure-diagnosis")
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(again["current_version_id"], changed["current_version_id"])
        self.assertIn("User refinement.", again["content"])

    def test_unknown_skill_or_scope_cannot_import(self):
        self.assertEqual(self.client.post("/v1/knowledge/skills/bundled/unknown/install", json={}).status_code, 404)
        self.assertEqual(self.client.post("/v1/knowledge/skills/bundled/project-change/install", json={"scope": "project", "scope_id": "missing"}).status_code, 409)
        self.assertEqual(self.app.state.knowledge.list_entries(), [])

    def test_off_deselected_and_frozen_versions_keep_native_semantics(self):
        entry = self.install("failure-diagnosis")
        version = self.app.state.knowledge.get_version(entry["current_version_id"])
        plan = plan_knowledge_materialization([version], self.app.state.knowledge.resource_bytes,
            input_policy=AgentInputPolicy(reference_loading={entry["id"]: "when_needed"}))
        self.assertEqual(plan.references[0].mode, "when_needed")
        self.assertEqual(plan.references[0].path, "/skills/failure-diagnosis/SKILL.md")
        off = plan_knowledge_materialization([version], self.app.state.knowledge.resource_bytes,
            input_policy=AgentInputPolicy(reference_loading={entry["id"]: "off"}))
        self.assertEqual(off.uploads, [])
        self.assertEqual(plan_knowledge_materialization([]).uploads, [])
        self.client.patch(f'/v1/knowledge/entries/{entry["id"]}', json={"enabled": False})
        frozen = self.app.state.knowledge.resolve_refs(skill_version_refs=[version.id], frozen=True)
        self.assertEqual(frozen.skill_version_refs, [version.id])

    def test_templates_use_real_installed_ids_without_changing_access(self):
        empty = self.client.get("/v1/agent-setup-templates").json()
        self.assertEqual(len(empty), 6)
        self.assertTrue(all(not item["configuration"]["skill_entry_ids"] for item in empty))
        installed = self.install("project-change")
        templates = self.client.get("/v1/agent-setup-templates").json()
        builder = next(item for item in templates if item["id"] == "guarded-project-builder")
        self.assertEqual(builder["configuration"]["skill_entry_ids"], [installed["id"]])
        for item in templates:
            config = item["configuration"]
            self.assertIsNone(config["approval_mode"])
            self.assertIsNone(config["work_mode"])
            self.assertIsNone(config["desktop_access"])
            self.assertEqual(config["connection_ids"], [])
            self.assertEqual(config["helper_agent_ids"], [])
            self.assertFalse(config["review"]["enabled"])
        reviewer = next(item for item in templates if item["id"] == "read-only-reviewer")
        self.assertFalse(set(reviewer["configuration"]["presented_tools"]) & {"write_file", "edit_file", "delete", "execute", "start_preview"})
        self.assertEqual(self.app.state.app_store.list_agent_setups(), [])
