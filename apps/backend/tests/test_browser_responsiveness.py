"""Browser route and service observation with substantial persisted diagnostics."""
from __future__ import annotations

import asyncio
import gc
import json
import tempfile
import threading
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from langchain_core.tools import StructuredTool
from starlette.requests import Request

from tests.large_run_history import synthetic_large_run
from workbench_backend.agents.schemas import AgentRunStatus, ModelRequestCapture
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.browser.routes import browser_action, browser_events, control_session, start_session
from workbench_backend.browser.schemas import BrowserActionRequest, BrowserControlRequest
from workbench_backend.browser.service import BrowserSessionService, _Session
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.checkpointer import close_sqlite_checkpointer, open_sqlite_checkpointer, submit_checkpoint_task
from workbench_backend.state.store import ApplicationStore


def assert_blocking_worker() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise AssertionError("Blocking Browser observation ran on an async event loop")


class _Runtime:
    def status(self):
        assert_blocking_worker()
        return {"supported": True, "installed": True, "chrome_available": True}


class _Worker:
    def __init__(self):
        self.state = {"session_id": "owned-chrome", "tabs": [{"page_id": "page", "url": "https://example.test/"}],
            "active_page_id": "page", "revision": 1, "viewport": {"width": 1440, "height": 900}}
        self.seq = 0
        self.streaming = []
        self.attributions = []
        self.effects = 0
        self.lost = False
        self.poll_started = asyncio.Event()
        self.poll_release = None

    async def poll(self, _last_seq):
        self.poll_started.set()
        if self.poll_release is not None:
            await self.poll_release.wait()
        self.seq += 1
        return {"state": {**self.state, "lost": self.lost}, "downloads": [],
            "frame": {"session_id": self.state["session_id"], "seq": self.seq, "image": "synthetic-frame"}}

    async def get_state(self):
        return {**self.state, "lost": self.lost}

    async def drain_downloads(self):
        return []

    async def set_streaming(self, visible):
        self.streaming.append(visible)

    async def reset_input(self):
        pass

    async def set_active(self, _index):
        pass

    async def set_attribution(self, value):
        self.attributions.append(value)

    async def validate_action(self, payload):
        if payload["session_id"] != self.state["session_id"] or payload["revision"] != self.state["revision"]:
            raise HarnessError("The page changed", code="browser_state_changed", status_code=409)

    async def action(self, _payload):
        self.effects += 1
        self.state["revision"] += 1


class _Request(Request):
    def __init__(self, app, iterations=3):
        super().__init__({"type": "http", "app": app, "method": "GET", "path": "/v1/browser/sessions/thread_large/events",
            "query_string": b"", "headers": []})
        self.iterations = iterations
        self.checks = 0

    async def is_disconnected(self):
        self.checks += 1
        return self.checks > self.iterations


class BrowserLargeHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.temp.name)).ensure()
        self.store = ApplicationStore(self.paths)
        self.assets = RetainedAssetService(self.store)
        self.run = synthetic_large_run(source_surface="chat", thread_id="thread_large", status=AgentRunStatus.running,
            presented_tools=["browser_snapshot", "browser_navigate"], browser_control="agent")
        self.assertGreaterEqual(len(self.run.model_requests), 50)
        self.assertGreaterEqual(sum(len(item.model_dump_json().encode()) for item in self.run.model_requests), 10 * 1024 * 1024)
        self.run = await asyncio.to_thread(self.store.put_run, self.run)
        now = utc_now()
        self.conversation = ChatConversation(id="chat_large", deployment_id=self.run.deployment_id,
            thread_id=self.run.thread_id, current_run_id=self.run.id, run_ids=[self.run.id], created_at=now, updated_at=now)
        await asyncio.to_thread(self.store.put_conversation, self.conversation)
        self.browser = BrowserSessionService(self.paths, app_store=self.store, assets=self.assets, runtime=_Runtime())
        self.app = FastAPI()
        self.app.state.assets = self.assets
        self.app.state.app_store = self.store
        self.app.state.browser = self.browser
        self.app.state.manager = SimpleNamespace(paths=self.paths)
        fixture = self

        class Harness:
            cancel_takeover = False
            released = []

            async def request_browser_takeover(self, _thread):
                if self.cancel_takeover:
                    raise HarnessError("This run is cancelling", code="run_cancelling", status_code=409)
                fixture.run.browser_control = "user"
                fixture.run.status = AgentRunStatus.running
                await asyncio.to_thread(fixture.store.put_execution_run, fixture.run)

            async def release_browser_takeover(self, _thread, observation):
                self.released.append(observation)
                fixture.run.browser_control = "agent"
                fixture.run.status = AgentRunStatus.running
                await asyncio.to_thread(fixture.store.put_execution_run, fixture.run)

        self.harness = self.app.state.harness = Harness()
        self.session = await self.on_owner(self.install_session())

    async def on_owner(self, coroutine):
        future = await asyncio.to_thread(submit_checkpoint_task, self.paths.checkpoints_db, coroutine)
        return await asyncio.wrap_future(future)

    async def install_session(self):
        worker = _Worker()
        output = self.paths.state / "browser-captures" / self.run.thread_id
        await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
        closed = asyncio.Event()

        async def snapshot():
            return "Page URL: https://example.test/\nheading Fresh page"

        async def tabs(action: str):
            return "0: (current) https://example.test/"

        session = _Session(self.run.thread_id, {
            "browser_snapshot": StructuredTool.from_function(coroutine=snapshot, name="browser_snapshot", description="Read page"),
            "browser_tabs": StructuredTool.from_function(coroutine=tabs, name="browser_tabs", description="Read tabs"),
        }, output, asyncio.create_task(closed.wait()), closed, worker=worker, metadata=worker.state,
            control=self.browser._controls.get(self.run.thread_id, "agent"))
        self.browser._sessions[self.run.thread_id] = session
        await asyncio.to_thread(self.browser._write_marker, self.run.thread_id)
        return session

    async def asyncTearDown(self):
        await self.on_owner(self.browser.shutdown())
        await asyncio.to_thread(close_sqlite_checkpointer, self.paths.checkpoints_db)
        self.store.close()
        self.temp.cleanup()

    async def collect_events(self, iterations=3):
        response = await browser_events(_Request(self.app, iterations), self.run.thread_id)
        return [item async for item in response.body_iterator]

    async def test_concurrent_marker_writers_and_removal_serialize_on_workers(self):
        key = self.run.thread_id
        staging = self.browser._marker(key).with_suffix(".tmp")
        written, release, second_started, removal_started = (threading.Event() for _ in range(4))
        original_write = Path.write_text
        original_remove = self.browser._remove_marker
        writes = []

        def gated_write(path, *args, **kwargs):
            assert_blocking_worker()
            result = original_write(path, *args, **kwargs)
            if path == staging:
                writes.append(threading.get_ident())
                if len(writes) == 1:
                    written.set()
                    if not release.wait(5):
                        raise AssertionError("Blocked marker writer was not released")
            return result

        def second_write():
            second_started.set()
            self.browser._write_marker(key)

        def remove():
            removal_started.set()
            original_remove(key)

        with patch.object(Path, "write_text", gated_write):
            first = asyncio.create_task(asyncio.to_thread(self.browser._write_marker, key))
            second = None
            try:
                self.assertTrue(await asyncio.to_thread(written.wait, 3))
                second = asyncio.create_task(asyncio.to_thread(second_write))
                self.assertTrue(await asyncio.to_thread(second_started.wait, 3))
                self.assertEqual(len(writes), 1, "Second writer cannot touch the same staging file")
            finally:
                release.set()
                await asyncio.gather(first, *([second] if second else []))
            self.assertEqual(len(writes), 2)
            self.assertEqual(json.loads(self.browser._marker(key).read_text())["thread_id"], key)
            written.clear()
            release.clear()
            writes.clear()
            writer = asyncio.create_task(asyncio.to_thread(self.browser._write_marker, key))
            removal = None
            try:
                self.assertTrue(await asyncio.to_thread(written.wait, 3))
                removal = asyncio.create_task(asyncio.to_thread(remove))
                self.assertTrue(await asyncio.to_thread(removal_started.wait, 3))
                self.assertFalse(removal.done(), "Close/reset removal must wait for the active marker write")
            finally:
                release.set()
                await asyncio.gather(writer, *([removal] if removal else []))
        self.assertFalse(self.browser._marker(key).exists())
        self.assertFalse(staging.exists())

    async def test_duplicate_loss_and_caller_cancellation_finish_before_reset_and_ignore_replacement(self):
        key = self.run.thread_id
        old_session = self.session
        entered, release = threading.Event(), threading.Event()
        original = self.browser._write_lost_marker
        writes = []

        def blocked_write(session):
            assert_blocking_worker()
            writes.append(session)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Blocked loss writer was not released")
            original(session)

        async def exercise():
            first = asyncio.create_task(self.browser._mark_lost(old_session))
            second = reset = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                self.assertNotIn(key, self.browser._sessions)
                second = asyncio.create_task(self.browser._mark_lost(old_session))
                reset = asyncio.create_task(self.browser.reset(key))
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)
                self.assertFalse(old_session.loss_task.cancelled())
                self.assertFalse(reset.done(), "Reset must wait for loss file work and the original worker stop")
                self.assertFalse(old_session.close_event.is_set())
            finally:
                release.set()
                await asyncio.gather(first, return_exceptions=True)
                await asyncio.wait_for(asyncio.gather(*([second] if second else []),
                    *([reset] if reset else [])), 3)
            self.assertEqual(len(writes), 1, "Overlapping loss reports cannot repeat cleanup")
            self.assertTrue(old_session.owner_task.done())
            self.assertTrue(old_session.loss_task.done())

        with patch.object(self.browser, "_write_lost_marker", side_effect=blocked_write):
            await self.on_owner(exercise())
        self.assertFalse(self.browser._marker(key).exists())
        await asyncio.to_thread(self.browser._ensure_marker, old_session)
        self.assertFalse(self.browser._marker(key).exists(), "A stale observer cannot resurrect Reset's lost marker")
        self.session = await self.on_owner(self.install_session())
        marker = self.browser._marker(key).read_bytes()
        await self.on_owner(self.browser._mark_lost(old_session))
        await asyncio.to_thread(self.browser._ensure_marker, old_session)
        self.assertIs(self.browser._sessions[key], self.session)
        self.assertFalse(self.session.close_event.is_set())
        self.assertEqual(self.browser._marker(key).read_bytes(), marker)
        self.assertEqual(self.session.worker.effects, 0)

    async def test_delayed_observer_marker_ensure_cannot_resurrect_after_reset(self):
        key = self.run.thread_id
        old_session = self.session
        locked, release, ensure_started, removal_started = (threading.Event() for _ in range(4))
        original_remove = self.browser._remove_marker

        def hold_marker_lock():
            with self.browser._marker_lock:
                locked.set()
                if not release.wait(5):
                    raise AssertionError("Marker lock holder was not released")

        def ensure():
            assert_blocking_worker()
            ensure_started.set()
            self.browser._ensure_marker(old_session)

        def remove(thread_id):
            assert_blocking_worker()
            removal_started.set()
            original_remove(thread_id)

        holder = asyncio.create_task(asyncio.to_thread(hold_marker_lock))
        observer = reset = None
        with patch.object(self.browser, "_remove_marker", side_effect=remove):
            try:
                self.assertTrue(await asyncio.to_thread(locked.wait, 3))
                observer = asyncio.create_task(asyncio.to_thread(ensure))
                self.assertTrue(await asyncio.to_thread(ensure_started.wait, 3))
                reset = asyncio.create_task(self.on_owner(self.browser.reset(key)))
                self.assertTrue(await asyncio.to_thread(removal_started.wait, 3))
                self.assertTrue(old_session.owner_task.done())
                self.assertNotIn(key, self.browser._sessions)
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(holder, *([observer] if observer else []),
                    *([reset] if reset else [])), 3)
        self.assertFalse(self.browser._marker(key).exists())
        self.assertEqual((await asyncio.to_thread(self.browser.status, key))["state"], "closed")

    async def test_live_view_error_is_visible_without_losing_session_and_clears_on_recovery(self):
        self.session.worker.state["error"] = "The live Browser view is unavailable."
        result = await self.on_owner(self.browser.poll_view(self.run.thread_id))
        self.assertEqual(result["state"]["error"], "The live Browser view is unavailable.")
        self.assertEqual(result["state"]["state"], "active")
        self.assertIs(self.browser._sessions[self.run.thread_id], self.session)
        self.session.worker.state["error"] = None
        recovered = await self.on_owner(self.browser.poll_view(self.run.thread_id))
        self.assertIsNone(recovered["state"]["error"])
        self.assertEqual(recovered["state"]["state"], "active")

    async def test_actual_event_route_reads_one_owner_per_iteration_without_diagnostics_on_either_loop(self):
        reads = []
        original = self.store.get_run_browser

        def operational_read(run_id):
            assert_blocking_worker()
            reads.append(threading.current_thread().name)
            return original(run_id)

        with patch.object(self.store, "get_run_browser", side_effect=operational_read), \
            patch.object(self.store, "get_run", side_effect=AssertionError("Diagnostic run hydration")), \
            patch.object(self.store, "normalize_run_diagnostics", side_effect=AssertionError("Diagnostic normalization")), \
            patch.object(ModelRequestCapture, "model_validate", side_effect=AssertionError("Capture hydration")):
            for _ in range(10):
                state = await asyncio.to_thread(self.browser.status, self.run.thread_id)
                self.assertEqual(state["control"], "agent")
            before = len(reads)
            events = await self.collect_events(4)
            self.assertEqual(len(reads) - before, 4)
        self.assertEqual(sum(item.startswith("event: state") for item in events), 1)
        self.assertEqual(sum(item.startswith("event: frame") for item in events), 4)
        self.assertEqual(self.browser._controls[self.run.thread_id], "agent")
        self.assertEqual(self.browser._control_run_ids[self.run.thread_id], self.run.id)
        self.assertEqual(self.session.viewers, 0)
        self.assertEqual(self.session.worker.streaming, [True, False])

    async def test_takeover_return_handoff_reconnect_and_cancellation_preserve_authority_and_effects(self):
        request = _Request(self.app)
        taken = await control_session(request, self.run.thread_id, BrowserControlRequest(action="take"))
        self.assertEqual(taken["control"], "user")
        payload = BrowserActionRequest.model_validate({"session_id": "owned-chrome", "page_id": "page", "revision": 1,
            "action": {"type": "pointer", "event": "click", "x": 20, "y": 30}})
        manual_owner = await asyncio.to_thread(self.browser.resolve_owner, self.run.thread_id)
        await asyncio.to_thread(self.browser.status, self.run.thread_id)
        with patch.object(self.browser, "resolve_owner", return_value=manual_owner):
            await browser_action(request, self.run.thread_id, payload)
        self.assertEqual(self.session.worker.attributions[-1]["run_id"], self.run.id)
        await self.collect_events(2)
        await self.collect_events(2)
        self.assertEqual(self.session.worker.effects, 1, "Viewing or reconnecting cannot replay a manual effect")
        stale_user_owner = await asyncio.to_thread(self.browser.resolve_owner, self.run.thread_id)
        returned = await control_session(request, self.run.thread_id, BrowserControlRequest(action="return"))
        self.assertEqual(returned["control"], "agent")
        self.assertEqual((await asyncio.to_thread(self.browser.status, self.run.thread_id, owner=stale_user_owner))["control"], "agent",
            "A delayed user-owned poll cannot undo Return, including identical persisted timestamps")
        self.assertIn("Fresh page", self.harness.released[-1])
        await control_session(request, self.run.thread_id, BrowserControlRequest(action="take"))
        stale_owner = await asyncio.to_thread(self.browser.resolve_owner, self.run.thread_id)
        previous = self.run.id
        self.run = self.run.model_copy(update={"id": "run_next", "browser_control": "agent", "status": AgentRunStatus.running})
        await asyncio.to_thread(self.store.put_run, self.run)
        self.conversation.current_run_id = self.run.id
        self.conversation.run_ids.append(self.run.id)
        self.conversation.updated_at = utc_now()
        await asyncio.to_thread(self.store.put_conversation, self.conversation)
        events = await self.collect_events(2)
        state = json.loads(next(item.split("data: ", 1)[1] for item in events if item.startswith("event: state")))
        self.assertEqual(state["control"], "agent")
        stale_state = await asyncio.to_thread(self.browser.status, self.run.thread_id, owner=stale_owner)
        self.assertEqual(stale_state["control"], "agent", "An older poll cannot restore the previous run's manual authority")
        self.assertEqual(self.browser._control_run_ids[self.run.thread_id], self.run.id)
        with self.assertRaises(HarnessError) as denied:
            await browser_action(request, self.run.thread_id, payload)
        self.assertEqual(denied.exception.code, "browser_control_required")
        self.harness.cancel_takeover = True
        with self.assertRaises(HarnessError) as cancelled:
            await control_session(request, self.run.thread_id, BrowserControlRequest(action="take"))
        self.assertEqual(cancelled.exception.code, "run_cancelling")
        self.assertEqual((await asyncio.to_thread(self.browser.status, self.run.thread_id))["control"], "agent")
        self.assertEqual(self.session.worker.effects, 1)
        self.assertEqual((await asyncio.to_thread(self.store.get_run, previous)).model_requests, [])
        self.harness.cancel_takeover = False
        await control_session(request, self.run.thread_id, BrowserControlRequest(action="take"))
        self.run.browser_control = "agent"
        self.run.status = AgentRunStatus.cancelled
        self.run.finished_at = utc_now()
        await asyncio.to_thread(self.store.put_execution_run, self.run)
        self.assertEqual((await asyncio.to_thread(self.browser.status, self.run.thread_id))["control"], "agent")
        self.assertEqual((await asyncio.to_thread(self.store.get_run, self.run.id)).model_requests, [])

    async def test_restart_worker_loss_and_cancelled_view_never_repeat_effects(self):
        await control_session(_Request(self.app), self.run.thread_id, BrowserControlRequest(action="take"))
        restarted = BrowserSessionService(self.paths, app_store=self.store, assets=self.assets, runtime=_Runtime())
        self.assertEqual((await asyncio.to_thread(restarted.status, self.run.thread_id))["control"], "user")
        self.assertEqual((await asyncio.to_thread(restarted.status, self.run.thread_id))["state"], "lost")
        for control in ("taking_control", "agent", "user"):
            self.run.browser_control = control
            await asyncio.to_thread(self.store.put_execution_run, self.run)
            self.assertEqual((await asyncio.to_thread(restarted.status, self.run.thread_id))["control"], control)
        self.app.state.browser = restarted
        events = await self.collect_events(2)
        self.assertIn('"state": "lost"', events[0])
        with self.assertRaises(HarnessError) as refused:
            await start_session(_Request(self.app), self.run.thread_id)
        self.assertEqual(refused.exception.code, "browser_session_lost")
        self.app.state.browser = self.browser
        self.session.worker.lost = True
        events = await self.collect_events(2)
        self.assertIn('"state": "lost"', events[0])
        self.assertEqual(self.session.worker.effects, 0)
        # Cancelling a view settles its subscription without changing authority.
        await self.on_owner(self.browser.reset(self.run.thread_id))
        self.session = await self.on_owner(self.install_session())
        response = await browser_events(_Request(self.app, 5), self.run.thread_id)
        await anext(response.body_iterator)
        await anext(response.body_iterator)

        async def block_poll():
            self.session.worker.poll_started = asyncio.Event()
            self.session.worker.poll_release = asyncio.Event()

        await self.on_owner(block_poll())
        pending = asyncio.create_task(anext(response.body_iterator))
        try:
            await asyncio.wait_for(self.on_owner(self.session.worker.poll_started.wait()), 3)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        finally:
            async def release_poll():
                self.session.worker.poll_release.set()
            await self.on_owner(release_poll())
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            await response.body_iterator.aclose()
        self.assertEqual(self.session.viewers, 0)
        self.assertEqual(self.session.worker.streaming, [True, False])
        self.assertEqual(self.session.worker.effects, 0)
        self.assertIs(self.browser._sessions[self.run.thread_id], self.session)
        self.assertEqual(self.session.control, "user", "Cancelling an observation must not release browser authority")

    async def test_actual_asgi_disconnect_releases_subscriber_in_cancelled_anyio_scope(self):
        request = _Request(self.app, 100)
        response = await browser_events(request, self.run.thread_id)
        disconnected, frame_sent = asyncio.Event(), asyncio.Event()

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and b"event: frame" in message.get("body", b""):
                frame_sent.set()

        async def block_next_poll():
            self.session.worker.poll_started = asyncio.Event()
            self.session.worker.poll_release = asyncio.Event()

        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always", RuntimeWarning)
            streaming = asyncio.create_task(response(request.scope, receive, send))
            try:
                await asyncio.wait_for(frame_sent.wait(), 3)
                self.assertEqual(self.session.viewers, 1)
                await self.on_owner(block_next_poll())
                await asyncio.wait_for(self.on_owner(self.session.worker.poll_started.wait()), 3)
                disconnected.set()
                await asyncio.wait_for(streaming, 3)
            finally:
                disconnected.set()
                async def release():
                    if self.session.worker.poll_release:
                        self.session.worker.poll_release.set()
                await self.on_owner(release())
                streaming.cancel()
                await asyncio.gather(streaming, return_exceptions=True)
            await asyncio.to_thread(gc.collect)
        self.assertFalse([item for item in emitted if "never awaited" in str(item.message)])
        self.assertEqual(self.session.viewers, 0)
        self.assertEqual(self.session.view_subscriptions, set())
        self.assertEqual(self.session.worker.streaming, [True, False])
        self.assertEqual(self.session.worker.effects, 0)
        self.assertIs(self.browser._sessions[self.run.thread_id], self.session)

    async def test_disconnect_before_owner_submission_creates_no_coroutine_or_other_viewer_release(self):
        await self.on_owner(self.browser.view_subscription(self.run.thread_id, True, subscription_id="existing-viewer"))
        request = _Request(self.app, 100)
        response = await browser_events(request, self.run.thread_id)
        disconnected = asyncio.Event()
        entered, cleanup_entered, release, finished = (threading.Event() for _ in range(4))
        counter_lock = threading.Lock()
        calls = 0

        def gated_open(path):
            nonlocal calls
            assert_blocking_worker()
            with counter_lock:
                calls += 1
                first = calls == 1
            if first:
                entered.set()
                try:
                    if not release.wait(5):
                        raise AssertionError("The blocked owner initializer was not released")
                    return open_sqlite_checkpointer(path)
                finally:
                    finished.set()
            cleanup_entered.set()
            return open_sqlite_checkpointer(path)

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(_message):
            pass

        with warnings.catch_warnings(record=True) as emitted, \
            patch("workbench_backend.browser.routes.open_sqlite_checkpointer", side_effect=gated_open), \
            patch.object(self.browser, "poll_view", wraps=self.browser.poll_view) as poll:
            warnings.simplefilter("always", RuntimeWarning)
            streaming = asyncio.create_task(response(request.scope, receive, send))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                disconnected.set()
                self.assertTrue(await asyncio.to_thread(cleanup_entered.wait, 3), "Disconnect cleanup must escape AnyIO cancellation")
                await asyncio.wait_for(streaming, 3)
                poll.assert_not_called()
                self.assertEqual(self.session.viewers, 1, "An unregistered connection cannot release a different viewer")
            finally:
                release.set()
                self.assertTrue(await asyncio.to_thread(finished.wait, 3))
                streaming.cancel()
                await asyncio.gather(streaming, return_exceptions=True)
            await asyncio.to_thread(gc.collect)
        self.assertFalse([item for item in emitted if "never awaited" in str(item.message)])
        self.assertEqual(self.session.view_subscriptions, {"existing-viewer"})
        await self.on_owner(self.browser.view_subscription(self.run.thread_id, False, subscription_id="existing-viewer"))
        self.assertEqual(self.session.viewers, 0)
