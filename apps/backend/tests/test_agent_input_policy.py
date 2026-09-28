"""Frozen disclosure semantics and native full-reference loading."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deepagents.backends.protocol import FileDownloadResponse

from workbench_backend.agents.effective_setup import compose_system_prompt
from workbench_backend.agents.input_sources import (
    WORKBENCH_CORE_INSTRUCTIONS, build_input_sources, create_input_preview, merge_input_policy,
)
from workbench_backend.agents.memory_skills import (
    configured_memory_middleware, plan_knowledge_materialization,
    reference_context, reference_tool_for_plan,
)
from workbench_backend.agents.setup_schemas import AgentInputPolicy, InstructionLayer
from workbench_backend.errors import HarnessError, KnowledgeError
from workbench_backend.knowledge.packages import guided_skill_source, parse_skill_requirements
from workbench_backend.knowledge.schemas import (
    KnowledgeCreateRequest, KnowledgeEditRequest, KnowledgeRevertRequest,
    KnowledgeVersion, SkillPackageImportRequest,
)
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.paths import WorkbenchPaths

SKILL = "---\nname: inspect-file\ndescription: Inspect a selected file.\nlicense: MIT # preserve\n---\n\nOriginal steps.\n"


def version(content, *, kind="memory", ident="one"):
    return KnowledgeVersion(id=f"v-{ident}", entry_id=ident, scope="user", kind=kind,
        content=content, provenance={"actor": "human"}, created_at="2026-09-28T00:00:00Z")


class FrozenBackend:
    def __init__(self, plan):
        self.files = dict(plan.uploads)

    def download_files(self, paths):
        return [FileDownloadResponse(path=path, content=self.files.get(path)) for path in paths]


class AgentInputPolicyTests(unittest.TestCase):
    def test_explicit_lists_replace_maps_merge_and_empty_override_clears(self):
        lower = AgentInputPolicy(tool_loading="always", pinned_tools=["echo"],
            reference_loading={"first": "always"}, excluded_sources=["project_outline"], instruction_override="old")
        merged = merge_input_policy(lower, AgentInputPolicy(reference_loading={"second": "off"}))
        self.assertEqual(merged.pinned_tools, ["echo"])
        self.assertEqual(merged.reference_loading, {"first": "always", "second": "off"})
        self.assertEqual(merged.instruction_override, "old")
        cleared = merge_input_policy(merged, AgentInputPolicy(pinned_tools=[], instruction_override=""))
        self.assertEqual(cleared.pinned_tools, [])
        self.assertEqual(cleared.instruction_override, "")
        self.assertEqual(merge_input_policy(cleared, AgentInputPolicy(instruction_override=None)).instruction_override, "")
        with self.assertRaises(HarnessError):
            merge_input_policy(None, AgentInputPolicy(excluded_sources=["access_policy"]))

    def test_authored_partial_policy_roundtrip_preserves_omissions_and_frozen_policy_is_full(self):
        from workbench_backend.agents.setup_schemas import SetupConfiguration
        authored = SetupConfiguration(input_policy=AgentInputPolicy(reference_loading={"one": "always"}))
        recovered = SetupConfiguration.model_validate_json(authored.model_dump_json())
        self.assertEqual(recovered.input_policy.model_fields_set, {"version", "reference_loading"})
        merged = merge_input_policy(AgentInputPolicy(pinned_tools=["echo"], excluded_sources=["project_outline"]), recovered.input_policy)
        self.assertEqual(merged.pinned_tools, ["echo"])
        self.assertEqual(merged.excluded_sources, ["project_outline"])
        self.assertEqual(set(merged.model_dump()), set(AgentInputPolicy.model_fields))

    def test_inspection_explicit_content_choice_preserves_frozen_cached_body(self):
        from workbench_backend.agents.setup_schemas import InputSourceRow, ResolvedSetupSelection, SetupConfiguration
        selection = ResolvedSetupSelection(configuration=SetupConfiguration(input_policy=AgentInputPolicy()),
            input_sources=[InputSourceRow(id="memory:one", title="Selected reference", kind="memory",
                origin="User Knowledge", reason="Frozen selection", content="Full original", estimated_tokens=3)])
        self.assertIsNone(create_input_preview(selection).sources[0].content)
        self.assertEqual(create_input_preview(selection, include_content=True).sources[0].content, "Full original")
        self.assertEqual(selection.input_sources[0].content, "Full original")

    def test_override_replaces_only_agent_block_and_preserves_verbatim_independent_sources(self):
        authored = "  replacement\nwith whitespace\n"
        prompt = compose_system_prompt(input_policy=AgentInputPolicy(instruction_override=authored), selected_agent=True,
            default_system_prompt="legacy", profile_system_prompt="Model guidance",
            surface_system_prompt=None, versions=[version("Protected", kind="protected_instruction")],
            instruction_layers=[InstructionLayer(name="Agent: Main", content="Old behaviour"),
                InstructionLayer(name="Turn overrides", content="Conversation note"),
                InstructionLayer(name="Task: Review", source_id="shortcut:2", content="Task instruction"),
                InstructionLayer(name="Selected project files", source_id="project", content="File context")])
        self.assertTrue(prompt.startswith(WORKBENCH_CORE_INSTRUCTIONS))
        self.assertNotIn("Old behaviour", prompt)
        for text in (authored, "Model guidance", "Conversation note", "Task instruction", "File context", "Protected"):
            self.assertIn(text, prompt)
        cleared = compose_system_prompt(input_policy=AgentInputPolicy(instruction_override=""), selected_agent=True,
            default_system_prompt="legacy", profile_system_prompt="Model guidance", surface_system_prompt=None,
            versions=[], instruction_layers=[InstructionLayer(name="Agent: Main", content="Old behaviour")])
        self.assertNotIn("Old behaviour", cleared)
        self.assertIn("Model guidance", cleared)

    def test_deferred_memory_has_metadata_but_reader_returns_entire_frozen_original(self):
        body = "<!-- retained original comment -->\n" + "Original fact.\n" * 500
        plan = plan_knowledge_materialization([version(body)], input_policy=AgentInputPolicy())
        self.assertEqual(plan.memory_sources, [])
        self.assertEqual(plan.uploads[0][1], body.encode("utf-8"))
        index = reference_context(plan)
        self.assertIn("v-one", index)
        self.assertNotIn("Original fact", index)
        backend = FrozenBackend(plan)
        reader = reference_tool_for_plan(backend, plan)
        self.assertEqual(reader.func("one", None), body)
        backend.files[plan.references[0].path] = b"changed later"
        with self.assertRaises(HarnessError) as changed:
            reader.func("one", None)
        self.assertEqual(changed.exception.code, "reference_version_changed")
        with self.assertRaises(HarnessError):
            reader.func("unselected", None)

    def test_reference_reader_runs_through_native_tool_node_with_runtime_injection(self):
        from langgraph.prebuilt import ToolNode
        from langgraph.graph import StateGraph, MessagesState, START, END
        from langchain_core.messages import AIMessage
        plan = plan_knowledge_materialization([version("Entire frozen source")], input_policy=AgentInputPolicy())
        reader = reference_tool_for_plan(FrozenBackend(plan), plan)
        builder = StateGraph(MessagesState)
        builder.add_node("tools", ToolNode([reader]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        result = builder.compile().invoke({"messages": [AIMessage(content="", tool_calls=[
            {"name": "read_reference", "args": {"entry_id": "one"}, "id": "native-reference-call"}])]})
        self.assertEqual(result['messages'][-1].content, 'Entire frozen source')

    def test_always_and_legacy_memory_reset_without_duplicate_v1_notice(self):
        full = version("Full original")
        plan = plan_knowledge_materialization([full], input_policy=AgentInputPolicy(reference_loading={"one": "always"}))
        middleware = configured_memory_middleware(FrozenBackend(plan), plan)[0]
        self.assertEqual(middleware.before_agent({}, None, None), {"memory_contents": {plan.memory_sources[0]: full.content}})
        self.assertIsNone(middleware._selection_notice)
        empty = configured_memory_middleware(FrozenBackend(plan), plan_knowledge_materialization([], input_policy=AgentInputPolicy()))[0]
        self.assertEqual(empty.before_agent({"memory_contents": {"old": "OLD"}}, None, None), {"memory_contents": {}})
        legacy = plan_knowledge_materialization([full])
        self.assertEqual(legacy.memory_sources, [legacy.uploads[0][0]])
        self.assertIsNotNone(configured_memory_middleware(FrozenBackend(legacy), legacy)[0]._selection_notice)

    def test_off_reference_uploads_no_body_and_source_estimate_is_zero(self):
        selected = version("Sensitive full reference")
        policy = AgentInputPolicy(reference_loading={"one": "off"})
        plan = plan_knowledge_materialization([selected], input_policy=policy)
        self.assertEqual(plan.uploads, [])
        self.assertIsNone(reference_tool_for_plan(FrozenBackend(plan), plan))
        row = next(row for row in build_input_sources(policy=policy, knowledge_versions=[selected], presented_tools=[]) if row.entry_id)
        self.assertEqual(row.mode, "off")
        self.assertEqual(row.estimated_tokens, 0)
        self.assertIsNone(row.content)
        self.assertIn("Earlier", row.history_hint)

    def test_skill_dependencies_roundtrip_preserves_unknown_yaml_and_frozen_metadata(self):
        changed, fields = guided_skill_source(SKILL, {"required_tools": ["read_file", "browser_navigate"],
            "required_connections": ["connection-id"], "requires_project": True})
        self.assertIn("license: MIT # preserve", changed)
        self.assertTrue(changed.endswith("Original steps.\n"))
        self.assertEqual(parse_skill_requirements(changed), {"required_tools": fields["required_tools"],
            "required_connections": ["connection-id"], "requires_project": True})
        unchanged, reopened = guided_skill_source(changed)
        self.assertEqual(unchanged, changed)
        self.assertEqual(reopened, fields)
        plan = plan_knowledge_materialization([version(changed, kind="skill")], input_policy=AgentInputPolicy())
        requirement = plan.skill_requirements["/skills/inspect-file/SKILL.md"]
        self.assertEqual(requirement.version_id, "v-one")
        self.assertEqual(requirement.required_tools, ["read_file", "browser_navigate"])
        self.assertTrue(requirement.requires_project)
        for invalid in (changed.replace('requires-project: true', 'requires-project: "yes"'),
                changed.replace('required-tools: ["read_file", "browser_navigate"]', 'required-tools: read_file')):
            with self.assertRaises(KnowledgeError):
                parse_skill_requirements(invalid)

    def test_native_skill_source_requirements_freeze_on_create_edit_and_import_before_body_read(self):
        source = SKILL.replace("license: MIT # preserve", "license: MIT # preserve\n"
            "required-tools: [echo]\nrequired-connections: [connection-one]\nrequires-project: true")
        edited_source = source.replace("[echo]", "[time_now]").replace(
            "[connection-one]", "[connection-two]").replace("requires-project: true", "requires-project: false")
        imported_source = edited_source.replace("[time_now]", "[read_file]")
        expected = [(["echo"], ["connection-one"], True),
            (["time_now"], ["connection-two"], False),
            (["read_file"], ["connection-two"], False)]
        with tempfile.TemporaryDirectory() as folder:
            service = KnowledgeService(WorkbenchPaths(root=Path(folder) / "data"))
            created = service.create(KnowledgeCreateRequest(scope="user", kind="skill", content=source))
            edited = service.edit(created.id, KnowledgeEditRequest(
                base_version=created.current_version_id, content=edited_source))
            package = Path(folder) / "skill"
            package.mkdir()
            (package / "SKILL.md").write_bytes(imported_source.encode("utf-8"))
            imported = service.import_skill(SkillPackageImportRequest(source_path=str(package),
                entry_id=created.id, base_version=edited.current_version_id))
            for entry, content, requirements in zip((created, edited, imported),
                    (source, edited_source, imported_source), expected):
                with self.subTest(version=entry.current_version_id):
                    frozen = service.get_version(entry.current_version_id)
                    self.assertEqual(entry.content, content)
                    self.assertEqual(frozen.content, content)
                    for record in (entry, frozen):
                        self.assertEqual((record.required_tools, record.required_connections,
                            record.requires_project), requirements)

            # A later edit/import cannot change the admitted version's requirements.
            frozen = service.get_version(created.current_version_id)
            plan = plan_knowledge_materialization([frozen], input_policy=AgentInputPolicy())
            reference = plan.references[0]
            self.assertEqual((reference.required_tools, reference.required_connections,
                reference.requires_project), expected[0])
            backend = FrozenBackend(plan)
            reader = reference_tool_for_plan(backend, plan)
            with patch.object(backend, "download_files", side_effect=AssertionError("body read before setup")):
                blocked = json.loads(reader.func(created.id, None))
            self.assertEqual(blocked["code"], "skill_setup_required")
            self.assertEqual(blocked["required_tools"], ["echo"])
            self.assertEqual(blocked["required_connections"], ["connection-one"])
            self.assertTrue(blocked["requires_project"])
            permitted = reference_tool_for_plan(backend, plan, require_ready=lambda reference, runtime: None)
            self.assertEqual(permitted.func(created.id, None), source)

    def test_always_skill_preflight_checks_tools_connections_and_project_without_enabling_them(self):
        from types import SimpleNamespace
        from workbench_backend.agents.setup_schemas import SetupConfiguration
        from workbench_backend.agents.setup_service import SetupService
        from workbench_backend.connections.schemas import ConnectionSnapshot, ConnectionTool
        source = SKILL.replace("license: MIT # preserve", "license: MIT # preserve\n"
            "required-tools: [echo]\nrequired-connections: [selected-connection]\nrequires-project: true")
        with tempfile.TemporaryDirectory() as folder:
            knowledge = KnowledgeService(WorkbenchPaths(root=Path(folder)))
            skill = knowledge.create(KnowledgeCreateRequest(scope="user", kind="skill", content=source))
            store = SimpleNamespace(get_deployment=lambda _: None, get_profile=lambda _: None, get_bundle=lambda _: None)
            ready = True
            setups = SetupService(None, SimpleNamespace(store=store), knowledge,
                connection_exists=lambda _: True, connection_available=lambda _: ready,
                connection_tools=lambda _: ["cx_saved_read"])
            config = SetupConfiguration(skill_version_refs=[skill.current_version_id], presented_tools=[],
                input_policy=AgentInputPolicy(reference_loading={skill.id: "always"}))
            blocked = setups.dependencies(config)
            self.assertEqual([(issue.kind, issue.id) for issue in blocked], [("skill_selection_required", skill.id)])
            for required in ("echo", "selected-connection", "Choose a project folder"):
                self.assertIn(required, blocked[0].reason)
            self.assertEqual(config.presented_tools, [])
            self.assertIsNone(config.connection_ids)

            selected = config.model_copy(update={"presented_tools": ["echo", "cx_saved_read"],
                "connection_ids": ["selected-connection"]})
            self.assertIn("Choose a project folder", setups.dependencies(selected)[0].reason)
            self.assertEqual(setups.dependencies(selected, project_bound=True), [])
            unused_connection = selected.model_copy(update={"presented_tools": ["echo"]})
            self.assertIn("Enable a tool from required connection",
                setups.dependencies(unused_connection, project_bound=True)[0].reason)
            ready = False
            self.assertIn("Set up required connection", setups.dependencies(selected, project_bound=True)[0].reason)
            frozen_connection = ConnectionSnapshot(id="selected-connection", name="Accepted", version=1,
                kind="mcp", transport="http", tools=[ConnectionTool(id="cx_saved_read", name="cx_saved_read",
                    remote_name="read", description="Read", input_schema={"type": "object"})])
            with patch.object(setups, "connection_tools", side_effect=AssertionError("latest manifest read")), \
                patch.object(setups, "connection_exists", side_effect=AssertionError("latest connection read")), \
                patch.object(setups, "connection_available", side_effect=AssertionError("runtime owns frozen readiness")):
                self.assertEqual(setups.dependencies(selected, frozen=True,
                    connection_snapshots=[frozen_connection], project_bound=True), [])
            knowledge.edit(skill.id, KnowledgeEditRequest(base_version=skill.current_version_id,
                content=source.replace("[echo]", "[time_now]")))
            self.assertEqual(setups.always_skill_requirements(selected), ({"echo"}, {"selected-connection"}))
            deferred = selected.model_copy(update={"input_policy": AgentInputPolicy(), "presented_tools": ["time_now"]})
            self.assertEqual(setups.dependencies(deferred), [], "Deferred requirements must remain on-use")
            off = config.model_copy(update={"input_policy": AgentInputPolicy(reference_loading={skill.id: "off"})})
            self.assertEqual(setups.dependencies(off), [])

    def test_memory_description_freezes_preserves_when_omitted_and_reverts(self):
        with tempfile.TemporaryDirectory() as folder:
            service = KnowledgeService(WorkbenchPaths(root=Path(folder)))
            first = service.create(KnowledgeCreateRequest(scope="user", kind="memory", content="one", description="Use for review"))
            first_version = service.get_version(first.current_version_id)
            second = service.edit(first.id, KnowledgeEditRequest(base_version=first.current_version_id, content="two"))
            self.assertEqual(second.description, "Use for review")
            cleared = service.edit(first.id, KnowledgeEditRequest(base_version=second.current_version_id, content="three", description=None))
            self.assertIsNone(cleared.description)
            reverted = service.revert(first.id, KnowledgeRevertRequest(base_version=cleared.current_version_id, target_version_id=first.current_version_id))
            self.assertEqual(reverted.description, first_version.description)
            self.assertEqual(service.get_version(first.current_version_id).content, "one")

    def test_actual_source_and_tool_definitions_follow_capture_privacy(self):
        from workbench_backend.agents.schemas import ModelRequestCapture
        from workbench_backend.agents.setup_schemas import InputSourceRow
        from workbench_backend.knowledge.diagnostics import apply_capture_policy
        from workbench_backend.knowledge.schemas import ContextCaptureSettings
        secret = "api_key=abcdefghijklmnop0123456789"
        capture = ModelRequestCapture(at="2026-09-28T00:00:00Z", input_sources=[InputSourceRow(
            id="memory:one", title=secret, kind="memory", origin="Knowledge", reason="Selected",
            entry_id="one", version_id="v-one", content=secret, required_tools=[secret], required_connections=[secret])],
            tool_schemas=[{"name": "selected_tool", "description": secret}])
        redacted = apply_capture_policy(capture, ContextCaptureSettings(redaction_mode="redact_secrets"))
        self.assertNotIn(secret, redacted.model_dump_json())
        self.assertTrue(redacted.redacted)
        discarded = apply_capture_policy(capture, ContextCaptureSettings(redaction_mode="discard"))
        self.assertEqual(discarded.tool_schemas, [])
        self.assertIsNone(discarded.input_sources[0].content)
        self.assertEqual(discarded.input_sources[0].version_id, "v-one")
        self.assertEqual(discarded.input_sources[0].required_tools, [])
        self.assertEqual(discarded.input_sources[0].required_connections, [])
        self.assertNotIn(secret, discarded.model_dump_json())


if __name__ == "__main__":
    unittest.main()
