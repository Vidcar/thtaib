"""Real immutable source fixtures; fake embeddings only where labelled."""
from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deepagents.backends.protocol import FileUploadResponse
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from workbench_backend.agents.memory_skills import memory_contents_for_turn, memory_version_costs, plan_knowledge_materialization
from workbench_backend.agents.project_outline import ProjectOutlineCache
from workbench_backend.agents.retrieval import documents_from_knowledge, documents_from_project_paths, documents_from_retained_assets, make_document_search_tool
from workbench_backend.assets.schemas import RetainedUploadRequest, RetainedAssetReuseRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.assets.tools import attachment_tool_for_run
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.inference.ids import utc_now
from workbench_backend.knowledge.schemas import KnowledgeVersion
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore
from tests.support import close_workbench_sqlite
from tests import test_chat as chat_test_support
from tests import test_agent_capabilities as helper_fixture
from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from langchain_core.messages import AIMessage


class Backend:
    def __init__(self):
        self.files = {}

    def upload_files(self, uploads):
        self.files.update(uploads)
        return [FileUploadResponse(path=path, error=None) for path, _ in uploads]


class DocumentContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ApplicationStore(WorkbenchPaths(self.root / "data"))
        self.store.put_conversation(ChatConversation(id="chat_docs", thread_id="thread_docs", deployment_id="dep", created_at=utc_now(), updated_at=utc_now()))
        self.assets = RetainedAssetService(self.store)
        self.backend = Backend()

    def tearDown(self):
        close_workbench_sqlite(self.store)
        self.tmp.cleanup()

    def upload(self, text, filename="notes.md"):
        return self.assets.retain_upload(RetainedUploadRequest(session_id="chat_docs", filename=filename,
            content_type="text/markdown", content_base64=base64.b64encode(text.encode()).decode()))

    def tool(self, ids):
        return make_document_search_tool(lambda: documents_from_retained_assets(self.store, ids,
            session_id="chat_docs", project_path=None), self.backend)

    def test_cross_document_lexical_pages_keep_source_identity(self):
        first = self.upload("\n".join(f"orchid item {i}" for i in range(25)))
        second = self.upload("orchid final receipt", "second.md")
        tool = self.tool([first.id, second.id])
        cursor, seen = None, []
        while True:
            result = tool.invoke({"query": "orchid", "limit": 4, "cursor": cursor})
            self.assertEqual(result["search_mode"], "lexical")
            self.assertEqual(result["total_matches"], 26)
            for item in result["results"]:
                self.assertIn(item["sha256"], item["source_url"])
                self.assertIn("source=file+text", item["source_url"])
                self.assertIn(item["source"], self.backend.files[item["path"]].decode())
                seen.append((item["asset_id"], item["extracted_line"]))
            cursor = result["next_cursor"]
            if cursor is None:
                self.assertFalse(result["has_more"])
                break
        self.assertEqual(len(set(seen)), 26)
        self.assertEqual(seen[-1], (second.id, 1))

    def test_source_access_is_rechecked_and_invalid_cursor_correctable(self):
        asset = self.upload("orchid one\norchid two")
        tool = self.tool([asset.id])
        page = tool.invoke({"query": "orchid", "limit": 1})
        self.assertIn("no longer matches", tool.invoke({"query": "other", "cursor": page["next_cursor"]}))
        self.assertIn("no longer matches", tool.invoke({"query": "orchid", "cursor": "garbage"}))
        denied = make_document_search_tool(lambda: documents_from_retained_assets(self.store, [asset.id],
            session_id="other-chat", project_path=None), self.backend)
        self.assertIsInstance(denied.invoke({"query": "orchid"}), str)

    def test_full_selection_uses_one_catalogue_block_without_reinjecting_text(self):
        ids = [self.upload(f"PRIVATE-DOCUMENT-TEXT-{index}", f"document-{index}.md").id for index in range(32)]
        blocks = self.assets.document_catalogue(RetainedAssetReuseRequest(asset_ids=ids, session_id="chat_docs"))
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("PRIVATE-DOCUMENT-TEXT", blocks[0].text)
        self.assertIn(ids[-1], blocks[0].text)

    def test_lazy_similarity_builds_once_and_rebuilds_after_change(self):
        path = self.root / "notes.md"
        path.write_text("orchid first", encoding="utf-8")
        builds = []
        def embedder():
            builds.append(True)
            return DeterministicFakeEmbedding(size=16)
        tool = make_document_search_tool(lambda: documents_from_project_paths(str(self.root), ["notes.md"]), self.backend, embedder)
        self.assertEqual(builds, [])
        result = tool.invoke({"query": "orchid"})
        self.assertEqual(result["search_mode"], "similarity")
        self.assertIsNone(result["total_matches"])
        tool.invoke({"query": "orchid"})
        self.assertEqual(len(builds), 1)
        path.write_text("orchid second edition", encoding="utf-8")
        tool.invoke({"query": "orchid"})
        self.assertEqual(len(builds), 2)
        self.assertIn("second edition", list(self.backend.files.values())[-1].decode())

    def test_selected_embedder_failure_does_not_claim_lexical_results(self):
        def failed():
            raise OSError("offline fixture")
        tool = make_document_search_tool(lambda: [Document(page_content="orchid")], self.backend, failed)
        result = tool.invoke({"query": "orchid"})
        self.assertIn("selected similarity model", result)
        self.assertEqual(self.backend.files, {})

    def test_attachment_search_pages_beyond_twenty_matches_and_long_lines(self):
        asset = self.upload("\n".join(f"orchid {i}" for i in range(42)))
        tool = attachment_tool_for_run(self.store, SimpleNamespace(retained_asset_ids=[asset.id], thread_id="thread_docs", project_path=None))
        first = tool.invoke({"asset_id": asset.id, "query": "orchid", "line_count": 20})
        self.assertEqual(first["total_matches"], 42)
        self.assertTrue(first["has_more"])
        second = tool.invoke(first["next_read"])
        self.assertEqual(second["excerpts"][0]["document_line"], 21)
        self.assertTrue(second["has_more"])
        third = tool.invoke(second["next_read"])
        self.assertEqual(third["excerpts"][0]["document_line"], 41)
        self.assertFalse(third["has_more"])
        long = self.upload("orchid " + "a" * 24000)
        tool = attachment_tool_for_run(self.store, SimpleNamespace(retained_asset_ids=[long.id], thread_id="thread_docs", project_path=None))
        part = tool.invoke({"asset_id": long.id})
        self.assertLess(part["next_read"]["start_char"], 12000)
        self.assertLessEqual(len(json.dumps(part)), 12000)
        next_part = tool.invoke(part["next_read"])
        self.assertEqual(next_part["excerpts"][0]["start_char"], part["next_read"]["start_char"])

    def test_complete_read_budget_counts_metadata_escaping_and_preserves_exact_citations(self):
        from urllib.parse import urlsplit, parse_qs
        from workbench_backend.assets.sources import SourceRangeRequest, read_source
        source_text = 'orchid ' + '\u2603"\\' * 6000
        asset = self.upload(source_text, "long-" + "a" * 230 + ".md")
        tool = attachment_tool_for_run(self.store, SimpleNamespace(retained_asset_ids=[asset.id], thread_id="thread_docs", project_path=None))
        request, recovered = {"asset_id": asset.id}, []
        while request:
            output = tool.invoke(request)
            self.assertLessEqual(len(json.dumps(output, ensure_ascii=True)), 12000)
            self.assertEqual(output["sha256"], asset.sha256)
            for excerpt in output["excerpts"]:
                link = urlsplit(excerpt["source_url"])
                query = parse_qs(link.query)
                viewed = read_source(self.assets, link.netloc, SourceRangeRequest(
                    sha256=link.path.lstrip('/'), source=query['source'][0], extracted_line=int(query['line'][0]),
                    start_char=int(query['start'][0]), end_char=int(query['end'][0]), session_id="chat_docs"))
                self.assertEqual(viewed.text, excerpt["text"])
                recovered.append(excerpt["text"])
            request = output["next_read"]
        self.assertEqual(''.join(recovered), source_text)

    def test_memory_is_native_full_version_map_and_never_embedding_corpus(self):
        def version(version_id, kind, content):
            return KnowledgeVersion(id=version_id, entry_id="entry", scope="user", kind=kind, content=content,
                provenance={"actor": "human"}, created_at=utc_now())
        original = version("v1", "memory", "Full original memory")
        updated = version("v2", "memory", "Full updated memory")
        frozen = plan_knowledge_materialization([original])
        self.assertEqual(list(memory_contents_for_turn(frozen).values()), [original.content])
        self.assertEqual(list(memory_contents_for_turn(plan_knowledge_materialization([updated])).values()), [updated.content])
        self.assertEqual(memory_contents_for_turn(plan_knowledge_materialization([])), {})
        self.assertEqual(list(memory_contents_for_turn(frozen).values()), [original.content])
        self.assertEqual(documents_from_knowledge([original, version("v3", "skill", "skill"), version("v4", "protected_instruction", "instruction")]), [])
        costs = memory_version_costs([original])
        self.assertEqual(costs[0]["estimated_content_tokens"], (len(original.content) + 2) // 3)
        self.assertIn("not tokenizer", costs[0]["token_counting_method"])


class ChatDocumentPersistenceTests(unittest.TestCase):
    setUp = chat_test_support.ChatHarnessTests.setUp
    tearDown = chat_test_support.ChatHarnessTests.tearDown
    _create = chat_test_support.ChatHarnessTests._create

    def test_saved_setup_allows_lexical_document_search_in_plan_and_respects_tools_off(self):
        created = self.client.post('/v1/chat/conversations', json={
            "deployment_id": self.deployment_id, "project_path": str(self.project),
            "work_mode": "plan", "presented_tools": ["search_knowledge"],
            "approval_mode": "full_access", "per_request_overrides": {"max_tokens": 512}})
        self.assertEqual(created.status_code, 200, created.text)
        chat = created.json()
        asset = RetainedAssetService(self.app.state.app_store).retain_upload(RetainedUploadRequest(
            session_id=chat["id"], filename="receipt.md", content_type="text/markdown",
            content_base64=base64.b64encode(b"ORCHID delivery receipt").decode()))
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "search_knowledge", "args": {"query": "ORCHID"}, "id": "search_docs"}]),
            AIMessage(content="Found the selected receipt.")])
        started = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={
            "task": "Find the receipt", "attachment_ids": [asset.id]})
        self.assertEqual(started.status_code, 200, started.text)
        finished = chat_test_support.wait_for_chat(self.client, chat["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertTrue(run["effective_setup"]["retrieval_presented"])
        self.assertNotIn("ORCHID delivery receipt", str(run["content_blocks"]))
        self.assertIsNone(run["effective_setup"]["loaded_embedding_deployment_id"])
        self.assertNotIn("model_requests", run)
        diagnostic = self.client.get(f'/v1/agent-runs/{finished["current_run_id"]}', params={"view": "diagnostic"})
        self.assertEqual(diagnostic.status_code, 200, diagnostic.text)
        self.assertIn('lexical', str(diagnostic.json()["model_requests"][-1]["messages"]))
        self.scripted = ScriptedChatModel([AIMessage(content="No documents selected now.")])
        removed = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={
            "task": "Continue after removing every document", "document_asset_ids": []})
        self.assertEqual(removed.status_code, 200, removed.text)
        idle = chat_test_support.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(idle["retained_asset_ids"], [])
        self.assertNotIn("search_knowledge", idle["presented_tools"])
        self.assertFalse(idle["effective_setup"]["retrieval_presented"])
        self.scripted = ScriptedChatModel([AIMessage(content="Tools are off.")])
        disabled = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={
            "task": "Continue without tools", "presented_tools": []})
        self.assertEqual(disabled.status_code, 200, disabled.text)
        off = chat_test_support.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(off["presented_tools"], [])
        self.assertFalse(off["effective_setup"]["retrieval_presented"])

    def test_follow_up_reads_selected_document_and_removal_affects_future_turn(self):
        chat = self._create()
        service = RetainedAssetService(self.app.state.app_store)
        asset = service.retain_upload(RetainedUploadRequest(session_id=chat["id"], filename="receipt.md",
            content_type="text/markdown", content_base64=base64.b64encode(b"ORCHID-PRIVATE-RECEIPT").decode()))
        self.scripted = ScriptedChatModel([AIMessage(content="Document selected.")])
        first = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={
            "task": "Keep this receipt", "attachment_ids": [asset.id], "presented_tools": ["read_attachment"]})
        self.assertEqual(first.status_code, 200, first.text)
        finished = chat_test_support.wait_for_chat(self.client, chat["id"])
        self.assertEqual(finished["document_asset_ids"], [asset.id])
        self.assertNotIn("ORCHID-PRIVATE-RECEIPT", str(finished["current_run"]["content_blocks"]))
        self.assertIn(asset.id, str(finished["current_run"]["content_blocks"]))
        self.scripted = ScriptedChatModel([AIMessage(content="", tool_calls=[{"id": "read_receipt", "name": "read_attachment", "args": {"asset_id": asset.id}}]), AIMessage(content="Read receipt.")])
        follow = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={"task": "What does the receipt say?", "presented_tools": ["read_attachment"]})
        self.assertEqual(follow.status_code, 200, follow.text)
        read = chat_test_support.wait_for_chat(self.client, chat["id"])
        self.assertEqual(read["current_run"]["retained_asset_ids"], [asset.id])
        self.assertEqual(read["current_run"]["status"], "completed", read["current_run"].get("error"))
        self.assertNotIn("model_requests", read["current_run"])
        diagnostic = self.client.get(f'/v1/agent-runs/{read["current_run_id"]}', params={"view": "diagnostic"})
        self.assertEqual(diagnostic.status_code, 200, diagnostic.text)
        self.assertIn("ORCHID-PRIVATE-RECEIPT", str(diagnostic.json()["model_requests"][-1]["messages"]))
        self.scripted = ScriptedChatModel([AIMessage(content="Selection removed.")])
        removed = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={"task": "Continue without documents", "document_asset_ids": [], "presented_tools": []})
        self.assertEqual(removed.status_code, 200, removed.text)
        cleared = chat_test_support.wait_for_chat(self.client, chat["id"])
        self.assertEqual(cleared["document_asset_ids"], [])
        self.assertEqual(cleared["current_run"]["retained_asset_ids"], [])
        previous = self.app.state.harness.get_run(read["current_run"]["id"])
        self.assertEqual(previous.retained_asset_ids, [asset.id])
        branched = self.client.post(f'/v1/chat/conversations/{chat["id"]}/branches', json={"source_run_id": previous.id, "mode": "continue"})
        self.assertEqual(branched.status_code, 200, branched.text)
        branch = branched.json()
        self.assertEqual(branch["document_asset_ids"], [asset.id])
        inherited, _ = service._load_content(asset.id, session_id=branch["id"], project_path=branch["project_path"])
        self.assertEqual(inherited.sha256, asset.sha256)

    def test_queued_documents_and_memory_keep_submitted_selection(self):
        memory = self.client.post('/v1/knowledge/entries', json={"scope": "user", "kind": "memory", "content": "Version one"}).json()
        original = memory["current_version_id"]
        chat = self._create(memory_version_refs=[original])
        asset = RetainedAssetService(self.app.state.app_store).retain_upload(RetainedUploadRequest(session_id=chat["id"], filename="frozen.md", content_type="text/markdown", content_base64=base64.b64encode(b"Frozen receipt").decode()))
        hold = threading.Event()
        set_generate_hold(hold)
        self.scripted = ScriptedChatModel([AIMessage(content="Finished active work")])
        try:
            active = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={"task": "Active turn", "attachment_ids": [asset.id], "presented_tools": ["read_attachment"]})
            self.assertEqual(active.status_code, 200, active.text)
            wait_for_generate_hold()
            first = self.client.post(f'/v1/chat/conversations/{chat["id"]}/queue', json={"task": "Use original selection", "memory_version_refs": [original], "document_asset_ids": [asset.id], "presented_tools": ["read_attachment"]})
            self.assertEqual(first.status_code, 200, first.text)
            changed = self.client.post(f'/v1/knowledge/entries/{memory["id"]}/edit', json={"base_version": original, "content": "Version two"}).json()["current_version_id"]
            second = self.client.post(f'/v1/chat/conversations/{chat["id"]}/queue', json={"task": "Use changed selection", "memory_version_refs": [changed], "document_asset_ids": [], "presented_tools": []})
            self.assertEqual(second.status_code, 200, second.text)
            view = second.json()
            self.assertEqual(view["document_asset_ids"], [])
            self.assertEqual(view["queue"][0]["attachment_ids"], [asset.id])
            self.assertEqual(view["queue"][0]["intended_config"]["memory_version_refs"], [original])
            self.assertEqual(view["queue"][1]["attachment_ids"], [])
            self.assertEqual(view["queue"][1]["intended_config"]["memory_version_refs"], [changed])
            self.assertEqual(view["current_run"]["memory_version_refs"], [original])
            self.assertEqual(view["current_run"]["retained_asset_ids"], [asset.id])
        finally:
            # Remove still-waiting work before releasing the active fake worker.
            latest = self.client.get(f'/v1/chat/conversations/{chat["id"]}').json()
            for item in latest.get("queue", []):
                self.client.delete(f'/v1/chat/conversations/{chat["id"]}/queue/{item["id"]}')
            hold.set()
            set_generate_hold(None)
            chat_test_support.wait_for_chat(self.client, chat["id"])


class HelperMemorySelectionTests(unittest.TestCase):
    setUp = helper_fixture.AgentCapabilitiesTests.setUp
    tearDown = helper_fixture.AgentCapabilitiesTests.tearDown
    post = helper_fixture.AgentCapabilitiesTests.post
    setup = helper_fixture.AgentCapabilitiesTests.setup
    harness = helper_fixture.AgentCapabilitiesTests.harness
    start = helper_fixture.AgentCapabilitiesTests.start

    def test_paused_run_reads_original_version_after_durable_memory_edit(self):
        from tests.support import wait_for_run
        from tests import test_host_shell as approval_fixture
        from workbench_backend.agents.memory_skills import memory_file_path

        memory = self.post('/v1/knowledge/entries', {
            "scope": "user", "kind": "memory", "content": "PAUSED-ORIGINAL-MEMORY"})
        version = memory['current_version_id']
        original_path = memory_file_path('user', memory['id'], version)
        actual_inputs = []

        class MemoryModel(ScriptedChatModel):
            def _generate(self, messages, *args, **kwargs):
                actual_inputs.append(str(messages))
                return super()._generate(messages, *args, **kwargs)

        script = MemoryModel([
            helper_fixture.call('ask_user', {'prompt': 'Continue?', 'answer_type': 'text'}, 'ask'),
            helper_fixture.call('read_file', {'file_path': original_path}, 'memory-read'),
            AIMessage(content='Finished'),
        ])
        self.harness(lambda *_: script)
        started = self.start(presented_tools=['ask_user', 'read_file'], memory_version_refs=[version])
        paused = approval_fixture.wait_for_interrupt(self.client, started['id'])
        changed = self.post(f'/v1/knowledge/entries/{memory["id"]}/edit', {
            "base_version": version, "content": "LATER-MEMORY-VERSION"})
        pending = paused['pending_interrupt']
        self.post(f'/v1/agent-runs/{started["id"]}/interrupt-decision', {
            'interrupt_id': pending['interrupt_id'], 'namespace': pending.get('namespace', []),
            'decisions': [{'type': 'respond', 'message': 'Continue'}]})
        finished = wait_for_run(self.client, started['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        self.assertEqual(finished['memory_version_refs'], [version])
        contents = str(finished['model_requests'][-1]['messages'])
        self.assertIn('PAUSED-ORIGINAL-MEMORY', contents)
        self.assertIn(original_path, contents)
        self.assertNotIn('LATER-MEMORY-VERSION', contents)
        self.assertNotIn(changed['current_version_id'], contents)
        self.assertEqual(actual_inputs[-1].count('Current turn memory selection:'), 1)
        self.assertNotIn('Current turn memory selection:', contents)
        self.assertIsNone(finished['content_blocks'])

    def test_helper_current_turn_notice_uses_its_own_frozen_selection(self):
        from tests.support import wait_for_run

        parent_memory = self.post('/v1/knowledge/entries', {
            "scope": "user", "kind": "memory", "content": "PARENT-MEMORY-CONTENT"})
        helper_memory = self.post('/v1/knowledge/entries', {
            "scope": "user", "kind": "memory", "content": "HELPER-MEMORY-CONTENT"})
        helper = self.setup(presented_tools=[], memory_version_refs=[helper_memory['current_version_id']])
        parent_model = ScriptedChatModel([
            helper_fixture.call('task', {'subagent_type': helper['id'], 'description': 'Report from your selected memory'}, 'delegate'),
            AIMessage(content='Finished'),
        ])
        child_prompts = []
        child_inputs = []

        class HelperModel(ScriptedChatModel):
            def _generate(self, messages, *args, **kwargs):
                child_prompts.append(messages[0].content)
                child_inputs.append(messages[-1].content)
                return super()._generate(messages, *args, **kwargs)

        self.harness(lambda run, _sink: HelperModel([AIMessage(content='Helper finished')])
            if run.parent_run_id else parent_model)
        finished = wait_for_run(self.client, self.start(
            presented_tools=['echo'], helper_agent_ids=[helper['id']],
            memory_version_refs=[parent_memory['current_version_id']])['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        child = self.app.state.harness.get_run(finished['child_runs'][0]['run_id'])
        current_input = str(child_inputs[-1])
        self.assertEqual(current_input.count('Current turn memory selection:'), 1)
        self.assertIn(helper_memory['current_version_id'], current_input)
        self.assertNotIn(parent_memory['current_version_id'], current_input)
        self.assertNotIn('HELPER-MEMORY-CONTENT', current_input)
        self.assertIn('HELPER-MEMORY-CONTENT', str(child_prompts[0]))
        self.assertNotIn('PARENT-MEMORY-CONTENT', str(child_prompts[0]))
        self.assertIsNone(child.content_blocks)
        self.assertNotIn('Current turn memory selection:', str(child.model_requests[-1].messages))


class ProjectOutlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = ProjectOutlineCache()
        # Test bootstrap places fixtures under this repository's ignored .scratch.
        self.git = patch("workbench_backend.agents.project_outline.subprocess.run", return_value=SimpleNamespace(returncode=1, stdout=b""))
        self.git.start()

    def tearDown(self):
        self.git.stop()
        self.tmp.cleanup()

    def build(self, **kwargs):
        return self.cache.build(str(self.root), "main", ["read_file"], **kwargs)

    def test_authority_exclusions_and_changed_content(self):
        (self.root / "main.py").write_text("def original():\n    pass\n")
        (self.root / ".env").write_text("SECRET_VALUE")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "ignored.py").write_text("def dependency(): pass")
        self.assertEqual(self.cache.build(str(self.root), presented_tools=[]).text, "")
        self.assertEqual(self.cache.build(str(self.root), presented_tools=["ls"]).text, "")
        first = self.build()
        self.assertIn("original", first.text)
        self.assertNotIn(".env", first.text)
        self.assertNotIn("ignored", first.text)
        (self.root / "main.py").write_text("def revised():\n    pass\n")
        self.assertIn("revised", self.build().text)
        self.assertNotIn("original", self.build().text)
        self.cache.invalidate(self.root)
        self.assertEqual(len(self.cache._entries), 0)
        self.assertEqual(self.build(excluded_paths=["main.py"]).text, "")

    def test_cap_and_context_pressure(self):
        for i in range(80):
            (self.root / f"module_{i}.ts").write_text("\n".join(f"export function symbol_{j}() {{}}" for j in range(20)))
        result = self.build()
        self.assertLessEqual(result.estimated_tokens, 1024)
        self.assertTrue(result.partial)
        self.assertLessEqual(result.included_files, 32)
        self.assertEqual(self.build(max_tokens=1).text, "")
        self.assertLessEqual(self.build(max_tokens=100).estimated_tokens, 100)

    def test_existing_git_ignore_owner_and_link_boundary(self):
        (self.root / "main.py").write_text("def visible(): pass")
        (self.root / "ignored.py").write_text("def invisible(): pass")
        completed = SimpleNamespace(returncode=0, stdout=b"ignored.py\0")
        with patch("workbench_backend.agents.project_outline.subprocess.run", return_value=completed):
            result = self.build()
        self.assertIn("visible", result.text)
        self.assertNotIn("invisible", result.text)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "linked.py").write_text("def outside_marker(): pass")
        try:
            (self.root / "linked.py").symlink_to(outside / "linked.py")
        except OSError:
            return  # Windows without Developer Mode: confinement covered by native integration.
        self.assertNotIn('"linked.py"', self.build().text)


if __name__ == "__main__":
    unittest.main()
