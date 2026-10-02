"""Permission boundary: This computer, excluded edits, delete, file order, windows, helpers."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage

from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.scripted_model import ScriptedChatModel
from tests.test_chat import wait_for_chat
from workbench_backend.agents.context import ContextObservation
from workbench_backend.agents.effective_setup import EffectiveSetup
from workbench_backend.agents.harness import HarnessService, _with_shell_folder
from workbench_backend.agents.helper_execution import _child_run_record, _narrow_child_access, _narrow_presented_tools
from workbench_backend.agents.host_shell import interrupt_on_for_run
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import (
    AgentRun,
    AgentRunStatus,
    InterruptDecisionRequest,
    PendingInterrupt,
    PendingInterruptAction,
)
from workbench_backend.agents.setup_schemas import FrozenHelperSelection, SetupConfiguration
from workbench_backend.app import create_app
from workbench_backend.desktop_automation import (
    DesktopAccessScope,
    DesktopAutomationError,
    DesktopAutomationService,
    WindowIdentity,
)
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ConnectedDeploymentRequest
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.preferences import (
    DEFAULT_SECRET_EXCLUSIONS,
    PROJECT_FILE_EXCLUSIONS,
    PermissionGrant,
    PreferenceStore,
)
from workbench_backend.state.store import ApplicationStore


EXACT = "echo marker > result.txt"
HOME_ONLY = "echo from-profile"


def _run(**updates) -> AgentRun:
    now = utc_now()
    values = dict(
        id="run-boundary",
        deployment_id="model",
        task="work",
        status=AgentRunStatus.running,
        thread_id="chat-1",
        approval_mode="ask",
        enabled_tools=["execute", "write_file", "edit_file", "apply_edits", "delete", "read_file"],
        presented_tools=["execute", "write_file", "edit_file", "apply_edits", "delete", "read_file"],
        created_at=now,
        updated_at=now,
    )
    values.update(updates)
    return AgentRun(**values)


def _request(name: str, args: dict):
    return SimpleNamespace(tool_call={"name": name, "id": "call-1", "args": args}, runtime=SimpleNamespace(state={"messages": []}))


def _pauses(run: AgentRun, grants, name: str, args: dict) -> bool:
    rules = interrupt_on_for_run(run, grants)
    if not rules or name not in rules:
        raise AssertionError(f"{name} has no approval gate")
    return bool(rules[name]["when"](_request(name, args)))


class _Parked:
    def __init__(self) -> None:
        self._stops: list[tuple[threading.Event, threading.Thread]] = []

    def resume(self, harness: HarnessService, run: AgentRun, actions: list[PendingInterruptAction], decisions: list[dict]):
        # A live worker keeps resume on the in-memory path. Restart would compile a graph.
        run.pending_interrupt = PendingInterrupt(
            interrupt_id=f"interrupt-{run.id}",
            namespace=["permissions"],
            action_requests=actions,
        )
        stop = threading.Event()
        worker = threading.Thread(target=stop.wait, daemon=True)
        worker.start()
        self._stops.append((stop, worker))
        harness._startup_reconciled = True
        harness._runs[run.id] = run
        harness._threads[run.id] = worker
        harness._cancels[run.id] = threading.Event()
        return harness.resume_interrupt(run.id, InterruptDecisionRequest(
            interrupt_id=run.pending_interrupt.interrupt_id,
            namespace=["permissions"],
            decisions=decisions,
        ), require_interrupt_identity=True)

    def close(self) -> None:
        for stop, worker in self._stops:
            stop.set()
            worker.join(2)


class ThisComputerGrantTests(unittest.TestCase):
    def test_ask_matches_exact_command_and_folder_after_this_chat_confirms(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root)
            folder = str(project.resolve())
            paths = WorkbenchPaths(project / "state")
            store = ApplicationStore(paths)
            parked = _Parked()
            try:
                prefs = PreferenceStore(store)
                harness = HarnessService(lambda: type("Manager", (), {"paths": paths})(), app_store=store)
                chat = _run(project_path=root, thread_id="chat-1", id="chat-run", source_surface="chat")
                other = _run(project_path=root, thread_id="other-chat", id="other-run", source_surface="chat")
                full = chat.model_copy(update={"approval_mode": "full_access", "id": "full-run"})
                saved = prefs.allow(other, PendingInterruptAction(
                    name="execute", args={"command": EXACT, "starting_folder": "C:\\not-the-grant"}), "always")
                prefs.confirm_host_shell("other-chat")
                self.assertEqual(saved.starting_folder, folder)
                self.assertTrue(saved.starting_folder.strip())
                self.assertNotIn("not-the-grant", saved.starting_folder)
                self.assertTrue(prefs.matches(other, "execute", {"command": EXACT, "timeout": 3}))
                # Another chat's Always allow does not skip this chat's first card.
                self.assertFalse(prefs.matches(chat, "execute", {"command": EXACT}))
                self.assertTrue(_pauses(chat, prefs, "execute", {"command": EXACT}))
                self.assertTrue(_pauses(full, prefs, "execute", {"command": EXACT}))
                self.assertIn(folder, interrupt_on_for_run(chat, prefs)["execute"]["description"])
                shown = _with_shell_folder(chat, PendingInterrupt(action_requests=[PendingInterruptAction(
                    name="execute", args={"command": EXACT, "starting_folder": "relative"})]))
                self.assertEqual(shown.action_requests[0].args["command"], EXACT)
                self.assertEqual(shown.action_requests[0].args["starting_folder"], folder)

                reject = _run(project_path=root, thread_id="chat-1", id="reject-run", source_surface="chat")
                parked.resume(harness, reject, [PendingInterruptAction(name="execute", args={"command": EXACT})],
                              [{"type": "reject"}])
                self.assertFalse(prefs.host_shell_confirmed("chat-1"))
                self.assertFalse(prefs.matches(chat, "execute", {"command": EXACT}))
                self.assertTrue(_pauses(chat, prefs, "execute", {"command": EXACT}))

                once = _run(project_path=root, thread_id="chat-1", id="once-run", source_surface="chat")
                parked.resume(harness, once, [PendingInterruptAction(name="execute", args={"command": "echo once"})],
                              [{"type": "approve", "scope": "once"}])
                self.assertTrue(prefs.host_shell_confirmed("chat-1"))
                self.assertFalse(prefs.matches(chat, "execute", {"command": "echo once"}))
                self.assertTrue(_pauses(chat, prefs, "execute", {"command": "echo once"}))
                self.assertFalse(_pauses(full, prefs, "execute", {"command": "echo somewhere-else"}))
                free = full.model_copy(update={"project_path": None, "id": "full-free"})
                self.assertFalse(_pauses(free, prefs, "execute", {"command": "echo project-free"}))

                session = _run(project_path=root, thread_id="chat-1", id="session-run", source_surface="chat")
                parked.resume(harness, session, [PendingInterruptAction(name="execute", args={"command": EXACT})],
                              [{"type": "approve", "scope": "session"}])
                self.assertFalse(_pauses(chat, prefs, "execute", {"command": EXACT, "timeout": 9, "starting_folder": "D:\\ignored"}))
                self.assertTrue(_pauses(chat, prefs, "execute", {"command": EXACT + " extra"}))
                self.assertTrue(_pauses(chat, prefs, "execute", {"command": "echo other"}))
                elsewhere = chat.model_copy(update={"project_path": str(project / "elsewhere")})
                self.assertTrue(_pauses(elsewhere, prefs, "execute", {"command": EXACT}))

                home = _run(project_path=None, thread_id="home-chat", id="home-run", source_surface="chat")
                home_grant = prefs.allow(home, PendingInterruptAction(name="execute", args={"command": HOME_ONLY}), "always")
                self.assertEqual(home_grant.starting_folder, str(Path.home().resolve()))
                prefs.confirm_host_shell("home-chat")
                self.assertTrue(prefs.matches(home, "execute", {"command": HOME_ONLY}))
                self.assertFalse(prefs.matches(chat.model_copy(update={"thread_id": "home-chat"}), "execute", {"command": HOME_ONLY}))

                for stored_folder in ("", None):
                    empty = PermissionGrant(
                        id=f"grant-empty-{stored_folder is None}", scope="always", action="execute",
                        arguments={"command": "echo empty"}, created_at=utc_now(), source_run_id="manual",
                        starting_folder=stored_folder)
                    with store._lock, store._conn:
                        store._conn.execute("INSERT INTO permission_grants VALUES(?, ?)", (empty.id, empty.model_dump_json()))
                self.assertFalse(prefs.matches(chat, "execute", {"command": "echo empty"}))

                direct = _run(thread_id=None, approval_mode="full_access", project_path=root, id="direct-run")
                self.assertFalse(_pauses(direct, prefs, "execute", {"command": "echo direct"}))
                self.assertTrue(_pauses(direct.model_copy(update={"project_path": None}), prefs, "execute", {"command": "echo direct"}))

                disabled = _run(id="disabled-run", thread_id="disabled-chat", enabled_tools=[], presented_tools=["execute"], project_path=root, source_surface="chat")
                with self.assertRaises(HarnessError) as raised:
                    parked.resume(harness, disabled, [PendingInterruptAction(name="execute", args={"command": EXACT})],
                                  [{"type": "approve", "scope": "always"}])
                self.assertEqual(raised.exception.code, "interrupt_tool_unavailable")
                self.assertFalse(prefs.host_shell_confirmed("disabled-chat"))
            finally:
                parked.close()
                store.close()


class ExcludedEditTests(unittest.TestCase):
    def test_excluded_approval_covers_only_that_edit_for_every_duration(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root) / "state")
            store = ApplicationStore(paths)
            parked = _Parked()
            try:
                prefs = PreferenceStore(store)
                harness = HarnessService(lambda: type("Manager", (), {"paths": paths})(), app_store=store)
                run = _run(project_path=root, thread_id="edits", id="edit-run")
                actions = [
                    PendingInterruptAction(name="write_file", args={"file_path": "/.env", "content": "SECRET"}),
                    PendingInterruptAction(name="edit_file", args={"file_path": "/.git/HEAD", "old_string": "a", "new_string": "b"}),
                    PendingInterruptAction(name="apply_edits", args={"file_path": "/.env.local", "base_sha256": "a" * 64, "edits": [{"old_string": "a", "new_string": "b"}]}),
                    PendingInterruptAction(name="write_file", args={"file_path": "/notes.txt", "content": "ok"}),
                    PendingInterruptAction(name="delete", args={"file_path": "/.env"}),
                ]
                parked.resume(harness, run, actions, [
                    {"type": "approve", "scope": "once"},
                    {"type": "approve", "scope": "session"},
                    {"type": "approve", "scope": "always"},
                    {"type": "approve", "scope": "session"},
                    {"type": "approve", "scope": "always"},
                ])
                self.assertFalse(prefs.host_shell_confirmed("edits"))
                saved = {(grant.action, grant.arguments.get("file_path"), grant.scope) for grant in prefs.grants()}
                self.assertEqual(saved, {
                    ("edit_file", "/.git/HEAD", "session"),
                    ("apply_edits", "/.env.local", "always"),
                    ("write_file", "/notes.txt", "session"),
                    ("delete", "/.env", "always"),
                })
                for name, args in (
                    ("write_file", {"file_path": "/.env", "content": "SECRET"}),
                    ("edit_file", {"file_path": "/.git/HEAD", "old_string": "a", "new_string": "b"}),
                    ("apply_edits", {"file_path": "/.env.local", "base_sha256": "a" * 64, "edits": [{"old_string": "a", "new_string": "b"}]}),
                ):
                    self.assertFalse(prefs.excluded_file_edit(run, name, args))
                self.assertTrue(_pauses(run, prefs, "write_file", {"file_path": "/.env", "content": "SECRET"}))
                self.assertFalse(_pauses(run, prefs, "edit_file", {"file_path": "/.git/HEAD", "old_string": "a", "new_string": "b"}))
                self.assertFalse(_pauses(run, prefs, "apply_edits", {"file_path": "/.env.local", "base_sha256": "a" * 64, "edits": [{"old_string": "a", "new_string": "b"}]}))
                self.assertFalse(_pauses(run, prefs, "write_file", {"file_path": "/notes.txt", "content": "ok"}))
                self.assertFalse(_pauses(run, prefs, "delete", {"file_path": "/.env"}))
                self.assertTrue(_pauses(run, prefs, "delete", {"file_path": "/.env.again"}))

                standing = PermissionGrant(
                    id="grant-standing", kind="project_files", scope="always", project_path=str(Path(root).resolve()),
                    action="project_files", arguments={}, created_at=utc_now(), source_run_id="settings",
                    operations=["write_file", "edit_file"], excluded_paths=[])
                with store._lock, store._conn:
                    store._conn.execute("INSERT INTO permission_grants VALUES(?, ?)", (standing.id, standing.model_dump_json()))
                # A stored grant that dropped secrets is not given the defaults back. Git stays excluded.
                self.assertFalse(prefs.excluded_file_edit(run, "write_file", {"file_path": "/.env"}))
                self.assertTrue(prefs.excluded_file_edit(run, "write_file", {"file_path": "/.git/config"}))
                self.assertTrue(all(pattern in PROJECT_FILE_EXCLUSIONS for pattern in (".git", ".git/**", "**/.git", "**/.git/**")))
                widened = _run(project_path=root, thread_id="standing", id="standing-run")
                before = len(prefs.grants())
                parked.resume(harness, widened, [
                    PendingInterruptAction(name="write_file", args={"file_path": "/.env", "content": "kept"}),
                    PendingInterruptAction(name="write_file", args={"file_path": "/.git/config", "content": "no"}),
                ], [{"type": "approve", "scope": "session"}, {"type": "approve", "scope": "always"}])
                paths_saved = {grant.arguments.get("file_path") for grant in prefs.grants()}
                self.assertIn("/.env", paths_saved)
                self.assertNotIn("/.git/config", paths_saved)
                self.assertEqual(len(prefs.grants()), before + 1)
                self.assertTrue(_pauses(widened, prefs, "write_file", {"file_path": "/.git/config", "content": "no"}))

                secrets = PermissionGrant(
                    id="grant-secrets", kind="project_files", scope="always", project_path=str(Path(root).resolve()),
                    action="project_files", arguments={}, created_at=utc_now(), source_run_id="settings",
                    operations=["write_file", "edit_file"], excluded_paths=list(DEFAULT_SECRET_EXCLUSIONS))
                with store._lock, store._conn:
                    store._conn.execute("INSERT INTO permission_grants VALUES(?, ?)", (secrets.id, secrets.model_dump_json()))
                self.assertTrue(prefs.excluded_file_edit(run, "write_file", {"file_path": "/.env"}))
                self.assertTrue(prefs.excluded_file_edit(run, "apply_edits", {"file_path": "/.env.local"}))
                held = len(prefs.grants())
                parked.resume(harness, _run(project_path=root, thread_id="secret-edit", id="secret-run"), [
                    PendingInterruptAction(name="write_file", args={"file_path": "/.env", "content": "SECRET"}),
                    PendingInterruptAction(name="edit_file", args={"file_path": "/.git/HEAD", "old_string": "a", "new_string": "b"}),
                    PendingInterruptAction(name="apply_edits", args={"file_path": "/.env.local", "base_sha256": "a" * 64, "edits": [{"old_string": "a", "new_string": "b"}]}),
                ], [
                    {"type": "approve", "scope": "once"},
                    {"type": "approve", "scope": "session"},
                    {"type": "approve", "scope": "always"},
                ])
                self.assertEqual(len(prefs.grants()), held)
                for name, args in (
                    ("write_file", {"file_path": "/.env", "content": "SECRET"}),
                    ("edit_file", {"file_path": "/.git/HEAD", "old_string": "a", "new_string": "b"}),
                    ("apply_edits", {"file_path": "/.env.local", "base_sha256": "a" * 64, "edits": [{"old_string": "a", "new_string": "b"}]}),
                ):
                    self.assertIsNone(prefs.matching_grant(run, name, args))
                    self.assertTrue(_pauses(run, prefs, name, args))
            finally:
                parked.close()
                store.close()


class DeleteBoundaryTests(unittest.TestCase):
    def test_full_access_delete_removes_git_and_secrets_and_still_refuses_unsafe_targets(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root)
            git = project / ".git"
            git.mkdir()
            (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            (project / ".env").write_text("SECRET=1\n", encoding="utf-8")
            nested = project / "nested"
            (nested / ".git").mkdir(parents=True)
            (nested / ".git" / "HEAD").write_text("ref\n", encoding="utf-8")
            (nested / ".env").write_text("SECRET=2\n", encoding="utf-8")
            (nested / "note.txt").write_text("gone\n", encoding="utf-8")
            wide = project / "wide"
            wide.mkdir()
            (wide / "a.txt").write_text("a", encoding="utf-8")
            (wide / "b.txt").write_text("b", encoding="utf-8")
            run = _run(project_path=root, approval_mode="full_access", thread_id="delete-chat", id="delete-run",
                       enabled_tools=["delete"], presented_tools=["delete"])
            for path in ("/.git", "/.env", "/nested"):
                self.assertFalse(_pauses(run, None, "delete", {"file_path": path}))
            ask = run.model_copy(update={"approval_mode": "ask", "id": "ask-delete"})
            self.assertTrue(_pauses(ask, None, "delete", {"file_path": "/.env"}))

            from deepagents.backends import FilesystemBackend
            backend = FilesystemBackend(root_dir=str(project), virtual_mode=True)
            middleware = WorkbenchHarnessMiddleware(run)

            def remove(path: str, call_id: str):
                called = []
                request = SimpleNamespace(tool_call={"name": "delete", "args": {"file_path": path}, "id": call_id},
                                          runtime=SimpleNamespace(state={"messages": []}))

                def handler(_request):
                    called.append(path)
                    result = backend.delete(path)
                    failed = bool(getattr(result, "error", None))
                    return ToolMessage(content=result.error or "Deleted", name="delete", tool_call_id=call_id,
                                       status="error" if failed else "success")

                message = middleware.wrap_tool_call(request, handler)
                return called, message

            called, message = remove("/.env", "delete-env")
            self.assertEqual(called, ["/.env"])
            self.assertFalse((project / ".env").exists())
            evidence = run.tool_outcomes["delete-env"].evidence
            self.assertTrue(evidence["before_exists"])
            self.assertTrue(evidence["after_inspected"])
            self.assertFalse(evidence["after_exists"])
            self.assertNotIn("undo", message.content.lower())

            called, _message = remove("/.git", "delete-git")
            self.assertEqual(called, ["/.git"])
            self.assertFalse(git.exists())

            called, _message = remove("/nested", "delete-nested")
            self.assertEqual(called, ["/nested"])
            self.assertFalse(nested.exists())
            nested_evidence = run.tool_outcomes["delete-nested"].evidence
            self.assertTrue(nested_evidence["after_inspected"])
            self.assertFalse(nested_evidence["after_exists"])
            self.assertGreater(nested_evidence["before_entries"], 1)

            def refused(path: str, call_id: str, text: str):
                called, message = remove(path, call_id)
                self.assertEqual(called, [], path)
                self.assertIn(text, message.content)

            refused("/", "delete-root", "project root")
            self.assertTrue(project.exists())
            with tempfile.TemporaryDirectory() as outside:
                outside_file = Path(outside) / "kept.txt"
                outside_file.write_text("stay", encoding="utf-8")
                link = project / "escape"
                try:
                    link.symlink_to(outside, target_is_directory=True)
                except OSError:
                    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), outside], check=True, capture_output=True)
                try:
                    refused("/escape", "delete-link", "symbolic link")
                    self.assertTrue(outside_file.exists())
                    self.assertTrue(link.exists())
                finally:
                    if link.is_junction():
                        link.rmdir()
                    elif link.exists() or link.is_symlink():
                        link.unlink()

            with patch("workbench_backend.agents.file_operations.MAX_DELETE_ENTRIES", 2):
                refused("/wide", "delete-wide", "inspection limit")
            self.assertTrue((wide / "a.txt").exists())
            self.assertTrue((wide / "b.txt").exists())


class FileOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_files_proceed_while_the_same_file_waits_off_the_worker(self):
        from workbench_backend.agents.file_operations import file_order_lock, file_order_path

        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="file-order")
        loop.set_default_executor(executor)
        release = threading.Event()
        tasks: list[asyncio.Task] = []
        try:
            with tempfile.TemporaryDirectory() as area:
                project = Path(area)
                (project / "same.txt").write_text("old", encoding="utf-8")
                run = _run(project_path=str(project), id="file-order", enabled_tools=["write_file", "read_file"],
                           presented_tools=["write_file", "read_file"])
                middleware = WorkbenchHarnessMiddleware(run)
                inside = threading.Event()

                async def hold(_request):
                    def work():
                        inside.set()
                        if not release.wait(5):
                            raise TimeoutError("holder was not released")
                        (project / "same.txt").write_text("new", encoding="utf-8")
                        return ToolMessage(content="new", name="write_file", tool_call_id="hold")
                    return await asyncio.to_thread(work)

                holder = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call={"name": "write_file", "args": {"file_path": "same.txt", "content": "new"}, "id": "hold"},
                                    runtime=SimpleNamespace(state={"messages": []})), hold))
                tasks.append(holder)
                self.assertTrue(await asyncio.to_thread(inside.wait, 5))
                lease = file_order_lock(file_order_path(project, "same.txt"))

                async def read(_request):
                    def work():
                        return ToolMessage(content=(project / "same.txt").read_text(encoding="utf-8"), name="read_file", tool_call_id="read")
                    return await asyncio.to_thread(work)

                reader = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call={"name": "read_file", "args": {"file_path": "same.txt"}, "id": "read"},
                                    runtime=SimpleNamespace(state={"messages": []})), read))
                tasks.append(reader)
                await self._until(lambda: lease.waiting() >= 1)
                self.assertFalse(reader.done())

                async def write_other(_request):
                    def work():
                        (project / "other.txt").write_text("other", encoding="utf-8")
                        return ToolMessage(content="other", name="write_file", tool_call_id="other")
                    return await asyncio.to_thread(work)

                other = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call={"name": "write_file", "args": {"file_path": "other.txt", "content": "other"}, "id": "other"},
                                    runtime=SimpleNamespace(state={"messages": []})), write_other))
                tasks.append(other)
                await asyncio.wait_for(other, 5)
                self.assertEqual((project / "other.txt").read_text(encoding="utf-8"), "other")
                self.assertFalse(reader.done())
                self.assertFalse(holder.done())
                self.assertGreaterEqual(lease.waiting(), 1)

                async def write_same(_request):
                    def work():
                        (project / "same.txt").write_text("second", encoding="utf-8")
                        return ToolMessage(content="second", name="write_file", tool_call_id="second")
                    return await asyncio.to_thread(work)

                second = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call={"name": "write_file", "args": {"file_path": "same.txt", "content": "second"}, "id": "second"},
                                    runtime=SimpleNamespace(state={"messages": []})), write_same))
                tasks.append(second)
                await self._until(lambda: lease.waiting() >= 2)
                self.assertFalse(second.done())
                release.set()
                await asyncio.wait_for(holder, 5)
                read_message = await asyncio.wait_for(reader, 5)
                await asyncio.wait_for(second, 5)
                self.assertEqual(read_message.content, "new")
                self.assertEqual((project / "same.txt").read_text(encoding="utf-8"), "second")
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
            executor.shutdown(wait=True, cancel_futures=True)

    def test_dot_segment_shares_the_lease_and_an_illegal_path_is_refused(self):
        from langchain_core.tools import ToolException
        from workbench_backend.agents.file_operations import file_order_lock, file_order_path, hold_file_order

        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            notes = file_order_path(project, "notes.txt")
            self.assertEqual(notes, file_order_path(project, "./notes.txt"))
            self.assertEqual(notes, file_order_path(project, "/notes.txt"))
            self.assertEqual(file_order_path(project, "nested/notes.txt"), file_order_path(project, "nested/./notes.txt"))
            self.assertIs(file_order_lock(notes), file_order_lock(file_order_path(project, "./notes.txt")))
            for illegal in ("../notes.txt", "nested/../../notes.txt", "C:/outside.txt", "//host/share"):
                with self.assertRaises(ValueError, msg=illegal):
                    file_order_path(project, illegal)
            with hold_file_order(file_order_path(project, "dir")):
                with self.assertRaises(ToolException):
                    with hold_file_order(file_order_path(project, "dir/child.txt")):
                        pass
            run = _run(project_path=str(project), id="illegal-path")
            middleware = WorkbenchHarnessMiddleware(run)
            called = []
            message = AIMessage(content="", tool_calls=[
                {"name": "write_file", "args": {"file_path": "notes.txt", "content": "one"}, "id": "1", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "./notes.txt", "content": "two"}, "id": "2", "type": "tool_call"},
                {"name": "delete", "args": {"file_path": "notes.txt"}, "id": "3", "type": "tool_call"},
            ])

            def effect(request):
                called.append(request.tool_call["id"])
                target = project / "notes.txt"
                if request.tool_call["name"] == "delete":
                    target.unlink(missing_ok=True)
                else:
                    target.write_text(request.tool_call["args"]["content"], encoding="utf-8")
                return ToolMessage(content="done", name=request.tool_call["name"], tool_call_id=request.tool_call["id"])

            for call in message.tool_calls:
                result = middleware.wrap_tool_call(SimpleNamespace(
                    tool_call=call, runtime=SimpleNamespace(state={"messages": [message]})), effect)
                self.assertEqual(result.status, "success", result.content)
            self.assertEqual(called, ["1", "2", "3"])
            self.assertFalse((project / "notes.txt").exists())
            refused = middleware.wrap_tool_call(SimpleNamespace(
                tool_call={"name": "write_file", "args": {"file_path": "../notes.txt", "content": "no"}, "id": "bad"},
                runtime=SimpleNamespace(state={"messages": []})), lambda _request: called.append("bad"))
            self.assertEqual(called, ["1", "2", "3"])
            self.assertEqual(refused.status, "error")
            self.assertIn("inside this project", refused.content)

    async def test_same_message_effects_finish_in_call_order(self):
        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            run = _run(project_path=str(project), id="batch-order")
            middleware = WorkbenchHarnessMiddleware(run)

            async def effect(request):
                def work():
                    name = request.tool_call["name"]
                    args = request.tool_call["args"]
                    target = project / str(args["file_path"]).replace("\\", "/").lstrip("./")
                    if name == "delete":
                        if target.is_dir():
                            import shutil
                            shutil.rmtree(target)
                        else:
                            target.unlink(missing_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(args["content"], encoding="utf-8")
                    return ToolMessage(content="done", name=name, tool_call_id=request.tool_call["id"])
                return await asyncio.to_thread(work)

            write_calls = [
                {"name": "write_file", "args": {"file_path": "notes.txt", "content": "one"}, "id": "one", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "./notes.txt", "content": "two"}, "id": "two", "type": "tool_call"},
            ]
            write_state = {"messages": [AIMessage(content="", tool_calls=write_calls)]}
            write_results = await asyncio.wait_for(asyncio.gather(*(
                middleware.awrap_tool_call(SimpleNamespace(
                    tool_call=call, runtime=SimpleNamespace(state=write_state)), effect)
                for call in write_calls
            )), 5)
            self.assertEqual([item.status for item in write_results], ["success", "success"])
            self.assertEqual((project / "notes.txt").read_text(encoding="utf-8"), "two")

            nested_calls = [
                {"name": "delete", "args": {"file_path": "dir"}, "id": "remove", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "rewrite", "type": "tool_call"},
            ]
            nested_state = {"messages": [AIMessage(content="", tool_calls=nested_calls)]}
            nested_results = await asyncio.wait_for(asyncio.gather(*(
                middleware.awrap_tool_call(SimpleNamespace(
                    tool_call=call, runtime=SimpleNamespace(state=nested_state)), effect)
                for call in nested_calls
            )), 5)
            self.assertEqual([item.status for item in nested_results], ["success", "success"])
            self.assertEqual((project / "dir" / "child.txt").read_text(encoding="utf-8"), "after")

    async def test_paused_directory_delete_holds_the_nested_write(self):
        from langgraph.errors import GraphInterrupt

        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            run = _run(project_path=str(project), id="pause-order")
            middleware = WorkbenchHarnessMiddleware(run)
            resume = asyncio.Event()
            saw_directory = []

            async def effect(request):
                name = request.tool_call["name"]
                args = request.tool_call["args"]
                if name == "delete":
                    if not resume.is_set():
                        raise GraphInterrupt(())

                    def remove():
                        import shutil
                        shutil.rmtree(project / "dir")

                    await asyncio.to_thread(remove)
                    return ToolMessage(content="removed", name=name, tool_call_id=request.tool_call["id"])

                def observe():
                    saw_directory.append((project / "dir").exists())
                    target = project / "dir" / "child.txt"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(args["content"], encoding="utf-8")

                await asyncio.to_thread(observe)
                return ToolMessage(content="wrote", name=name, tool_call_id=request.tool_call["id"])

            calls = [
                {"name": "delete", "args": {"file_path": "dir"}, "id": "remove", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "rewrite", "type": "tool_call"},
            ]
            state = {"messages": [AIMessage(content="", tool_calls=calls)]}
            requests = [SimpleNamespace(tool_call=call, runtime=SimpleNamespace(state=state)) for call in calls]
            delete_task = asyncio.create_task(middleware.awrap_tool_call(requests[0], effect))
            write_task = asyncio.create_task(middleware.awrap_tool_call(requests[1], effect))
            resumed = written = None
            try:
                await self._until(lambda: getattr(run.tool_outcomes.get("remove"), "outcome", None) == "not_dispatched")
                await self._until(lambda: "remove" in middleware._call_settled or saw_directory)
                await asyncio.sleep(0.05)
                self.assertEqual(run.tool_outcomes["remove"].outcome, "not_dispatched")
                self.assertFalse(middleware._call_settled["remove"].is_set())
                self.assertFalse(write_task.done())
                self.assertEqual(saw_directory, [])
                self.assertEqual((project / "dir" / "child.txt").read_text(encoding="utf-8"), "before")
                resume.set()
                resumed = await asyncio.wait_for(middleware.awrap_tool_call(requests[0], effect), 5)
                with self.assertRaises(GraphInterrupt):
                    await asyncio.wait_for(delete_task, 5)
                written = await asyncio.wait_for(write_task, 5)
            finally:
                resume.set()
                for task in (delete_task, write_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(delete_task, write_task, return_exceptions=True)
            self.assertEqual(getattr(resumed, "status", None), "success")
            self.assertEqual(run.tool_outcomes["remove"].outcome, "succeeded")
            self.assertEqual(saw_directory, [False])
            self.assertEqual(getattr(written, "status", None), "success")
            self.assertEqual(run.tool_outcomes["rewrite"].outcome, "succeeded")
            self.assertEqual((project / "dir" / "child.txt").read_text(encoding="utf-8"), "after")

    async def test_rejected_directory_delete_releases_the_nested_write(self):
        from langgraph.errors import GraphInterrupt

        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            (folder / "keep.txt").write_text("keep", encoding="utf-8")
            run = _run(project_path=str(project), id="reject-order")
            middleware = WorkbenchHarnessMiddleware(run)
            saw_directory = []

            async def effect(request):
                name = request.tool_call["name"]
                if name == "delete":
                    raise GraphInterrupt(())

                def observe():
                    saw_directory.append((project / "dir").exists())
                    target = project / "dir" / "child.txt"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(request.tool_call["args"]["content"], encoding="utf-8")

                await asyncio.to_thread(observe)
                return ToolMessage(content="wrote", name=name, tool_call_id=request.tool_call["id"])

            calls = [
                {"name": "delete", "args": {"file_path": "dir"}, "id": "remove", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "rewrite", "type": "tool_call"},
            ]
            state = {"messages": [AIMessage(content="", tool_calls=calls)]}
            requests = [SimpleNamespace(tool_call=call, runtime=SimpleNamespace(state=state)) for call in calls]
            delete_task = asyncio.create_task(middleware.awrap_tool_call(requests[0], effect))
            write_task = asyncio.create_task(middleware.awrap_tool_call(requests[1], effect))
            try:
                await self._until(lambda: getattr(run.tool_outcomes.get("remove"), "outcome", None) == "not_dispatched")
                await asyncio.sleep(0.05)
                self.assertFalse(write_task.done())
                self.assertEqual(saw_directory, [])
                self.assertEqual((folder / "child.txt").read_text(encoding="utf-8"), "before")
                self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
                state["messages"].append(ToolMessage(
                    content="User rejected the tool call for `delete` with id remove. The tool was not executed.",
                    name="delete", tool_call_id="remove", status="error"))
                written = await asyncio.wait_for(write_task, 5)
                with self.assertRaises(GraphInterrupt):
                    await asyncio.wait_for(delete_task, 5)
            finally:
                for task in (delete_task, write_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(delete_task, write_task, return_exceptions=True)
            self.assertEqual(run.tool_outcomes["remove"].outcome, "failed")
            self.assertEqual(saw_directory, [True])
            self.assertEqual(getattr(written, "status", None), "success")
            self.assertEqual(run.tool_outcomes["rewrite"].outcome, "succeeded")
            self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
            self.assertEqual((folder / "child.txt").read_text(encoding="utf-8"), "after")

    async def test_failed_directory_delete_releases_the_nested_write(self):
        from langchain_core.tools import ToolException

        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            (folder / "keep.txt").write_text("keep", encoding="utf-8")
            run = _run(project_path=str(project), id="fail-order")
            middleware = WorkbenchHarnessMiddleware(run)
            saw_directory = []

            async def effect(request):
                name = request.tool_call["name"]
                if name == "delete":
                    raise ToolException("The delete failed before it changed the tree.")

                def observe():
                    saw_directory.append(run.tool_outcomes["remove"].outcome)
                    target = project / "dir" / "child.txt"
                    target.write_text(request.tool_call["args"]["content"], encoding="utf-8")

                await asyncio.to_thread(observe)
                return ToolMessage(content="wrote", name=name, tool_call_id=request.tool_call["id"])

            calls = [
                {"name": "delete", "args": {"file_path": "dir"}, "id": "remove", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "rewrite", "type": "tool_call"},
            ]
            state = {"messages": [AIMessage(content="", tool_calls=calls)]}
            delete_result, written = await asyncio.wait_for(asyncio.gather(*(
                middleware.awrap_tool_call(SimpleNamespace(
                    tool_call=call, runtime=SimpleNamespace(state=state)), effect)
                for call in calls
            )), 5)
            self.assertEqual(delete_result.status, "error")
            self.assertEqual(run.tool_outcomes["remove"].outcome, "failed")
            self.assertEqual(saw_directory, ["failed"])
            self.assertEqual(written.status, "success")
            self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
            self.assertEqual((folder / "child.txt").read_text(encoding="utf-8"), "after")

    async def test_old_error_with_a_reused_id_does_not_release_the_new_write(self):
        from langgraph.errors import GraphInterrupt

        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            (folder / "keep.txt").write_text("keep", encoding="utf-8")
            run = _run(project_path=str(project), id="reused-id-old-error")
            middleware = WorkbenchHarnessMiddleware(run)
            saw_directory = []

            async def effect(request):
                name = request.tool_call["name"]
                if name == "delete":
                    raise GraphInterrupt(())

                def observe():
                    saw_directory.append((project / "dir").exists())
                    target = project / "dir" / "child.txt"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(request.tool_call["args"]["content"], encoding="utf-8")

                await asyncio.to_thread(observe)
                return ToolMessage(content="wrote", name=name, tool_call_id=request.tool_call["id"])

            new_calls = [
                {"name": "delete", "args": {"file_path": "dir"}, "id": "call_1", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "call_2", "type": "tool_call"},
            ]
            state = {"messages": [
                AIMessage(content="", tool_calls=[
                    {"name": "delete", "args": {"file_path": "other"}, "id": "call_1", "type": "tool_call"},
                ]),
                ToolMessage(
                    content="User rejected the tool call for `delete` with id call_1. The tool was not executed.",
                    name="delete", tool_call_id="call_1", status="error"),
                AIMessage(content="", tool_calls=new_calls),
            ]}
            requests = [SimpleNamespace(tool_call=call, runtime=SimpleNamespace(state=state)) for call in new_calls]
            delete_task = asyncio.create_task(middleware.awrap_tool_call(requests[0], effect))
            write_task = asyncio.create_task(middleware.awrap_tool_call(requests[1], effect))
            try:
                await self._until(lambda: getattr(run.tool_outcomes.get("call_1"), "outcome", None) == "not_dispatched")
                await self._until(lambda: "call_1" in middleware._call_settled or saw_directory)
                await asyncio.sleep(0.05)
                self.assertEqual(run.tool_outcomes["call_1"].outcome, "not_dispatched")
                self.assertEqual(run.tool_outcomes["call_1"].detail, "Waiting for approval or an answer.")
                self.assertFalse(middleware._call_settled["call_1"].is_set())
                self.assertFalse(write_task.done())
                self.assertEqual(saw_directory, [])
                self.assertEqual((folder / "child.txt").read_text(encoding="utf-8"), "before")
                self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
            finally:
                for task in (delete_task, write_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(delete_task, write_task, return_exceptions=True)

    async def test_later_attempt_after_rejection_waits_for_its_own_effect(self):
        from langgraph.errors import GraphInterrupt

        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            (folder / "keep.txt").write_text("keep", encoding="utf-8")
            run = _run(project_path=str(project), id="reused-id-next-attempt")
            middleware = WorkbenchHarnessMiddleware(run)
            release = asyncio.Event()
            saw_directory = []

            async def effect(request):
                name = request.tool_call["name"]
                if name == "delete":
                    if not release.is_set():
                        raise GraphInterrupt(())

                    def remove():
                        import shutil
                        shutil.rmtree(project / "dir")

                    await asyncio.to_thread(remove)
                    return ToolMessage(content="removed", name=name, tool_call_id=request.tool_call["id"])

                def observe():
                    saw_directory.append((project / "dir").exists())
                    target = project / "dir" / "child.txt"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(request.tool_call["args"]["content"], encoding="utf-8")

                await asyncio.to_thread(observe)
                return ToolMessage(content="wrote", name=name, tool_call_id=request.tool_call["id"])

            first_calls = [
                {"name": "delete", "args": {"file_path": "dir"}, "id": "call_1", "type": "tool_call"},
                {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "call_2", "type": "tool_call"},
            ]
            state = {"messages": [AIMessage(content="", tool_calls=first_calls)]}
            first_requests = [SimpleNamespace(tool_call=call, runtime=SimpleNamespace(state=state)) for call in first_calls]
            delete_task = asyncio.create_task(middleware.awrap_tool_call(first_requests[0], effect))
            write_task = asyncio.create_task(middleware.awrap_tool_call(first_requests[1], effect))
            later_delete = later_write = resumed = written = None
            try:
                await self._until(lambda: getattr(run.tool_outcomes.get("call_1"), "outcome", None) == "not_dispatched")
                state["messages"].append(ToolMessage(
                    content="User rejected the tool call for `delete` with id call_1. The tool was not executed.",
                    name="delete", tool_call_id="call_1", status="error"))
                written = await asyncio.wait_for(write_task, 5)
                with self.assertRaises(GraphInterrupt):
                    await asyncio.wait_for(delete_task, 5)
                self.assertEqual(run.tool_outcomes["call_1"].outcome, "failed")
                self.assertTrue(middleware._call_settled["call_1"].is_set())
                self.assertEqual(saw_directory, [True])
                self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
                (folder / "child.txt").write_text("before", encoding="utf-8")
                saw_directory.clear()

                later_calls = [
                    {"name": "delete", "args": {"file_path": "dir"}, "id": "call_1", "type": "tool_call"},
                    {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "later"}, "id": "call_3", "type": "tool_call"},
                ]
                state["messages"].append(AIMessage(content="", tool_calls=later_calls))
                later_requests = [SimpleNamespace(tool_call=call, runtime=SimpleNamespace(state=state)) for call in later_calls]
                later_delete = asyncio.create_task(middleware.awrap_tool_call(later_requests[0], effect))
                await self._until(lambda: (
                    getattr(run.tool_outcomes.get("call_1"), "outcome", None) == "not_dispatched"
                    and middleware._file_attempts.get("call_1", 0) >= 2
                    and "call_1" in middleware._call_settled
                    and not middleware._call_settled["call_1"].is_set()))
                with self.assertRaises(GraphInterrupt):
                    await asyncio.wait_for(later_delete, 5)
                later_write = asyncio.create_task(middleware.awrap_tool_call(later_requests[1], effect))
                await asyncio.sleep(0.05)
                self.assertEqual(run.tool_outcomes["call_1"].outcome, "not_dispatched")
                self.assertFalse(middleware._call_settled["call_1"].is_set())
                self.assertFalse(later_write.done())
                self.assertEqual(saw_directory, [])
                self.assertEqual((folder / "child.txt").read_text(encoding="utf-8"), "before")
                self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
                release.set()
                resumed = await asyncio.wait_for(middleware.awrap_tool_call(later_requests[0], effect), 5)
                written = await asyncio.wait_for(later_write, 5)
            finally:
                release.set()
                for task in (delete_task, write_task, later_delete, later_write):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(
                    delete_task, write_task,
                    *([later_delete] if later_delete is not None else []),
                    *([later_write] if later_write is not None else []),
                    return_exceptions=True)
            self.assertEqual(getattr(resumed, "status", None), "success")
            self.assertEqual(run.tool_outcomes["call_1"].outcome, "succeeded")
            self.assertEqual(saw_directory, [False])
            self.assertEqual(getattr(written, "status", None), "success")
            self.assertEqual((project / "dir" / "child.txt").read_text(encoding="utf-8"), "later")
            self.assertFalse((folder / "keep.txt").exists())

    async def test_older_result_does_not_release_the_newer_attempt(self):
        with tempfile.TemporaryDirectory() as area:
            project = Path(area)
            folder = project / "dir"
            folder.mkdir()
            (folder / "child.txt").write_text("before", encoding="utf-8")
            (folder / "keep.txt").write_text("keep", encoding="utf-8")
            run = _run(project_path=str(project), id="reused-id-superseded")
            middleware = WorkbenchHarnessMiddleware(run)
            # Hold the older entry after it has reserved the id and before the file lease.
            # The owner must reach reserve_tool in that window. Settling there lets the write run first.
            release_old = threading.Event()
            release_effect = asyncio.Event()
            owner_at_reserve = asyncio.Event()
            saw_directory = []
            handler_runs = []
            control = middleware.execution_control
            original_reserve = control.reserve_tool
            original_begin = middleware._begin_tool

            def reserve(run, call_id, name=""):
                if control.tool_call_inflight(run, call_id):
                    owner_at_reserve.set()
                return original_reserve(run, call_id, name)

            def begin(request, attempt=None):
                original_begin(request, attempt)
                if request.tool_call["id"] == "call_1" and attempt == 1:
                    release_old.wait()

            control.reserve_tool = reserve
            middleware._begin_tool = begin

            async def effect(request):
                name = request.tool_call["name"]
                call_id = request.tool_call["id"]
                if name == "delete":
                    handler_runs.append(call_id)
                    if call_id == "call_3":
                        await release_effect.wait()

                    def remove():
                        import shutil
                        shutil.rmtree(project / request.tool_call["args"]["file_path"])

                    await asyncio.to_thread(remove)
                    return ToolMessage(content="removed", name=name, tool_call_id=call_id)

                def observe():
                    target = project / request.tool_call["args"]["file_path"]
                    saw_directory.append(target.parent.exists())
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(request.tool_call["args"]["content"], encoding="utf-8")

                await asyncio.to_thread(observe)
                return ToolMessage(content="wrote", name=name, tool_call_id=call_id)

            delete_call = {"name": "delete", "args": {"file_path": "dir"}, "id": "call_1", "type": "tool_call"}
            write_call = {"name": "write_file", "args": {"file_path": "dir/child.txt", "content": "after"}, "id": "call_2", "type": "tool_call"}
            message = AIMessage(content="", tool_calls=[delete_call, write_call])
            state = {"messages": [message]}
            older = asyncio.create_task(middleware.awrap_tool_call(
                SimpleNamespace(tool_call=delete_call, runtime=SimpleNamespace(state=state)), effect))
            newer = write_task = older_ran = newer_ran = write_ran = None
            try:
                await self._until(lambda: getattr(run.tool_outcomes.get("call_1"), "outcome", None) == "running")
                newer = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call=delete_call, runtime=SimpleNamespace(state=state)), effect))
                await self._until(lambda: owner_at_reserve.is_set() and middleware._file_attempts.get("call_1", 0) >= 2)
                write_task = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call=write_call, runtime=SimpleNamespace(state=state)), effect))
                await asyncio.sleep(0.2)
                self.assertTrue(owner_at_reserve.is_set())
                self.assertTrue(control.tool_call_inflight(run, "call_1"))
                self.assertFalse(newer.done())
                self.assertFalse(write_task.done())
                self.assertEqual(handler_runs, [])
                self.assertEqual(saw_directory, [])
                self.assertFalse(middleware._call_settled["call_1"].is_set())
                self.assertNotEqual(run.tool_outcomes["call_1"].outcome, "succeeded")
                self.assertNotEqual(getattr(run.tool_outcomes["call_1"], "result", None), "This file call did not run.")
                self.assertNotEqual(middleware._outcome_attempt.get("call_1"), middleware._file_attempts.get("call_1"))
                self.assertEqual((folder / "child.txt").read_text(encoding="utf-8"), "before")
                self.assertEqual((folder / "keep.txt").read_text(encoding="utf-8"), "keep")
                release_old.set()
                stepped = await asyncio.wait_for(older, 5)
                self.assertIsInstance(stepped, ToolMessage)
                self.assertEqual(stepped.status, "error")
                self.assertEqual(stepped.tool_call_id, "call_1")
                owned = await asyncio.wait_for(newer, 5)
                written = await asyncio.wait_for(write_task, 5)
                self.assertEqual(handler_runs, ["call_1"])
                self.assertEqual(getattr(owned, "status", None), "success")
                self.assertEqual(getattr(owned, "content", None), "removed")
                self.assertEqual(run.tool_outcomes["call_1"].outcome, "succeeded")
                self.assertEqual(middleware._outcome_attempt.get("call_1"), middleware._file_attempts.get("call_1"))
                self.assertTrue(middleware._call_settled["call_1"].is_set())
                self.assertEqual(saw_directory, [False])
                self.assertEqual(getattr(written, "status", None), "success")
                self.assertEqual((project / "dir" / "child.txt").read_text(encoding="utf-8"), "after")
                self.assertFalse((folder / "keep.txt").exists())

                # The older entry is already inside the handler when the owner reserves.
                # Adopting that result must not run the delete again.
                replay_folder = project / "dir2"
                replay_folder.mkdir()
                (replay_folder / "child.txt").write_text("before", encoding="utf-8")
                (replay_folder / "keep.txt").write_text("keep", encoding="utf-8")
                saw_directory.clear()
                owner_at_reserve.clear()
                delete_again = {"name": "delete", "args": {"file_path": "dir2"}, "id": "call_3", "type": "tool_call"}
                write_again = {"name": "write_file", "args": {"file_path": "dir2/child.txt", "content": "after"}, "id": "call_4", "type": "tool_call"}
                state["messages"].append(AIMessage(content="", tool_calls=[delete_again, write_again]))
                older_ran = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call=delete_again, runtime=SimpleNamespace(state=state)), effect))
                await self._until(lambda: handler_runs.count("call_3") == 1 and control.tool_call_inflight(run, "call_3"))
                newer_ran = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call=delete_again, runtime=SimpleNamespace(state=state)), effect))
                await self._until(lambda: owner_at_reserve.is_set() and middleware._file_attempts.get("call_3", 0) >= 2)
                write_ran = asyncio.create_task(middleware.awrap_tool_call(
                    SimpleNamespace(tool_call=write_again, runtime=SimpleNamespace(state=state)), effect))
                await asyncio.sleep(0.2)
                self.assertTrue(control.tool_call_inflight(run, "call_3"))
                self.assertFalse(newer_ran.done())
                self.assertFalse(write_ran.done())
                self.assertEqual(handler_runs.count("call_3"), 1)
                self.assertEqual(saw_directory, [])
                self.assertFalse(middleware._call_settled["call_3"].is_set())
                self.assertNotEqual(getattr(run.tool_outcomes.get("call_3"), "result", None), "This file call did not run.")
                self.assertEqual((replay_folder / "child.txt").read_text(encoding="utf-8"), "before")
                self.assertEqual((replay_folder / "keep.txt").read_text(encoding="utf-8"), "keep")
                release_effect.set()
                stepped_ran = await asyncio.wait_for(older_ran, 5)
                self.assertEqual(getattr(stepped_ran, "status", None), "error")
                owned_ran = await asyncio.wait_for(newer_ran, 5)
                written_ran = await asyncio.wait_for(write_ran, 5)
                self.assertEqual(handler_runs.count("call_3"), 1)
                self.assertEqual(getattr(owned_ran, "status", None), "success")
                self.assertEqual(getattr(owned_ran, "content", None), "removed")
                self.assertEqual(run.tool_outcomes["call_3"].outcome, "succeeded")
                self.assertEqual(middleware._outcome_attempt.get("call_3"), middleware._file_attempts.get("call_3"))
                self.assertEqual(saw_directory, [False])
                self.assertEqual(getattr(written_ran, "status", None), "success")
                self.assertEqual((project / "dir2" / "child.txt").read_text(encoding="utf-8"), "after")
                self.assertFalse((replay_folder / "keep.txt").exists())
            finally:
                release_old.set()
                release_effect.set()
                for task in (older, newer, write_task, older_ran, newer_ran, write_ran):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(
                    older,
                    *([newer] if newer is not None else []),
                    *([write_task] if write_task is not None else []),
                    *([older_ran] if older_ran is not None else []),
                    *([newer_ran] if newer_ran is not None else []),
                    *([write_ran] if write_ran is not None else []),
                    return_exceptions=True)

    async def _until(self, predicate, timeout: float = 5) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.02)
        raise AssertionError("timed out waiting for a file-order waiter")


class OwnQueueTests(unittest.TestCase):
    def test_this_chats_queue_is_not_waiting_for_project(self):
        from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
        from workbench_backend.chat.service import ChatService

        now = utc_now()
        queued = [
            ChatQueueItem(id="one", task="first", created_at=now, updated_at=now, wait_reason="project_order", queue_position=9),
            ChatQueueItem(id="two", task="second", created_at=now, updated_at=now, wait_reason="project_busy"),
        ]
        conversation = ChatConversation(
            id="chat", deployment_id="model", project_path="D:/work", created_at=now, updated_at=now, queue=queued)
        viewed = ChatService._view_queue_progress(None, conversation)
        self.assertEqual([item.wait_reason for item in viewed.queue], [None, None])
        self.assertEqual([item.queue_position for item in viewed.queue], [1, 2])
        self.assertIsNone(viewed.queue[1].waiting_run_id)


class _WindowRuntime:
    def available(self):
        return True

    def command_path(self):
        return Path("winapp.exe")


class OneWindowTests(unittest.TestCase):
    def test_own_and_elevated_windows_are_hidden_and_refused(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root)).ensure()
            identities = {101: WindowIdentity(101, 10, 1000.0), 202: WindowIdentity(202, 20, 2000.0), 303: WindowIdentity(303, 30, 3000.0)}
            own: set[int] = set()
            elevated: set[int] = set()

            def runner(args, timeout):
                payload = [
                    {"hwnd": 101, "processId": 10, "processName": "workbench", "title": "Local AI Workbench", "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": False},
                    {"hwnd": 202, "processId": 20, "processName": "admin", "title": "Administrator", "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": False},
                    {"hwnd": 303, "processId": 30, "processName": "notes", "title": "Notes", "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": True},
                ]
                return CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")

            service = DesktopAutomationService(
                paths, runtime=_WindowRuntime(), identity_lookup=lambda hwnd: identities[hwnd], command_runner=runner,
                own_process_ids=lambda: set(own), elevated_check=lambda pid: pid in elevated)
            self.assertEqual(service.snapshot_grant("thread", "selected"), (DesktopAccessScope.off, None))
            self.assertEqual([item.hwnd for item in service.picker_windows()], [101, 202, 303])
            with self.assertRaises(DesktopAutomationError) as every:
                service.set_scope("thread", "all")
            self.assertEqual(every.exception.code, "desktop_invalid_arguments")

            own.add(10)
            elevated.add(20)
            self.assertEqual([item.hwnd for item in service.picker_windows()], [303])
            for hwnd in (101, 202):
                with self.assertRaises(DesktopAutomationError) as refused:
                    service.set_scope("thread", "selected", hwnd=hwnd)
                self.assertEqual(refused.exception.code, "desktop_window_refused")
            service.set_scope("thread", "selected", hwnd=303)
            self.assertEqual(service.snapshot_grant("thread", "selected")[0], DesktopAccessScope.selected)
            elevated.add(30)
            self.assertEqual(service.snapshot_grant("thread", "selected"), (DesktopAccessScope.off, None))
            with self.assertRaises(DesktopAutomationError) as changed:
                service.list_windows("thread")
            self.assertEqual(changed.exception.code, "desktop_window_refused")
            with self.assertRaises(DesktopAutomationError) as authorized:
                service._authorize_window("thread", 303)
            self.assertEqual(authorized.exception.code, "desktop_window_refused")

    def test_recorded_desktop_process_is_hidden_and_lookup_failure_refuses_the_list(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root)).ensure()
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            calls = []
            try:
                (paths.state / "desktop-process.json").write_text(json.dumps({"pid": child.pid}), encoding="utf-8")
                import psutil
                live = {psutil.Process().pid, child.pid}
                parent = psutil.Process().parent()
                if parent is not None:
                    live.add(parent.pid)
                    live.update(item.pid for item in parent.children(recursive=True))
                    live.update(item.pid for item in psutil.Process(child.pid).children(recursive=True))
                decoy_pid = 50_000
                while decoy_pid in live:
                    decoy_pid += 1
                identities = {
                    404: WindowIdentity(404, child.pid, 1.0),
                    505: WindowIdentity(505, decoy_pid, 2.0),
                    303: WindowIdentity(303, 30, 3000.0),
                }

                def runner(args, timeout):
                    calls.append(args)
                    payload = [
                        {"hwnd": 404, "processId": child.pid, "processName": "electron", "title": "Local AI Workbench", "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": False},
                        {"hwnd": 505, "processId": decoy_pid, "processName": "electron", "title": "Local AI Workbench", "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": False},
                        {"hwnd": 303, "processId": 30, "processName": "notes", "title": "Notes", "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": True},
                    ]
                    return CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")

                service = DesktopAutomationService(
                    paths, runtime=_WindowRuntime(), identity_lookup=lambda hwnd: identities[hwnd], command_runner=runner)
                listed = service.picker_windows()
                self.assertEqual([item.hwnd for item in listed], [505, 303])
                decoy = next(item for item in listed if item.hwnd == 505)
                self.assertEqual(decoy.process_name, "electron")
                self.assertEqual(decoy.title, "Local AI Workbench")
                self.assertNotIn(decoy.process_id, live)
                with self.assertRaises(DesktopAutomationError) as refused:
                    service.set_scope("thread", "selected", hwnd=404)
                self.assertEqual(refused.exception.code, "desktop_window_refused")
            finally:
                child.kill()
                child.wait(timeout=5)
            (paths.state / "desktop-process.json").write_text("{", encoding="utf-8")
            calls.clear()
            with self.assertRaises(DesktopAutomationError) as broken:
                service.picker_windows()
            self.assertEqual(broken.exception.code, "desktop_window_refused")
            self.assertEqual(calls, [])

    def test_message_sends_before_a_window_is_picked(self):
        with tempfile.TemporaryDirectory() as root:
            area = Path(root)
            app = create_app(data_root=area / "data")
            client = offline_workbench_client(app)
            try:
                app.state.manager.attach_connected(ConnectedDeploymentRequest(display_name="First", endpoint="http://127.0.0.1:9/v1"))
                app.state.harness._model_factory = lambda *_args: ScriptedChatModel([AIMessage(content="Sent before a window.")])
                deployment = app.state.manager.list_deployments()[0]
                created = client.post("/v1/chat/conversations", json={
                    "deployment_id": deployment.id, "desktop_access": "selected",
                    "input_policy": {"pinned_tools": ["desktop_list_windows"]},
                    "presented_tools": ["desktop_list_windows"]})
                self.assertEqual(created.status_code, 200, created.text)
                chat = created.json()
                with patch.object(app.state.harness.desktop_automation.runtime, "command_path", return_value=area / "winapp.exe"):
                    started = client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Say hello"})
                    self.assertEqual(started.status_code, 200, started.text)
                finished = wait_for_chat(client, chat["id"])
                self.assertEqual(finished["current_run"]["status"], "completed", finished["current_run"].get("error"))
                self.assertIsNone(finished["current_run"].get("pending_interrupt"))
                self.assertTrue(any(item["role"] == "user" for item in finished["transcript"]))
                stored = app.state.harness._runs[finished["current_run"]["id"]]
                self.assertIsNone(stored.desktop_window)
            finally:
                close_workbench_sqlite(app, client)


class HelperInheritanceTests(unittest.TestCase):
    def test_helper_cannot_turn_on_a_tool_the_parent_lacks(self):
        with tempfile.TemporaryDirectory() as root:
            window = {"hwnd": 101, "process_id": 10, "process_created_at": 1000.0}
            parent = _run(
                id="parent-run", project_path=root, thread_id="parent-chat", approval_mode="full_access",
                desktop_access="selected", desktop_window=window,
                enabled_tools=["read_file", "write_file"], presented_tools=["read_file", "write_file"])
            blocked = SetupConfiguration(presented_tools=["read_file", "execute"], requires_host_shell=True, approval_mode="full_access")
            with self.assertRaises(HarnessError) as raised:
                _narrow_presented_tools(parent, blocked, None)
            self.assertEqual(raised.exception.code, "setup_shell_required")

            inherit = SetupConfiguration(presented_tools=["read_file", "execute", "task"], desktop_access=None, approval_mode="ask")
            selected, presented, _work_mode = _narrow_presented_tools(parent, inherit, None)
            approval, desktop = _narrow_child_access(parent, inherit)
            self.assertEqual(presented, ["read_file"])
            self.assertEqual(approval, "ask")
            self.assertEqual(desktop, "selected")
            self.assertNotIn("execute", presented)
            self.assertNotIn("task", presented)

            explicit = SetupConfiguration(presented_tools=["read_file", "execute"], desktop_access="all", approval_mode="full_access")
            _selected_all, presented_all, _work = _narrow_presented_tools(parent, explicit, None)
            _approval, desktop_all = _narrow_child_access(parent, explicit)
            self.assertEqual(desktop_all, "selected")
            self.assertEqual(presented_all, ["read_file"])
            parent_off = parent.model_copy(update={"desktop_access": "off", "desktop_window": None})
            self.assertEqual(_narrow_child_access(parent_off, explicit)[1], "off")

            setup = EffectiveSetup(selected_deployment_id="model", loaded_deployment_id="model", system_prompt="Help.")
            refs = SimpleNamespace(memory_version_refs=[], skill_version_refs=[], protected_instruction_version_refs=[])
            deployment = SimpleNamespace(id="model")
            with patch("workbench_backend.agents.helper_execution.observe_context", return_value=ContextObservation()):
                child = _child_run_record(
                    parent, FrozenHelperSelection(agent_id="helper", version_id="v1", name="Helper", configuration=inherit),
                    inherit, {"messages": []}, "child-1", deployment, None, presented, selected, approval, "work", desktop,
                    setup, refs, [], [])
                broad = _child_run_record(
                    parent, FrozenHelperSelection(agent_id="helper", version_id="v1", name="Helper", configuration=explicit),
                    explicit, {"messages": []}, "child-2", deployment, None, presented_all, ["read_file", "execute"], "full_access",
                    "work", desktop_all, setup, refs, [], [])
            self.assertEqual(child.enabled_tools, ["read_file"])
            self.assertNotIn("execute", child.enabled_tools)
            self.assertIn("execute", child.denied_tools)
            self.assertEqual(child.project_path, parent.project_path)
            self.assertEqual(child.thread_id, "parent-chat")
            self.assertEqual(child.desktop_window, window)
            self.assertEqual(child.desktop_access, "selected")
            self.assertEqual(broad.desktop_access, "selected")
            self.assertEqual(broad.desktop_window, window)
            self.assertEqual(broad.project_path, parent.project_path)
            self.assertEqual(broad.enabled_tools, list(presented_all))
            self.assertIn("execute", broad.denied_tools)


if __name__ == "__main__":
    unittest.main()
