"""Canonical folders, immutable setup versions and real Chat dispatch selection."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.inference.schemas import (
    BundleSource, ConnectedDeploymentRequest, Deployment, DeploymentStatus,
    LocalImportRequest, ManagementScope, ModelBundle, ModelConfigurationWriteRequest, RunProfile,
)
from workbench_backend.inference.settings import resolve_bags
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, write_tiny_gguf
from tests.test_chat import wait_for_chat


class ProjectSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)
        self.folder = self.root / "project"
        self.folder.mkdir()
        (self.folder / "sample.txt").write_text("original", encoding="utf-8")
        self.deployment = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(display_name="Fixture", endpoint="http://127.0.0.1:9/v1"))

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def project(self, **values):
        return self.post("/v1/projects", {"path": str(self.folder), **values})

    def setup(self, **configuration):
        return self.post("/v1/agent-setups", {"name": "Helper", "configuration": {"deployment_id": self.deployment.id, **configuration}})

    def test_reference_exclusion_precedes_latest_resolution_and_keeps_control_row(self):
        memory = self.post('/v1/knowledge/entries', {'scope': 'user', 'kind': 'memory', 'display_name': 'Saved review facts', 'content': 'Full secret reference'})
        setup = self.setup(memory_entry_ids=[memory['id']], input_policy={'pinned_tools': ['echo']})
        first = self.post('/v1/setup-resolution', {'agent_setup_id': setup['id']})
        self.assertEqual(first['configuration']['input_policy']['reference_loading'], {})
        self.assertEqual(first['configuration']['memory_version_refs'], [memory['current_version_id']])
        entry = self.app.state.knowledge.store.get_entry(memory['id'])
        self.app.state.knowledge.store.put_entry(entry.model_copy(update={'active': False}))
        with patch.object(self.app.state.knowledge, 'get_version', side_effect=AssertionError('Off inspected a version body')):
            resolved = self.post('/v1/setup-resolution', {'agent_setup_id': setup['id'], 'include_input_content': True,
                'overrides': {'input_policy': {'excluded_sources': [f'memory:{memory["id"]}']}}})
        self.assertEqual(resolved['configuration']['memory_version_refs'], [])
        self.assertEqual(resolved['configuration']['memory_entry_ids'], [memory['id']])
        self.assertEqual(resolved['configuration']['input_policy']['pinned_tools'], ['echo'])
        row = next(row for row in resolved['input_sources'] if row['entry_id'] == memory['id'])
        self.assertEqual(row['mode'], 'off')
        self.assertEqual(row['title'], 'Saved review facts')
        self.assertEqual(row['origin'], 'user Knowledge')
        self.assertEqual(row['estimated_tokens'], 0)
        self.assertIsNone(row['content'])
        self.assertIn('Earlier', row['history_hint'])

    def test_cold_preview_expands_native_schemas_without_starting_workers_or_model(self):
        with patch.object(self.app.state.manager, 'ensure_deployment_ready', side_effect=AssertionError('preview started a model')):
            resolved = self.post('/v1/setup-resolution', {'include_input_content': True,
                'overrides': {'deployment_id': self.deployment.id, 'presented_tools': ['read_file', 'desktop_search', 'start_preview'],
                    'input_policy': {'pinned_tools': ['read_file']}}})
        tools = {row['tool_name']: row for row in resolved['input_sources'] if row['tool_name']}
        for name in ('read_file', 'desktop_search', 'start_preview'):
            self.assertIn(name, tools[name]['content'])
        self.assertIn('Project-relative', tools['read_file']['content'])
        self.assertIn('selector', tools['desktop_search']['content'])
        self.assertIn('entry_path', tools['start_preview']['content'])

    def test_frozen_reference_reading_routes_require_action_without_widening(self):
        memory = self.post('/v1/knowledge/entries', {'scope': 'user', 'kind': 'memory', 'content': 'Entire original'})
        skill = self.post('/v1/knowledge/entries', {'scope': 'user', 'kind': 'skill',
            'content': '---\nname: inspect-context\ndescription: Inspect selected context.\n---\n\nOriginal steps.\n'})

        def resolve(**overrides):
            return self.client.post('/v1/setup-resolution', json={'overrides': overrides})

        # Exact version refs also need a reader, even when no entry-id list was authored.
        no_tools = resolve(presented_tools=[], memory_version_refs=[memory['current_version_id']])
        self.assertEqual(no_tools.status_code, 409, no_tools.text)
        self.assertEqual(no_tools.json()['code'], 'deferred_reference_tools_off')
        memory_excluded = resolve(presented_tools=['echo'], memory_version_refs=[memory['current_version_id']],
            input_policy={'excluded_sources': ['tool:read_reference']})
        self.assertEqual(memory_excluded.status_code, 409, memory_excluded.text)
        self.assertEqual(memory_excluded.json()['code'], 'deferred_reference_reader_excluded')
        self.assertIn('Include now, Remove, or Enable reading', memory_excluded.json()['error'])
        both_excluded = resolve(presented_tools=['echo', 'read_file'], skill_version_refs=[skill['current_version_id']],
            input_policy={'excluded_sources': ['tool:read_reference', 'tool:read_file']})
        self.assertEqual(both_excluded.status_code, 409, both_excluded.text)
        self.assertEqual(both_excluded.json()['code'], 'deferred_reference_reader_excluded')
        file_route = resolve(presented_tools=['read_file'], skill_version_refs=[skill['current_version_id']],
            input_policy={'excluded_sources': ['tool:read_reference']})
        self.assertEqual(file_route.status_code, 200, file_route.text)
        self.assertEqual(file_route.json()['configuration']['presented_tools'], ['read_file'])
        included = resolve(presented_tools=[], memory_version_refs=[memory['current_version_id']],
            input_policy={'reference_loading': {memory['id']: 'always'}})
        self.assertEqual(included.status_code, 200, included.text)
        self.assertEqual(included.json()['configuration']['presented_tools'], [])

    def test_progressive_connection_defers_readiness_but_rejects_disabled_and_unknown_records(self):
        from workbench_backend.connections.schemas import ConnectionRecord, ConnectionTool
        from workbench_backend.inference.ids import utc_now
        record = ConnectionRecord(id='connection-deferred', name='Saved disconnected connection', version=1,
            kind='mcp', transport='http', url='http://127.0.0.1:9/mcp',
            tools=[ConnectionTool(id='descriptor', name='cx_saved_read', remote_name='read', description='Read remote text', input_schema={'type': 'object', 'properties': {}})],
            created_at=utc_now(), updated_at=utc_now(), last_error='Disconnected')
        self.app.state.connections.store.put(record)
        with patch.object(self.app.state.connections, 'available', side_effect=AssertionError('deferred preview tested a connection')), \
                patch.object(self.app.state.connections, 'get', side_effect=AssertionError('preview read credentials')):
            resolved = self.post('/v1/setup-resolution', {'include_input_content': True,
                'overrides': {'connection_ids': [record.id], 'presented_tools': ['cx_saved_read']}})
        self.assertEqual(resolved['configuration']['connection_ids'], [record.id])
        self.assertEqual(resolved['configuration']['presented_tools'], ['cx_saved_read'])
        source = next(row for row in resolved['input_sources'] if row['tool_name'] == 'cx_saved_read')
        self.assertIn('Read remote text', source['content'])
        self.assertIn('"parameters"', source['content'])
        self.assertEqual(source['mode'], 'when_needed')
        self.assertEqual(source['estimated_tokens'], 0)
        with patch.object(self.app.state.connections, 'get', side_effect=AssertionError('snapshot read credentials')):
            snapshots = self.app.state.connections.snapshot([record.id], allow_unready=True)
        self.assertEqual(snapshots[0].tools, record.tools)
        self.assertEqual(snapshots[0].version, record.version)
        eager = self.client.post('/v1/setup-resolution', json={'overrides': {'connection_ids': [record.id], 'input_policy': {'tool_loading': 'always'}}})
        self.assertEqual(eager.status_code, 409, eager.text)
        self.app.state.connections.store.put(record.model_copy(update={'enabled': False}))
        for ident in (record.id, 'unknown'):
            rejected = self.client.post('/v1/setup-resolution', json={'overrides': {'connection_ids': [ident]}})
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(rejected.json()['missing_dependencies'][0]['kind'], 'connection')

    def test_helper_connections_freeze_exact_metadata_inside_parent_selection(self):
        from workbench_backend.agents.helpers import freeze_helpers
        from workbench_backend.connections.schemas import ConnectionRecord, ConnectionTool
        from workbench_backend.inference.ids import utc_now
        records = []
        for ident in ('permitted', 'outside'):
            record = ConnectionRecord(id=ident, name=f'Saved {ident}', version=1,
                kind='mcp', transport='http', url='http://127.0.0.1:9/mcp', credential_ref='opaque-reference',
                tools=[ConnectionTool(id=f'cx_{ident}', name=f'cx_{ident}', remote_name='read',
                    description='Read accepted text', input_schema={'type': 'object', 'properties': {'original': {'type': 'string'}}})],
                created_at=utc_now(), updated_at=utc_now())
            self.app.state.connections.store.put(record)
            records.append(record)
        helper = self.setup(presented_tools=['echo'], connection_ids=['permitted', 'outside'])
        parent = SetupConfiguration(deployment_id=self.deployment.id, presented_tools=['echo'], connection_ids=['permitted'])
        with patch.object(self.app.state.connections, 'get', side_effect=AssertionError('helper freeze read credentials')):
            frozen, = freeze_helpers(self.app.state.setups, [helper['id']], parent_configuration=parent,
                connection_snapshot=self.app.state.connections.snapshot)
        self.assertEqual([item.id for item in frozen.connection_snapshots], ['permitted'])
        self.assertEqual(frozen.configuration.connection_ids, ['permitted'])
        self.assertEqual(frozen.connection_snapshots[0].tools, records[0].tools)
        with patch.object(self.app.state.setups, 'connection_tools', side_effect=AssertionError('accepted catalogue refreshed')), \
            patch.object(self.app.state.setups, 'connection_exists', side_effect=AssertionError('accepted dependency refreshed')):
            self.assertEqual(self.app.state.setups.dependencies(frozen.configuration, frozen=True,
                connection_snapshots=frozen.connection_snapshots), [])
            widened = frozen.configuration.model_copy(update={'connection_ids': ['permitted', 'outside']})
            issues = self.app.state.setups.dependencies(widened, frozen=True,
                connection_snapshots=frozen.connection_snapshots)
        self.assertEqual([(issue.kind, issue.id) for issue in issues], [('connection', 'outside')])
        original = frozen.model_dump_json()
        changed = records[0].model_copy(deep=True)
        changed.version = 2
        changed.tools[0].input_schema = {'type': 'object', 'properties': {'later': {'type': 'integer'}}}
        self.app.state.connections.store.put(changed)
        self.assertEqual(frozen.model_dump_json(), original)
        self.assertIn('original', frozen.connection_snapshots[0].tools[0].input_schema['properties'])
        self.assertNotIn('later', frozen.connection_snapshots[0].tools[0].input_schema['properties'])
        self.assertNotIn('credential_present', original)

    def test_project_aliases_removal_and_fixed_chat_area(self):
        project = self.project(name="Work")
        alias = self.project(path=str(self.folder / ".." / "project"))
        self.assertEqual(project["id"], alias["id"])
        chat = self.post("/v1/chat/conversations", {"project_id": project["id"], "deployment_id": self.deployment.id})
        self.assertEqual(chat["area_id"], project["id"])
        self.assertEqual(chat["area_label"], "Work")
        listing = self.client.get(f'/v1/projects/{project["id"]}/files').json()
        self.assertEqual(listing["path"], "")
        self.assertEqual(listing["entries"][0]["path"], "sample.txt")
        self.assertEqual(self.client.get(f'/v1/projects/{project["id"]}/files', params={"path": ".."}).status_code, 403)
        read = self.client.get(f'/v1/projects/{project["id"]}/file', params={"path": "sample.txt"})
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["text"], "original")
        self.assertIsNone(read.json()["text_unavailable_reason"])
        self.assertEqual(self.client.get(f'/v1/projects/{project["id"]}/file', params={"path": "../sample.txt"}).status_code, 403)
        self.assertEqual(self.client.get(f'/v1/projects/{project["id"]}/file', params={"path": "memories/note.txt"}).status_code, 403)
        binary = self.folder / "binary.dat"
        binary.write_bytes(b"\x00\x01not text")
        unread = self.client.get(f'/v1/projects/{project["id"]}/file', params={"path": "binary.dat"})
        self.assertEqual(unread.status_code, 200, unread.text)
        self.assertIsNone(unread.json()["text"])
        self.assertIn("not UTF-8", unread.json()["text_unavailable_reason"])
        link = self.folder / "linked"
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        denied = self.client.get(f'/v1/projects/{project["id"]}/file', params={"path": "linked/secret.txt"})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertNotIn("secret", denied.text)
        self.assertEqual(self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={"task": "go", "project_id": None}).status_code, 409)
        removed = self.client.delete(f'/v1/projects/{project["id"]}').json()
        self.assertFalse(removed["active"])
        self.assertEqual((self.folder / "sample.txt").read_text(), "original")
        self.assertEqual(self.client.get(f'/v1/chat/conversations/{chat["id"]}').json()["area_id"], project["id"])
        self.assertEqual(self.client.get('/v1/projects').json(), [])
        self.assertEqual(self.project()["id"], project["id"])

    def test_versions_conflicts_duplicate_and_dependency_removal(self):
        setup = self.setup(presented_tools=[])
        payload = {"base_version": setup["current_version_id"], "name": "Renamed", "configuration": setup["configuration"]}
        updated = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json=payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(self.client.patch(f'/v1/agent-setups/{setup["id"]}', json=payload).status_code, 409)
        versions = self.client.get(f'/v1/agent-setups/{setup["id"]}/versions').json()
        self.assertEqual([v["name"] for v in versions], ["Helper", "Renamed"])
        copied = self.post(f'/v1/agent-setups/{setup["id"]}/duplicate', {})
        self.assertNotEqual(copied["id"], setup["id"])
        self.app.state.manager.store.delete_deployment(self.deployment.id)
        view = self.client.get(f'/v1/agent-setups/{setup["id"]}').json()
        self.assertEqual(view["missing_dependencies"][0]["id"], self.deployment.id)
        self.assertEqual(view["helper_missing_dependencies"][0]["id"], self.deployment.id)
        failed = self.client.post('/v1/setup-resolution', json={"agent_setup_version_id": setup["current_version_id"]})
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["code"], "setup_dependencies_missing")
        self.client.delete(f'/v1/agent-setups/{setup["id"]}')
        self.assertEqual(len(self.client.get(f'/v1/agent-setups/{setup["id"]}/versions').json()), 2)

    def test_visual_tool_catalogue_round_trips_saved_agent(self):
        catalogue_response = self.client.get('/v1/agent-tools')
        self.assertEqual(catalogue_response.status_code, 200, catalogue_response.text)
        catalogue = catalogue_response.json()
        selected = catalogue['enabled']
        self.assertEqual([tool['id'] for tool in catalogue['tools']], selected)
        self.assertIn('browser_take_screenshot', selected)
        self.assertIn('desktop_screenshot', selected)
        created = self.client.post('/v1/agent-setups', json={
            'name': 'Visual tester',
            'configuration': {
                'deployment_id': self.deployment.id,
                'desktop_access': 'selected',
                'presented_tools': selected,
            },
        })
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()['configuration']['presented_tools'], selected)
        self.assertEqual(created.json()['configuration']['desktop_access'], 'selected')
        resolved = self.post('/v1/setup-resolution', {'agent_setup_id': created.json()['id']})
        self.assertIsNone(resolved['configuration']['desktop_access'], 'saved intention cannot grant Windows access')

    def test_named_layers_and_empty_selection_do_not_erase_protected_restrictions(self):
        self.app.state.app_store.put_setup_defaults(SetupConfiguration(approval_mode="full_access"))
        project = self.project()
        setup = self.setup(instructions="AGENT", presented_tools=[], requires_project=True)
        resolved = self.post('/v1/setup-resolution', {"project_id": project["id"], "agent_setup_version_id": setup["current_version_id"], "overrides": {"instructions": "TURN", "requires_project": False}})
        self.assertEqual(resolved["configuration"]["presented_tools"], [])
        self.assertTrue(resolved["configuration"]["requires_project"])
        self.assertEqual([i["content"] for i in resolved["instruction_layers"]], ["AGENT", "TURN"])

    def test_dependency_preview_matches_inherited_application_selection(self):
        self.app.state.app_store.put_setup_defaults(SetupConfiguration(approval_mode="full_access"))
        setup = self.setup(profile_id='removed-preset', presented_tools=[])
        self.assertEqual([(issue['kind'], issue['id']) for issue in setup['missing_dependencies']], [('profile_id', 'removed-preset')])
        self.assertEqual([(issue['kind'], issue['id']) for issue in setup['helper_missing_dependencies']], [('profile_id', 'removed-preset')])
        rejected = self.client.post('/v1/setup-resolution', json={'agent_setup_id': setup['id']})
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()['code'], 'setup_dependencies_missing')

    def test_edit_cannot_reactivate_setup_removed_before_version_commit(self):
        setup = self.setup(presented_tools=[])
        store = self.app.state.app_store
        save = store.save_agent_setup

        def remove_before_commit(record, version=None, *, base_version=None):
            if base_version is not None:
                current = store.get_agent_setup(record.id)
                save(current.model_copy(update={'active': False}))
            return save(record, version, base_version=base_version)

        with patch.object(store, 'save_agent_setup', side_effect=remove_before_commit):
            response = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json={
                'name': 'Stale edit', 'base_version': setup['current_version_id'], 'configuration': setup['configuration']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertFalse(store.get_agent_setup(setup['id']).active)
        self.assertEqual(len(store.list_agent_setup_versions(setup['id'])), 1)

    def test_tools_off_does_not_require_inactive_connection(self):
        setup = self.setup(presented_tools=[], connection_ids=['removed-connection'])
        self.assertEqual(setup['missing_dependencies'], [])
        resolved = self.post('/v1/setup-resolution', {'agent_setup_version_id': setup['current_version_id']})
        self.assertEqual(resolved['configuration']['presented_tools'], [])
        enabled = self.client.post('/v1/setup-resolution', json={
            'agent_setup_version_id': setup['current_version_id'], 'overrides': {'presented_tools': ['echo']}})
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.assertEqual(enabled.json()['configuration']['presented_tools'], [], 'Chat cannot turn tools on for an agent')

    def test_dependency_preview_reports_different_model_and_deployment(self):
        from workbench_backend.inference.schemas import ModelBundle, BundleSource
        self.app.state.manager.store.put_bundle(ModelBundle(id='other-model', display_name='Other model',
            source=BundleSource(kind='local'), files=[], created_at=self.deployment.created_at))
        setup = self.setup(bundle_id='other-model', presented_tools=[])
        self.assertTrue(any(issue['kind'] == 'bundle_id' and 'different model' in issue['reason'] for issue in setup['missing_dependencies']), setup)
        self.assertTrue(any(issue['kind'] == 'bundle_id' and 'different model' in issue['reason'] for issue in setup['helper_missing_dependencies']), setup)
        response = self.client.post('/v1/setup-resolution', json={'agent_setup_version_id': setup['current_version_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['code'], 'setup_dependencies_missing')

    def test_same_bundle_variant_never_inherits_another_variant_deployment(self):
        store = self.app.state.manager.store
        store.put_bundle(ModelBundle(id='variant-model', display_name='Variant model',
            source=BundleSource(kind='local'), files=[], created_at=self.deployment.created_at))
        first = store.put_profile(RunProfile(id='variant-a', display_name='A', bundle_id='variant-model',
            bags=resolve_bags(startup={'ctx_size': 2048}),
            created_at=self.deployment.created_at, updated_at=self.deployment.updated_at))
        second = store.put_profile(RunProfile(id='variant-b', display_name='B', bundle_id='variant-model',
            bags=resolve_bags(startup={'ctx_size': 4096}),
            created_at=self.deployment.created_at, updated_at=self.deployment.updated_at))
        a = store.put_deployment(Deployment(id='variant-deploy-a', display_name='A',
            scope=ManagementScope.managed, status=DeploymentStatus.stopped,
            bundle_id='variant-model', profile_id=first.id, settings=first.bags,
            created_at=self.deployment.created_at, updated_at=self.deployment.updated_at))
        request = {'overrides': {'model_configuration_id': second.id, 'deployment_id': a.id}}
        unresolved = self.post('/v1/setup-resolution', request)
        self.assertIsNone(unresolved['configuration']['deployment_id'])
        b = store.put_deployment(Deployment(id='variant-deploy-b', display_name='B',
            scope=ManagementScope.managed, status=DeploymentStatus.stopped,
            bundle_id='variant-model', profile_id=second.id, settings=second.bags,
            created_at=self.deployment.created_at, updated_at=self.deployment.updated_at))
        resolved = self.post('/v1/setup-resolution', request)
        self.assertEqual(resolved['configuration']['deployment_id'], b.id)
        self.assertEqual(resolved['configuration']['profile_id'], second.id)

    def test_model_editor_preview_uses_conversation_scope_and_keeps_defaults_unrequested(self):
        manager = self.app.state.manager
        file = write_tiny_gguf(self.root / 'model-preview.gguf')
        bundle_id = manager.import_local(LocalImportRequest(source_path=str(file))).bundle_id
        saved_startup = {'n_gpu_layers': 'all', 'fit': 'off', 'cache_type_k': 'q4_0', 'cache_type_v': 'q4_0'}
        profile = manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(
            display_name='All GPU', startup=saved_startup))
        deployments_before = [deployment.id for deployment in manager.list_deployments()]
        options = manager.get_bundle_configuration_options(bundle_id)
        self.assertIn('all', [option.value for option in options.gpu_layers.options])
        self.assertEqual(options.startup_defaults['cache_type_k'].applied, 'f16')
        self.assertEqual(options.startup_defaults['fit'].applied, 'on')

        def preview(startup=None):
            overrides = {'model_configuration_id': profile.id}
            if startup is not None:
                overrides['startup_overrides'] = startup
            return self.post('/v1/setup-resolution', {'editing_layer': 'conversation', 'overrides': overrides})

        saved = preview()
        self.assertEqual(saved['configuration']['model_configuration_id'], profile.id)
        self.assertEqual(saved['configuration']['profile_id'], profile.id)
        self.assertEqual(saved['configuration']['bundle_id'], bundle_id)
        for key, value in saved_startup.items():
            with self.subTest(saved=key):
                fact = saved['effective_values'][f'startup.{key}']
                self.assertEqual(fact['value'], value)
                self.assertEqual(fact['source'], 'Configuration: All GPU')
                self.assertTrue(fact['inherited'])
                self.assertIsNone(fact['requested_override'])

        draft_startup = {'n_gpu_layers': 0, 'fit': 'on', 'cache_type_k': 'f16', 'cache_type_v': 'f16'}
        draft = preview(draft_startup)
        self.assertEqual(draft['configuration']['startup_overrides'], draft_startup)
        for key, value in draft_startup.items():
            with self.subTest(draft=key):
                fact = draft['effective_values'][f'startup.{key}']
                self.assertEqual(fact['value'], value)
                self.assertEqual(fact['requested_override'], value)
                self.assertEqual(fact['inherited_value'], saved_startup[key])
                self.assertFalse(fact['inherited'])

        reset = preview({})
        self.assertEqual(reset['configuration']['startup_overrides'], {})
        for key, value in saved_startup.items():
            self.assertEqual(reset['effective_values'][f'startup.{key}']['value'], value)
            self.assertIsNone(reset['effective_values'][f'startup.{key}']['requested_override'])
        omitted = preview({'cache_type_k': None})
        self.assertIsNone(omitted['configuration']['startup_overrides']['cache_type_k'])
        self.assertEqual(omitted['effective_values']['startup.cache_type_k']['value'], 'f16')
        self.assertEqual(omitted['effective_values']['startup.cache_type_k']['inherited_value'], 'q4_0')

        for result in (saved, draft, reset, omitted):
            default = result['effective_values']['startup.flash_attn']
            # Auto is evaluated by the native loading plan; a cold preview does
            # not invent the runtime's eventual On/Off choice.
            self.assertIsNone(default['value'])
            self.assertFalse(default['known'])
            self.assertIsNone(default['requested_override'])
            self.assertNotIn('flash_attn', result['configuration']['startup_overrides'] or {})
        application = self.post('/v1/setup-resolution', {'editing_layer': 'application', 'overrides': {
            'approval_mode': 'full_access', 'model_configuration_id': profile.id,
            'startup_overrides': draft_startup, 'per_request_overrides': {'temperature': 0.2}}})
        self.assertEqual(application['configuration']['approval_mode'], 'full_access')
        for key in ('model_configuration_id', 'profile_id', 'bundle_id', 'deployment_id', 'startup_overrides', 'per_request_overrides'):
            self.assertIsNone(application['configuration'][key], key)
        self.assertEqual(manager.store.get_profile(profile.id).bags.startup.requested, saved_startup)
        self.assertEqual([deployment.id for deployment in manager.list_deployments()], deployments_before,
            'editor previews never prepare or start an inference process')

    def test_assigned_agent_model_missing_blocks_main_and_helper_roles(self):
        setup = self.post('/v1/agent-setups', {'name': 'Writer',
            'configuration': {'instructions': 'Write carefully.', 'deployment_id': 'missing-helper-model'}})
        self.assertEqual([(issue['kind'], issue['id']) for issue in setup['missing_dependencies']], [('deployment_id', 'missing-helper-model')])
        self.assertEqual([(issue['kind'], issue['id']) for issue in setup['helper_missing_dependencies']],
            [('deployment_id', 'missing-helper-model')])
        rejected = self.client.post('/v1/setup-resolution', json={'agent_setup_id': setup['id']})
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()['code'], 'setup_dependencies_missing')

    def test_explicit_null_clears_inherited_embedding_on_subsequent_turns(self):
        project = self.project(defaults={'embedding_deployment_id': self.deployment.id})
        resolved = self.post('/v1/setup-resolution', {'project_id': project['id'], 'overrides': {'embedding_deployment_id': None}})
        self.assertIsNone(resolved['configuration']['embedding_deployment_id'])
        chat = self.post('/v1/chat/conversations', {'project_id': project['id'], 'deployment_id': self.deployment.id})
        from workbench_backend.chat.schemas import ChatStartRequest
        conversation = self.app.state.app_store.get_conversation(chat['id'])
        self.app.state.chat._apply_start_configuration(conversation, ChatStartRequest(task='clear', embedding_deployment_id=None))
        self.app.state.app_store.put_conversation(conversation)
        reloaded = self.app.state.app_store.get_conversation(chat['id'])
        self.app.state.chat._apply_start_configuration(reloaded, ChatStartRequest(task='continue'))
        self.assertIsNone(reloaded.embedding_deployment_id)

    def test_chat_uses_latest_agent_record_and_saved_empty_tool_choice(self):
        setup = self.setup(instructions="AGENT ORIGINAL", presented_tools=["read_file"], per_request_overrides={"temperature": 0.2}, input_policy={"tool_loading": "always"})
        project = self.project()
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content="done")]))
        chat = self.post('/v1/chat/conversations', {"project_id": project["id"], "deployment_id": self.deployment.id, "agent_setup_id": setup["id"]})
        with patch.object(self.app.state.manager, 'ensure_deployment_ready', return_value=self.deployment):
            self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "hello"})
            first = wait_for_chat(self.client, chat["id"])
            run = first["current_run"]
            self.assertEqual(run["agent_setup_version_id"], setup["current_version_id"])
            self.assertIn("AGENT ORIGINAL", run["effective_setup"]["system_prompt"])
            self.assertEqual(run["effective_setup"]["bags"]["per_request"]["requested"]["temperature"], 0.2)
            self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "again", "presented_tools": []})
            second = wait_for_chat(self.client, chat["id"])
            self.assertEqual(second["thread_id"], first["thread_id"])
            self.assertEqual(second["current_run"]["presented_tools"], ["read_file"], 'Chat cannot replace agent-owned tools')
            updated = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json={'base_version': setup['current_version_id'], 'name': 'Edited agent', 'configuration': {'deployment_id': self.deployment.id, 'instructions': 'SAVED LATEST INSTRUCTIONS', 'presented_tools': []}})
            self.assertEqual(updated.status_code, 200, updated.text)
            self.post(f'/v1/chat/conversations/{chat["id"]}/start', {'task': 'use saved changes'})
            third = wait_for_chat(self.client, chat['id'])
            self.assertEqual(third['current_run']['agent_setup_version_id'], updated.json()['current_version_id'])
            self.assertEqual(third['current_run']['presented_tools'], [])
            self.assertIn('SAVED LATEST INSTRUCTIONS', third['current_run']['effective_setup']['system_prompt'])
            self.assertEqual(third['thread_id'], first['thread_id'])

    def test_general_chat_applies_explicit_turn_instructions(self):
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content="done")]))
        chat = self.post('/v1/chat/conversations', {"deployment_id": self.deployment.id})
        self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "hello", "instructions": "GENERAL TURN INSTRUCTIONS", "presented_tools": []})
        finished = wait_for_chat(self.client, chat['id'])
        self.assertEqual(finished['current_run']['status'], 'completed', finished['current_run'].get('error'))
        self.assertIn('GENERAL TURN INSTRUCTIONS', finished['current_run']['effective_setup']['system_prompt'])

    def test_queued_setup_retains_selected_version_and_project_instruction_snapshot(self):
        setup = self.setup(instructions='SAVED AGENT ORIGINAL', presented_tools=[])
        project = self.project()
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content="done")]))
        chat = self.post('/v1/chat/conversations', {'project_id': project['id'], 'deployment_id': self.deployment.id, 'agent_setup_version_id': setup['current_version_id']})
        queued = self.post(f'/v1/chat/conversations/{chat["id"]}/queue', {'task': 'queued work'})
        self.assertEqual(queued['queue'][0]['intended_config']['agent_setup_version_id'], setup['current_version_id'])
        self.assertEqual(self.client.patch(f'/v1/projects/{project["id"]}', json={'name': 'Project later edit'}).status_code, 200)
        changed = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json={'base_version': setup['current_version_id'], 'name': 'Helper', 'configuration': {'deployment_id': self.deployment.id, 'instructions': 'SAVED AGENT LATER EDIT', 'presented_tools': []}})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.post(f'/v1/chat/conversations/{chat["id"]}/queue/resume', {})
        finished = wait_for_chat(self.client, chat['id'])
        run = finished['current_run']
        self.assertEqual(run['status'], 'completed', run.get('error'))
        self.assertEqual(run['agent_setup_version_id'], setup['current_version_id'])
        prompt = run['effective_setup']['system_prompt']
        self.assertIn('SAVED AGENT ORIGINAL', prompt)
        self.assertNotIn('LATER EDIT', prompt)
