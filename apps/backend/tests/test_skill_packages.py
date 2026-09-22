"""Full inert skill packages and same-thread official knowledge refresh."""

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from langchain_core.messages import AIMessage

from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.agents.memory_skills import skill_slug_from_entry_id
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
        self.assertEqual({r['path'] for r in imported['resources']}, {'references/checklist.txt', 'scripts/optional.py'})
        resource = self.client.get(f'/v1/knowledge/versions/{imported["current_version_id"]}/resource', params={'path': 'references/checklist.txt'}).json()
        self.assertEqual(resource['content'], 'RESOURCE-ONE')
        self.assertFalse(resource['execution_available'])
        self.assertFalse((self.root / 'executed.txt').exists())
        archive = self.root / 'package.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.write(self.package / 'SKILL.md', 'example/SKILL.md')
            z.write(self.package / 'references' / 'checklist.txt', 'example/references/checklist.txt')
        imported_zip = self.import_package(archive)
        self.assertEqual(imported_zip['resources'][0]['sha256'], next(r['sha256'] for r in imported['resources'] if r['path'].endswith('checklist.txt')))

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

    def test_same_thread_refresh_reads_new_resource_and_removes_deselected_discovery(self):
        imported = self.import_package()
        slug = skill_slug_from_entry_id(imported['id'])
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
            self.assertIn(expected, str(finished['current_run']['model_requests'][-1]['messages']))
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
        self.assertNotIn(slug, finished['current_run']['model_requests'][-1]['instructions'])

    def test_next_turn_memory_refresh_changes_actual_instructions_without_resetting_history(self):
        reset_received_prompts()
        memory = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'memory', 'content': 'MEMORY-ORIGINAL-UNIQUE'}).json()
        deployment = self.client.post('/v1/deployments/connected', json={'endpoint': 'http://127.0.0.1:9/v1', 'display_name': 'fixture'}).json()
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content='done')]))
        chat = self.client.post('/v1/chat/conversations', json={'deployment_id': deployment['id'], 'memory_version_refs': [memory['current_version_id']]}).json()
        self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'First message', 'presented_tools': []})
        first = wait_for_chat(self.client, chat['id'])
        self.assertEqual(first['current_run']['status'], 'completed', first['current_run'].get('error'))
        self.assertIn('MEMORY-ORIGINAL-UNIQUE', RECEIVED_PROMPTS[-1])
        self.assertIn('pending proposal is not saved', RECEIVED_PROMPTS[-1])
        self.assertIn('Editing files under /memories changes derived scratch only', RECEIVED_PROMPTS[-1])
        self.assertNotIn('To persist new knowledge, call `edit_file`', RECEIVED_PROMPTS[-1])
        changed = self.client.post(f'/v1/knowledge/entries/{memory["id"]}/edit', json={'content': 'MEMORY-UPDATED-UNIQUE', 'base_version': memory['current_version_id']}).json()
        self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'Second message', 'presented_tools': [], 'memory_version_refs': [changed['current_version_id']]})
        second = wait_for_chat(self.client, chat['id'])
        self.assertEqual(second['current_run']['status'], 'completed', second['current_run'].get('error'))
        prompt = RECEIVED_PROMPTS[-1]
        self.assertIn('MEMORY-UPDATED-UNIQUE', prompt)
        self.assertNotIn('MEMORY-ORIGINAL-UNIQUE', prompt)
        self.assertEqual(first['thread_id'], second['thread_id'])
        self.assertGreater(len(second['transcript']), len(first['transcript']))
        self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={'task': 'Third message', 'presented_tools': [], 'memory_version_refs': []})
        third = wait_for_chat(self.client, chat['id'])
        self.assertEqual(third['current_run']['status'], 'completed', third['current_run'].get('error'))
        self.assertNotIn('MEMORY-UPDATED-UNIQUE', RECEIVED_PROMPTS[-1])
        self.assertEqual(third['thread_id'], first['thread_id'])
