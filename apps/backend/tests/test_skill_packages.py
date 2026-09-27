"""Native skill packages, same-thread skill reload and fixed chat memory."""

import stat
import base64
import tempfile
import unittest
import zipfile
from pathlib import Path

from langchain_core.messages import AIMessage

from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import harness_scratch_root
from tests.scripted_model import ScriptedChatModel, RECEIVED_PROMPTS, reset_received_prompts
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import wait_for_chat

MARKDOWN = '---\nname: example-skill\ndescription: Read the supplied reference before answering.\n---\nUse references/checklist.txt. Scripts are optional task data.\n'


class SkillPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root / 'data')
        self.client = offline_workbench_client(self.app)
        self.package = self.root / 'skill'
        (self.package / 'references').mkdir(parents=True)
        (self.package / 'scripts').mkdir()
        (self.package / 'SKILL.md').write_text(MARKDOWN)
        (self.package / 'references' / 'checklist.txt').write_text('RESOURCE-ONE')
        marker = self.root / 'executed.txt'
        (self.package / 'scripts' / 'optional.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("unsafe")')

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def import_package(self, source=None, **extra):
        response = self.client.post('/v1/knowledge/skills/import', json={'source_path': str(source or self.package), **extra})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_directory_and_archive_retain_resources_without_execution(self):
        imported = self.import_package()
        self.assertEqual(imported['display_name'], 'example-skill')
        self.assertIsNone(self.app.state.knowledge.store.get_entry(imported['id']).display_name)
        self.assertEqual({r['path'] for r in imported['resources']}, {'references/checklist.txt', 'scripts/optional.py'})
        resource = self.client.get(f'/v1/knowledge/versions/{imported["current_version_id"]}/resource', params={'path': 'references/checklist.txt'}).json()
        self.assertEqual(resource['content'], 'RESOURCE-ONE')
        self.assertFalse(resource['execution_available'])
        self.assertFalse((self.root / 'executed.txt').exists())
        archive = self.root / 'package.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.write(self.package / 'SKILL.md', 'example/SKILL.md')
            z.write(self.package / 'references' / 'checklist.txt', 'example/references/checklist.txt')
        imported_zip = self.import_package(archive, entry_id=imported['id'], base_version=imported['current_version_id'])
        self.assertEqual(imported_zip['display_name'], 'example-skill')
        self.assertEqual(imported_zip['resources'][0]['sha256'], next(r['sha256'] for r in imported['resources'] if r['path'].endswith('checklist.txt')))

    def test_skill_label_tracks_saved_name_unless_explicitly_renamed(self):
        created = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'skill', 'content': MARKDOWN})
        self.assertEqual(created.status_code, 200, created.text)
        skill = created.json()
        self.assertEqual(skill['display_name'], 'example-skill')
        self.assertIsNone(self.app.state.knowledge.store.get_entry(skill['id']).display_name)

        revised_source = MARKDOWN.replace('name: example-skill', 'name: native-review')
        revised = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/edit', json={
            'base_version': skill['current_version_id'], 'content': revised_source,
        })
        self.assertEqual(revised.status_code, 200, revised.text)
        revised = revised.json()
        self.assertEqual(revised['content'], revised_source)
        self.assertEqual(revised['display_name'], 'native-review')
        self.assertEqual(self.client.get(f'/v1/knowledge/entries/{skill["id"]}').json()['display_name'], 'native-review')
        self.assertEqual(next(item for item in self.client.get('/v1/knowledge/entries').json() if item['id'] == skill['id'])['display_name'], 'native-review')

        renamed = self.client.patch(f'/v1/knowledge/entries/{skill["id"]}', json={'display_name': 'My review skill'})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()['display_name'], 'My review skill')
        restored = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/revert', json={
            'target_version_id': skill['current_version_id'], 'base_version': revised['current_version_id'],
        })
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()['content'], MARKDOWN)
        self.assertEqual(restored.json()['display_name'], 'My review skill')

    def test_explicit_import_label_survives_source_name_change(self):
        imported = self.import_package(display_name='Publisher label')
        self.assertEqual(imported['display_name'], 'Publisher label')
        self.assertEqual(self.app.state.knowledge.store.get_entry(imported['id']).display_name, 'Publisher label')
        revised_source = MARKDOWN.replace('name: example-skill', 'name: imported-review')
        revised = self.client.post(f'/v1/knowledge/entries/{imported["id"]}/edit', json={
            'base_version': imported['current_version_id'], 'content': revised_source,
        })
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()['display_name'], 'Publisher label')
        self.assertEqual(revised.json()['content'], revised_source)

    def test_guided_preview_preserves_unknown_yaml_comments_and_multiline_fields(self):
        source = '---\n# publisher comment\nname: example-skill # keep this\ndescription: >-\n  Read several\n  references.\nlicense: MIT\nmetadata:\n  owner: publisher\n---\n\nOriginal instructions.\n'
        initial = self.client.post('/v1/knowledge/skills/preview', json={'content': source}).json()
        self.assertTrue(initial['guided_available'])
        self.assertTrue(initial['valid'])
        self.assertEqual(initial['content'], source)
        self.assertEqual(initial['description'], 'Read several references.')
        changed = self.client.post('/v1/knowledge/skills/preview', json={'content': source, 'fields': {'name': 'renamed-skill', 'description': 'New purpose', 'instructions': '\nRevised instructions.\n'}}).json()
        self.assertEqual(changed['issues'], [])
        self.assertIn('name: "renamed-skill" # keep this', changed['content'])
        self.assertIn('# publisher comment', changed['content'])
        self.assertIn('license: MIT\nmetadata:\n  owner: publisher', changed['content'])
        self.assertIn('description: "New purpose"\nlicense:', changed['content'])
        invalid = self.client.post('/v1/knowledge/skills/preview', json={'content': 'invalid source'}).json()
        self.assertFalse(invalid['guided_available'])
        self.assertFalse(invalid['valid'])
        self.assertEqual(invalid['content'], 'invalid source')
        self.assertTrue(invalid['issues'])
        duplicate_keys = source.replace('license: MIT', 'name: second-name\nlicense: MIT')
        advanced = self.client.post('/v1/knowledge/skills/preview', json={'content': duplicate_keys}).json()
        self.assertFalse(advanced['guided_available'])
        self.assertTrue(advanced['valid'], 'valid native Source remains savable when guided fields cannot represent it')

    def test_resource_changes_are_one_version_and_old_resources_remain_immutable(self):
        skill = self.import_package()
        encode = lambda text: base64.b64encode(text.encode()).decode()
        changed = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/edit', json={'base_version': skill['current_version_id'], 'content': MARKDOWN, 'resource_changes': [{'path': 'references/checklist.txt', 'content_base64': encode('NEW')}, {'path': 'scripts/optional.py', 'remove': True}, {'path': 'references/new.txt', 'content_base64': encode('ADDED')} ]})
        self.assertEqual(changed.status_code, 200, changed.text)
        new = changed.json()
        self.assertEqual(len(self.client.get(f'/v1/knowledge/entries/{skill["id"]}/versions').json()), 2)
        self.assertEqual({r['path'] for r in new['resources']}, {'references/checklist.txt', 'references/new.txt'})
        original = self.client.get(f'/v1/knowledge/versions/{skill["current_version_id"]}/resource', params={'path': 'references/checklist.txt'}).json()
        self.assertEqual(original['content'], 'RESOURCE-ONE')
        self.assertFalse((self.root / 'executed.txt').exists())
        for changes in [[{'path': '../escape', 'content_base64': encode('X')}], [{'path': 'SKILL.md', 'content_base64': encode('X')}], [{'path': 'SKILL.md/child.txt', 'content_base64': encode('X')}], [{'path': 'skill.MD/child.txt', 'content_base64': encode('X')}], [{'path': 'references/NEW.txt', 'content_base64': encode('X')}], [{'path': 'references/new.txt/child', 'content_base64': encode('X')}], [{'path': 'broken', 'content_base64': '?'}]]:
            rejected = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/edit', json={'base_version': new['current_version_id'], 'content': MARKDOWN, 'resource_changes': changes})
            self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(len(self.client.get(f'/v1/knowledge/entries/{skill["id"]}/versions').json()), 2)

    def test_same_scope_slug_uniqueness_and_latest_record_resolution(self):
        skill = self.import_package()
        duplicate = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'skill', 'content': MARKDOWN})
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        new = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/edit', json={'base_version': skill['current_version_id'], 'content': MARKDOWN + 'Saved edit.\n'}).json()
        refs = self.app.state.knowledge.resolve_entry_refs(skill_entry_ids=[skill['id']])
        self.assertEqual(refs.skill_version_refs, [new['current_version_id']])
        self.client.patch(f'/v1/knowledge/entries/{skill["id"]}', json={'enabled': False})
        from workbench_backend.errors import KnowledgeError
        with self.assertRaises(KnowledgeError):
            self.app.state.knowledge.resolve_entry_refs(skill_entry_ids=[skill['id']])
        frozen = self.app.state.knowledge.resolve_refs(skill_version_refs=[skill['current_version_id']], frozen=True)
        self.assertEqual(frozen.skill_version_refs, [skill['current_version_id']])

    def test_unsafe_archives_and_missing_frontmatter_are_rejected_before_retention(self):
        for index, names in enumerate([['../escape.txt'], ['/absolute.txt'], ['C:/escape.txt'], ['references/a.txt', 'references/A.txt'], ['references/a.txt.'], ['NUL.txt'], ['references', 'references/a.txt']]):
            with self.subTest(names=names):
                archive = self.root / f'bad-{index}.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('SKILL.md', MARKDOWN)
                    for name in names:
                        z.writestr(name, 'bad')
                response = self.client.post('/v1/knowledge/skills/import', json={'source_path': str(archive)})
                self.assertEqual(response.status_code, 400, response.text)
        archive = self.root / 'link.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('SKILL.md', MARKDOWN)
            link = zipfile.ZipInfo('references/link')
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, '../../outside')
        self.assertEqual(self.client.post('/v1/knowledge/skills/import', json={'source_path': str(archive)}).status_code, 400)
        (self.package / 'SKILL.md').write_text('missing frontmatter')
        self.assertEqual(self.client.post('/v1/knowledge/skills/import', json={'source_path': str(self.package)}).status_code, 400)
        self.assertEqual(self.app.state.knowledge.list_entries(), [])

    def test_editor_requires_native_skill_and_keeps_content_verbatim(self):
        for content in ('Use a checklist.', '---\nname: Bad Name\ndescription: Check the work.\n---\nBody', '---\nname: valid-name\ndescription: Check the work.\n---\n'):
            response = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'skill', 'content': content})
            self.assertEqual(response.status_code, 400, response.text)
        created = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'skill', 'content': MARKDOWN})
        self.assertEqual(created.status_code, 200, created.text)
        skill = created.json()
        self.assertEqual(skill['content'], MARKDOWN)
        invalid = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/edit', json={'base_version': skill['current_version_id'], 'content': 'freeform replacement'})
        self.assertEqual(invalid.status_code, 400, invalid.text)
        self.assertEqual(self.client.get(f'/v1/knowledge/entries/{skill["id"]}').json()['current_version_id'], skill['current_version_id'])
        changed_markdown = MARKDOWN.replace('example-skill', 'renamed-skill').replace('Scripts are optional task data.', 'Resources remain optional.')
        changed = self.client.post(f'/v1/knowledge/entries/{skill["id"]}/edit', json={'base_version': skill['current_version_id'], 'content': changed_markdown})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()['content'], changed_markdown)

    def test_single_file_import_requires_skill_markdown_filename(self):
        arbitrary = self.root / 'instructions.md'
        arbitrary.write_text(MARKDOWN, encoding='utf-8')
        refused = self.client.post('/v1/knowledge/skills/import', json={'source_path': str(arbitrary)})
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()['code'], 'skill_package_missing')
        imported = self.import_package(self.package / 'SKILL.md')
        self.assertEqual(imported['content'], (self.package / 'SKILL.md').read_bytes().decode('utf-8'))

    def test_update_and_revert_preserve_each_resource_version_and_detect_corruption(self):
        original = self.import_package()
        (self.package / 'references' / 'checklist.txt').write_text('RESOURCE-TWO')
        changed = self.import_package(entry_id=original['id'], base_version=original['current_version_id'])
        self.assertNotEqual(original['current_version_id'], changed['current_version_id'])
        old = self.client.get(f'/v1/knowledge/versions/{original["current_version_id"]}/resource', params={'path': 'references/checklist.txt'}).json()
        self.assertEqual(old['content'], 'RESOURCE-ONE')
        reverted = self.client.post(f'/v1/knowledge/entries/{original["id"]}/revert', json={'base_version': changed['current_version_id'], 'target_version_id': original['current_version_id']}).json()
        self.assertEqual(reverted['resources'], original['resources'])
        digest = next(r['sha256'] for r in original['resources'] if r['path'].endswith('checklist.txt'))
        (self.app.state.manager.paths.knowledge / 'resources' / digest).write_text('damaged')
        failed = self.client.get(f'/v1/knowledge/versions/{reverted["current_version_id"]}/resource', params={'path': 'references/checklist.txt'})
        self.assertEqual(failed.status_code, 409, failed.text)

    def test_same_thread_skill_reload_reads_new_resource_and_removes_deselected_discovery(self):
        imported = self.import_package()
        slug = 'example-skill'
        virtual = f'/skills/{slug}/references/checklist.txt'
        deployment = self.client.post('/v1/deployments/connected', json={'endpoint': 'http://127.0.0.1:9/v1', 'display_name': 'fixture'}).json()
        def model(run, _):
            if run.skill_version_refs:
                return ScriptedChatModel([AIMessage(content='', tool_calls=[{'id': 'read-resource', 'name': 'read_file', 'args': {'file_path': virtual}}]), AIMessage(content='read complete')])
            return ScriptedChatModel([AIMessage(content='no skill selected')])
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge, model_factory=model)
        chat = self.client.post('/v1/chat/conversations', json={'deployment_id': deployment['id'], 'skill_version_refs': [imported['current_version_id']]}).json()
        for expected, version in [('RESOURCE-ONE', imported['current_version_id']), ('RESOURCE-TWO', None)]:
            if version is None:
                (self.package / 'references' / 'checklist.txt').write_text(expected)
                changed = self.import_package(entry_id=imported['id'], base_version=imported['current_version_id'])
                version = changed['current_version_id']
            start = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'Read the skill resource', 'skill_version_refs': [version], 'presented_tools': ['read_file']})
            self.assertEqual(start.status_code, 200, start.text)
            finished = wait_for_chat(self.client, chat['id'])
            self.assertEqual(finished['current_run']['status'], 'completed', finished['current_run'].get('error'))
            self.assertNotIn('model_requests', finished['current_run'])
            diagnostic = self.client.get(f'/v1/agent-runs/{finished["current_run_id"]}', params={'view': 'diagnostic'})
            self.assertEqual(diagnostic.status_code, 200, diagnostic.text)
            self.assertIn(expected, str(diagnostic.json()['model_requests'][-1]['messages']))
            self.assertEqual(finished['thread_id'], chat['thread_id'])
        scratch = harness_scratch_root(self.app.state.manager.paths, chat['thread_id'])
        (scratch / 'conversation_history' / 'keep.txt').write_text('framework history')
        (scratch / 'large_tool_results' / 'keep.txt').write_text('framework offload')
        cleared = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'Continue without skills', 'skill_version_refs': [], 'presented_tools': []})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        finished = wait_for_chat(self.client, chat['id'])
        self.assertEqual(finished['current_run']['status'], 'completed', finished['current_run'].get('error'))
        self.assertEqual(finished['thread_id'], chat['thread_id'])
        self.assertFalse((scratch / 'skills' / slug).exists())
        self.assertTrue((scratch / 'conversation_history' / 'keep.txt').is_file())
        self.assertTrue((scratch / 'large_tool_results' / 'keep.txt').is_file())
        self.assertNotIn('model_requests', finished['current_run'])
        diagnostic = self.client.get(f'/v1/agent-runs/{finished["current_run_id"]}', params={'view': 'diagnostic'})
        self.assertEqual(diagnostic.status_code, 200, diagnostic.text)
        self.assertNotIn(slug, diagnostic.json()['model_requests'][-1]['instructions'])

    def test_memory_version_changes_explicitly_on_next_turn_and_can_be_deselected(self):
        reset_received_prompts()
        actual_inputs = []

        class MemoryModel(ScriptedChatModel):
            def _generate(self, messages, *args, **kwargs):
                actual_inputs.append(messages[-1].content)
                return super()._generate(messages, *args, **kwargs)

        memory = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'memory', 'content': 'MEMORY-ORIGINAL-UNIQUE'}).json()
        deployment = self.client.post('/v1/deployments/connected', json={'endpoint': 'http://127.0.0.1:9/v1', 'display_name': 'fixture'}).json()
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: MemoryModel([AIMessage(content='done')]))
        chat = self.client.post('/v1/chat/conversations', json={'deployment_id': deployment['id'], 'memory_version_refs': [memory['current_version_id']]}).json()
        self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'First message', 'presented_tools': []})
        first = wait_for_chat(self.client, chat['id'])
        self.assertEqual(first['current_run']['status'], 'completed', first['current_run'].get('error'))
        self.assertIn('MEMORY-ORIGINAL-UNIQUE', RECEIVED_PROMPTS[-1])
        self.assertIn('pending proposal is not saved', RECEIVED_PROMPTS[-1])
        self.assertIn('Editing files under /memories changes derived scratch only', RECEIVED_PROMPTS[-1])
        self.assertNotIn('To persist new knowledge, call `edit_file`', RECEIVED_PROMPTS[-1])
        changed = self.client.post(f'/v1/knowledge/entries/{memory["id"]}/edit', json={'content': 'MEMORY-UPDATED-UNIQUE', 'base_version': memory['current_version_id']}).json()
        attempted = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'Change memory here', 'presented_tools': [], 'memory_version_refs': [changed['current_version_id']]})
        self.assertEqual(attempted.status_code, 200, attempted.text)
        second = wait_for_chat(self.client, chat['id'])
        self.assertEqual(second['current_run']['status'], 'completed', second['current_run'].get('error'))
        prompt = RECEIVED_PROMPTS[-1]
        self.assertNotIn('MEMORY-ORIGINAL-UNIQUE', prompt)
        self.assertIn('MEMORY-UPDATED-UNIQUE', prompt)
        current_input = actual_inputs[-1]
        self.assertEqual(str(current_input).count('Current turn memory selection:'), 1)
        self.assertIn(changed['current_version_id'], str(current_input))
        self.assertNotIn(memory['current_version_id'], str(current_input))
        self.assertNotIn('MEMORY-UPDATED-UNIQUE', str(current_input))
        self.assertEqual(first['thread_id'], second['thread_id'])
        self.assertGreater(len(second['transcript']), len(first['transcript']))
        self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'No memory now', 'presented_tools': [], 'memory_version_refs': []})
        third = wait_for_chat(self.client, chat['id'])
        self.assertEqual(third['current_run']['status'], 'completed', third['current_run'].get('error'))
        self.assertNotIn('MEMORY-UPDATED-UNIQUE', RECEIVED_PROMPTS[-1])
        self.assertNotIn('MEMORY-ORIGINAL-UNIQUE', RECEIVED_PROMPTS[-1])
        self.assertIn('Current turn memory selection: none.', str(actual_inputs[-1]))
        self.assertIsNone(third['current_run']['content_blocks'])
        self.assertEqual(third['thread_id'], first['thread_id'])
