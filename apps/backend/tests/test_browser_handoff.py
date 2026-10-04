"""Whole-task browser ownership uses real native graph pause and continuation."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

from langchain.agents import create_agent
from langchain.agents.middleware import ExtendedModelResponse, ModelRequest, ModelResponse
from deepagents.backends import FilesystemBackend
from deepagents.middleware.summarization import SUMMARIZATION_EVENT_KEY, SummarizationMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphInterrupt

from tests import test_harness as harness_fixture
from tests import test_agent_capabilities as helper_fixture
from tests.scripted_model import (ScriptedChatModel, RECEIVED_PROMPTS,
    reset_received_prompts, set_generate_hold, wait_for_generate_hold)
from tests.support import wait_for_run
from workbench_backend.agents.execution_policy import ExecutionControl
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun, InterruptDecisionRequest
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.request_projection import TOOL_CONTEXT_MARKER, project_context_payload
from workbench_backend.state.checkpointer import submit_checkpoint_task


def fixture_run(**values):
    now = utc_now()
    return AgentRun(id="root", deployment_id="model", task="task", thread_id="chat",
        enabled_tools=["echo"], presented_tools=["echo"], created_at=now, updated_at=now, **values)


class BrowserDrainTests(unittest.TestCase):
    def test_drain_tracks_child_model_and_tool_but_excludes_passive_delegation(self):
        root = fixture_run()
        child = root.model_copy(deep=True, update={"id": "child"})
        control = ExecutionControl(root)
        model_entered, tool_entered = threading.Event(), threading.Event()
        model_release, tool_release, task_release = threading.Event(), threading.Event(), threading.Event()

        def model():
            with control.model_dispatch(child):
                model_entered.set()
                self.assertTrue(model_release.wait(5))

        def tool():
            with control.tool_dispatch(child, "effect", "echo"):
                tool_entered.set()
                self.assertTrue(tool_release.wait(5))

        def passive():
            with control.tool_dispatch(root, "delegation", "task"):
                self.assertTrue(task_release.wait(5))

        with ThreadPoolExecutor(max_workers=4) as pool:
            pending_task = pool.submit(passive)
            pending_model, pending_tool = pool.submit(model), pool.submit(tool)
            try:
                self.assertTrue(model_entered.wait(5))
                self.assertTrue(tool_entered.wait(5))
                control.take_browser_control()
                settled = pool.submit(control.wait_for_browser_settle)
                self.assertEqual(root.browser_control, "taking_control")
                model_release.set()
                pending_model.result(5)
                self.assertFalse(settled.done(), "Active child tool must still own the drain")
                tool_release.set()
                pending_tool.result(5)
                settled.result(5)
                self.assertEqual(root.browser_control, "user")
                self.assertFalse(pending_task.done(), "Delegation wait must not deadlock takeover")
            finally:
                model_release.set()
                tool_release.set()
                task_release.set()
            pending_task.result(5)

    def test_stale_browser_mutation_is_not_repeated_but_fresh_proposal_can_execute(self):
        root = fixture_run()
        root.enabled_tools = root.presented_tools = ["browser_click"]
        control = ExecutionControl(root)
        control.observe_model_response(root, SimpleNamespace(result=[
            AIMessage(content="", tool_calls=[{"id": "before", "name": "browser_click", "args": {}}])]), 0)
        control.take_browser_control()
        control.wait_for_browser_settle()
        control.return_browser_control("Fresh structure")
        middleware = WorkbenchHarnessMiddleware(root, execution_control=control)
        effects = []
        def invoke(ident):
            request = SimpleNamespace(tool_call={"id": ident, "name": "browser_click", "args": {}})
            return middleware.wrap_tool_call(request,
                lambda _: effects.append(ident) or ToolMessage(content="clicked", name="browser_click", tool_call_id=ident))
        self.assertEqual(invoke("before").status, "error")
        self.assertEqual(root.tool_outcomes["before"].outcome, "not_dispatched")
        invoke("after")
        self.assertEqual(effects, ["after"])
        with self.assertRaises(Exception) as caught:
            invoke("after")
        self.assertEqual(caught.exception.code, "duplicate_tool_call")


class BrowserObservationTests(unittest.TestCase):
    def request(self, messages, state=None):
        return ModelRequest(model=ScriptedChatModel([]), tools=[], messages=messages,
            state=state if state is not None else {"messages": messages}, runtime=None)

    def test_failed_cancelled_or_interrupted_dispatch_does_not_consume_marked_observation(self):
        root = fixture_run(browser_observation="HANDOFF-A", browser_revision=1)
        workbench = WorkbenchHarnessMiddleware(root)
        messages = [HumanMessage(content="Accepted task", id="task"),
            AIMessage(content="", additional_kwargs={"reasoning_content": "CURRENT-CYCLE"},
                tool_calls=[{"name": "echo", "args": {"text": "ok"}, "id": "echo"}]),
            ToolMessage(content="ok", name="echo", tool_call_id="echo")]
        request = self.request(messages)
        sent = []
        for error in (RuntimeError("failed"), asyncio.CancelledError(), GraphInterrupt(())):
            def fail(filtered):
                sent.append(filtered)
                raise error
            with self.assertRaises(type(error)):
                workbench.wrap_model_call(request, fail)
        self.assertEqual(len(messages), 3)
        self.assertEqual(root.browser_observation, "HANDOFF-A")
        response = workbench.wrap_model_call(request,
            lambda filtered: sent.append(filtered) or ModelResponse(result=[AIMessage(content="Done")]))
        self.assertIsInstance(response, ExtendedModelResponse)
        observation = response.model_response.result[0]
        self.assertTrue(observation.additional_kwargs[TOOL_CONTEXT_MARKER])
        self.assertTrue(observation.content.startswith("<tool_response>\n"))
        self.assertTrue(all(item.messages[-1].model_dump() == observation.model_dump() for item in sent))
        projected = project_context_payload(sent[-1].messages, reasoning_scope="current_turn")
        self.assertEqual(projected["messages"][1]["reasoning_content"], "CURRENT-CYCLE")
        self.assertEqual(workbench.browser_messages_for_count(messages)[-1].model_dump(), observation.model_dump())
        state = {"messages": [*messages, *response.model_response.result], **response.command.update}
        reconstructed = WorkbenchHarnessMiddleware(root)
        again = reconstructed.wrap_model_call(self.request(state["messages"], state),
            lambda filtered: sent.append(filtered) or ModelResponse(result=[AIMessage(content="Continued")]))
        self.assertIsInstance(again, ModelResponse)
        self.assertEqual(sum(bool(item.additional_kwargs.get("workbench_browser_observation"))
            for item in sent[-1].messages), 1)

    def test_async_cancellation_keeps_the_same_pending_observation(self):
        async def exercise():
            root = fixture_run(browser_observation="ASYNC-A", browser_revision=2)
            workbench = WorkbenchHarnessMiddleware(root)
            request = self.request([HumanMessage(content="Task", id="task")])
            sent = []
            async def fail(filtered):
                sent.append(filtered.messages[-1])
                raise asyncio.CancelledError()
            with self.assertRaises(asyncio.CancelledError):
                await workbench.awrap_model_call(request, fail)
            async def succeed(filtered):
                sent.append(filtered.messages[-1])
                return ModelResponse(result=[AIMessage(content="Done")])
            response = await workbench.awrap_model_call(request, succeed)
            self.assertIsInstance(response, ExtendedModelResponse)
            self.assertEqual(sent[0].model_dump(), sent[1].model_dump())
            self.assertEqual(root.browser_observation, "ASYNC-A")
        asyncio.run(exercise())

    def test_pending_handoff_is_historical_when_resumed_browser_result_is_newer(self):
        root = fixture_run(browser_observation="PAGE-A", browser_revision=1)
        root.enabled_tools = root.presented_tools = ["browser_snapshot"]
        workbench = WorkbenchHarnessMiddleware(root)
        tool_request = SimpleNamespace(tool_call={"id": "newer-read", "name": "browser_snapshot", "args": {}})
        result = workbench.wrap_tool_call(tool_request,
            lambda _: ToolMessage(content="PAGE-B", name="browser_snapshot", tool_call_id="newer-read"))
        messages = [HumanMessage(content="Task"),
            AIMessage(content="", tool_calls=[tool_request.tool_call]), result]
        request = self.request(messages)
        workbench.prepare_context_request(request)
        counted = workbench.browser_messages_for_count(messages)
        sent = workbench._with_browser_observation(request).messages
        self.assertEqual(counted[-1].model_dump(), sent[-1].model_dump())
        self.assertIn("historical snapshot", sent[-1].content)
        self.assertIn("newer-read", sent[-1].content)
        self.assertIn("they supersede this snapshot", sent[-1].content)
        self.assertNotIn("Current browser state was refreshed", sent[-1].content)
        # Genuine later lifecycle changes must survive older browser evidence.
        workbench.execution_control.invalidate_browser_state("PAGE-A")
        fresh = workbench._with_browser_observation(request).messages[-1]
        self.assertNotEqual(fresh.id, sent[-1].id)
        self.assertNotIn("historical snapshot", fresh.content)
        self.assertNotIn("newer-read", fresh.content)

    def test_failed_browser_result_and_helper_evidence_do_not_supersede_handoff(self):
        root = fixture_run(browser_observation="PAGE-A", browser_revision=1)
        root.enabled_tools = root.presented_tools = ["browser_snapshot"]
        workbench = WorkbenchHarnessMiddleware(root)
        failed = workbench.wrap_tool_call(SimpleNamespace(tool_call={
            "id": "failed-read", "name": "browser_snapshot", "args": {}}),
            lambda _: ToolMessage(content="No live page", name="browser_snapshot",
                tool_call_id="failed-read", status="error"))
        child = root.model_copy(deep=True, update={"id": "helper", "tool_outcomes": {}})
        helper = WorkbenchHarnessMiddleware(child, execution_control=workbench.execution_control)
        child_result = helper.wrap_tool_call(SimpleNamespace(tool_call={
            "id": "child-read", "name": "browser_snapshot", "args": {}}),
            lambda _: ToolMessage(content="Helper page", name="browser_snapshot", tool_call_id="child-read"))
        messages = [HumanMessage(content="Task"), failed, child_result]
        sent = workbench._with_browser_observation(self.request(messages)).messages[-1]
        self.assertNotIn("historical snapshot", sent.content)
        self.assertNotIn("failed-read", sent.content)
        self.assertNotIn("child-read", sent.content)

    def test_new_lifecycle_change_during_generation_is_not_acknowledged_with_older_snapshot(self):
        root = fixture_run(browser_observation="PAGE-A", browser_revision=1)
        workbench = WorkbenchHarnessMiddleware(root)
        request = self.request([HumanMessage(content="Task", id="task")])
        sent = []
        def answer(filtered):
            sent.append(filtered.messages[-1])
            workbench.execution_control.invalidate_browser_state("PAGE-C")
            return ModelResponse(result=[helper_fixture.call("browser_snapshot", {}, "proposed-read")])
        response = workbench.wrap_model_call(request, answer)
        receipt = response.command.update["_browser_observation_seen"]
        self.assertEqual(receipt, sent[0].additional_kwargs["workbench_browser_observation"])
        self.assertEqual(root.browser_tool_proposals["root:proposed-read"], 1)
        state = {"messages": [*request.messages, *response.model_response.result], **response.command.update}
        next_request = self.request(state["messages"], state)
        next_observation = workbench._with_browser_observation(next_request).messages[-1]
        self.assertIn("PAGE-C", next_observation.content)
        self.assertNotIn("PAGE-A", next_observation.content)
        self.assertNotEqual(next_observation.additional_kwargs["workbench_browser_observation"], receipt)

    def test_native_checkpoint_survives_reconstruction_compaction_and_identical_handoffs(self):
        root = fixture_run()
        root.enabled_tools = root.presented_tools = ["browser_snapshot", "echo"]
        control = ExecutionControl(root)
        received = []
        class HandoffModel(ScriptedChatModel):
            def _generate(self, messages, *args, **kwargs):
                received.append(list(messages))
                response = super()._generate(messages, *args, **kwargs)
                if len(received) == 1:
                    control.invalidate_browser_state("PAGE-A")
                return response
        value = HandoffModel([
            helper_fixture.call("browser_snapshot", {}, "read-b"),
            helper_fixture.call("echo", {"text": "ok"}, "echo"), AIMessage(content="Done")])
        snapshot = StructuredTool.from_function(name="browser_snapshot", description="Read the live page",
            func=lambda: "PAGE-B")
        echo = StructuredTool.from_function(name="echo", description="Echo text", func=lambda text: text)
        saver, config = InMemorySaver(), {"configurable": {"thread_id": "observation-checkpoint"}}
        workbench = WorkbenchHarnessMiddleware(root, execution_control=control)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        history_backend = FilesystemBackend(root_dir=temporary.name, virtual_mode=True)
        def summarizer():
            return SummarizationMiddleware(model=ScriptedChatModel([AIMessage(content="Retained browser summary")]),
                backend=history_backend, trigger=("messages", 6), keep=("messages", 1))
        graph = create_agent(value, tools=[snapshot, echo], middleware=[summarizer(), workbench], checkpointer=saver)
        graph.invoke({"messages": [HumanMessage(content="Accepted task", id="task")]}, config)
        state = graph.get_state(config).values
        observations = [item for item in state["messages"] if item.additional_kwargs.get("workbench_browser_observation")]
        self.assertEqual(len(observations), 1)
        first = observations[0]
        self.assertEqual(state["_browser_observation_seen"], first.additional_kwargs["workbench_browser_observation"])
        self.assertIn("historical snapshot", first.content)
        self.assertIn("read-b", first.content)
        self.assertEqual([sum(bool(item.additional_kwargs.get("workbench_browser_observation"))
            for item in frame) for frame in received], [0, 1, 0])
        self.assertEqual(received[1][-1].model_dump(), first.model_dump())
        self.assertLess(state["messages"].index(first), next(index for index, item in enumerate(state["messages"])
            if isinstance(item, AIMessage) and any(call["id"] == "echo" for call in item.tool_calls)))
        # Actual upstream compaction covers the delivered observation in raw
        # canonical history. Its native receipt prevents reinjection even
        # though the effective model context no longer includes that message.
        self.assertGreater(state[SUMMARIZATION_EVENT_KEY]["cutoff_index"], state["messages"].index(first))
        self.assertIsNotNone(state[SUMMARIZATION_EVENT_KEY]["file_path"])
        history = history_backend.download_files([state[SUMMARIZATION_EVENT_KEY]["file_path"]])[0]
        self.assertIsNone(history.error)
        self.assertIn("PAGE-A", history.content.decode("utf-8"))
        effective = SummarizationMiddleware._apply_event_to_messages(state["messages"], state[SUMMARIZATION_EVENT_KEY])
        self.assertFalse(any(item.additional_kwargs.get("workbench_browser_observation") for item in effective))
        continued = []
        class ContinuedModel(ScriptedChatModel):
            def _generate(self, messages, *args, **kwargs):
                continued.append(list(messages))
                return super()._generate(messages, *args, **kwargs)
        rebuilt = create_agent(ContinuedModel([AIMessage(content="Continued"), AIMessage(content="Again")]), tools=[snapshot, echo],
            middleware=[summarizer(), WorkbenchHarnessMiddleware(root, execution_control=control)], checkpointer=saver)
        rebuilt.invoke({"messages": [HumanMessage(content="Continue", id="continue")]}, config)
        self.assertFalse(any(item.additional_kwargs.get("workbench_browser_observation") for item in continued[0]))
        self.assertEqual(rebuilt.get_state(config).values["_browser_observation_seen"], state["_browser_observation_seen"])
        self.assertEqual(sum(bool(item.additional_kwargs.get("workbench_browser_observation"))
            for item in rebuilt.get_state(config).values["messages"]), 1)
        control.take_browser_control()
        control.wait_for_browser_settle()
        control.return_browser_control("PAGE-A")
        rebuilt.invoke({"messages": [HumanMessage(content="Continue again", id="again")]}, config)
        second = next(item for item in reversed(rebuilt.get_state(config).values["messages"])
            if item.additional_kwargs.get("workbench_browser_observation"))
        self.assertNotEqual(second.id, first.id)
        # A fresh accepted run on the same native thread owns its own receipt.
        fresh_root = root.model_copy(deep=True, update={"id": "fresh-run"})
        fresh = create_agent(ScriptedChatModel([AIMessage(content="New run")]), tools=[snapshot, echo],
            middleware=[summarizer(), WorkbenchHarnessMiddleware(fresh_root)], checkpointer=saver)
        fresh.invoke({"messages": [HumanMessage(content="New task", id="new-task")]}, config)
        self.assertEqual(sum(bool(item.additional_kwargs.get("workbench_browser_observation"))
            for item in fresh.get_state(config).values["messages"]), 3)


class BrowserNativeHandoffTests(unittest.TestCase):
    setUp = harness_fixture.HarnessApiTests.setUp
    tearDown = harness_fixture.HarnessApiTests.tearDown
    _start = harness_fixture.HarnessApiTests._start
    _wait_for_pending_interrupt = harness_fixture.HarnessApiTests._wait_for_pending_interrupt

    def submit(self, coroutine):
        return submit_checkpoint_task(self.manager.paths.checkpoints_db, coroutine)

    def wait_for_control(self, run_id, expected):
        harness = self.app.state.harness
        deadline = time.monotonic() + 5
        with harness._updates:
            while harness._runs[run_id].browser_control != expected:
                left = deadline - time.monotonic()
                self.assertGreater(left, 0, harness._runs[run_id])
                harness._updates.wait(timeout=left)

    def test_takeover_during_generation_pauses_native_graph_then_continues_once(self):
        reset_received_prompts()
        release = threading.Event()
        set_generate_hold(release)
        harness = self.app.state.harness
        try:
            started = self._start(thread_id="browser-model", presented_tools=["echo"])
            wait_for_generate_hold(timeout=5)
            takeover = self.submit(harness.request_browser_takeover("browser-model"))
            self.wait_for_control(started["id"], "taking_control")
            self.assertFalse(takeover.done(), "Manual input cannot start during model generation")
            release.set()
            takeover.result(5)
            paused = self._wait_for_pending_interrupt(started["id"])
            self.assertEqual(paused["pending_interrupt"]["kind"], "browser_control")
            self.assertEqual(paused["dispatched_tool_calls"], 0, "Proposed tools must not dispatch during takeover")
            with self.assertRaises(Exception) as caught:
                harness.resume_interrupt(started["id"], InterruptDecisionRequest(decisions=[]))
            self.assertEqual(caught.exception.code, "browser_control_active")
            self.submit(harness.release_browser_takeover("browser-model", "Current page marker FRESH-PAGE-73")).result(5)
            final = wait_for_run(self.client, started["id"])
            self.assertEqual(final["status"], "completed", final.get("error"))
            self.assertEqual([item["name"] for item in final["tool_invocations"]], ["echo"])
            self.assertTrue(any("FRESH-PAGE-73" in prompt for prompt in RECEIVED_PROMPTS))
        finally:
            release.set()
            set_generate_hold(None)

    def test_final_answer_already_generating_can_settle_without_an_extra_continuation(self):
        release = threading.Event()
        set_generate_hold(release)
        self.scripted = ScriptedChatModel([AIMessage(content="The completed answer")])
        harness = self.app.state.harness
        try:
            started = self._start(thread_id="browser-final", presented_tools=[])
            wait_for_generate_hold(timeout=5)
            takeover = self.submit(harness.request_browser_takeover("browser-final"))
            self.wait_for_control(started["id"], "taking_control")
            release.set()
            takeover.result(5)
            final = wait_for_run(self.client, started["id"])
            self.assertEqual(final["status"], "completed", final.get("error"))
            self.assertEqual(final["dispatched_tool_calls"], 0)
            self.assertIsNone(final["pending_interrupt"])
            finished_at = final["finished_at"]
            self.submit(harness.release_browser_takeover("browser-final", "Fresh idle page")).result(5)
            self.assertEqual(harness.get_run(started["id"]).finished_at, finished_at)
        finally:
            release.set()
            set_generate_hold(None)

    def test_existing_approval_is_preserved_and_its_answer_cannot_dispatch_while_user_controls(self):
        reset_received_prompts()
        self.scripted = ScriptedChatModel([
            helper_fixture.call("ask_user", {"prompt": "Choose format", "answer_type": "text"}, "question"),
            AIMessage(content="Continued after control returned"),
        ])
        started = self._start(thread_id="browser-approval", presented_tools=["ask_user"])
        harness = self.app.state.harness
        old = self._wait_for_pending_interrupt(started["id"])["pending_interrupt"]
        self.submit(harness.request_browser_takeover("browser-approval")).result(5)
        self.assertEqual(harness.get_run(started["id"]).pending_interrupt.interrupt_id, old["interrupt_id"])
        harness.resume_interrupt(started["id"], InterruptDecisionRequest(
            interrupt_id=old["interrupt_id"], namespace=old["namespace"],
            decisions=[{"type": "respond", "message": "Text"}]), require_interrupt_identity=True)
        self.assertEqual(harness.get_run(started["id"]).pending_interrupt.interrupt_id, old["interrupt_id"])
        self.assertEqual(len(RECEIVED_PROMPTS), 1)
        self.submit(harness.release_browser_takeover("browser-approval", "Fresh structure")).result(5)
        final = wait_for_run(self.client, started["id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertIsNone(final["pending_interrupt"])

    def test_stop_during_native_browser_pause_never_replays_tool(self):
        release = threading.Event()
        set_generate_hold(release)
        harness = self.app.state.harness
        try:
            started = self._start(thread_id="browser-stop", presented_tools=["echo"])
            wait_for_generate_hold(timeout=5)
            takeover = self.submit(harness.request_browser_takeover("browser-stop"))
            self.wait_for_control(started["id"], "taking_control")
            release.set()
            takeover.result(5)
            self._wait_for_pending_interrupt(started["id"])
            harness.cancel(started["id"])
            final = wait_for_run(self.client, started["id"])
            self.assertEqual(final["status"], "cancelled", final.get("error"))
            self.assertEqual(final["dispatched_tool_calls"], 0)
        finally:
            release.set()
            set_generate_hold(None)

    def test_stop_during_takeover_drain_aborts_model_and_never_grants_manual_control(self):
        entered = threading.Event()
        class WaitingModel(ScriptedChatModel):
            async def _agenerate(self, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        self.scripted = WaitingModel([])
        started = self._start(thread_id="browser-stop-drain", presented_tools=["echo"])
        self.assertTrue(entered.wait(5))
        harness = self.app.state.harness
        takeover = self.submit(harness.request_browser_takeover("browser-stop-drain"))
        self.wait_for_control(started["id"], "taking_control")
        harness.cancel(started["id"])
        final = wait_for_run(self.client, started["id"])
        self.assertEqual(final["status"], "cancelled", final.get("error"))
        self.assertEqual(final["dispatched_tool_calls"], 0)
        with self.assertRaises(Exception) as caught:
            takeover.result(5)
        self.assertEqual(caught.exception.code, "run_cancelling")
        self.assertEqual(final["browser_control"], "agent")

    def test_takeover_after_browser_approval_invalidates_old_click_without_losing_approval(self):
        effects = []
        async def click(element: str, target: str):
            """Click the chosen element."""
            effects.append(target)
            return "clicked"
        tool = StructuredTool.from_function(coroutine=click, name="browser_click")
        harness = self.app.state.harness
        @asynccontextmanager
        async def tools(_run):
            yield [tool]
        self.scripted = ScriptedChatModel([
            helper_fixture.call("browser_click", {"element": "Submit", "target": "old-ref"}, "old-click"),
            AIMessage(content="Reconsidered the changed page"),
        ])
        with patch.object(harness, "_worker_tools_context", tools):
            started = self._start(thread_id="browser-click-approval", presented_tools=["browser_click"], approval_mode="ask")
            approval = self._wait_for_pending_interrupt(started["id"])["pending_interrupt"]
            self.submit(harness.request_browser_takeover("browser-click-approval")).result(5)
            self.submit(harness.release_browser_takeover("browser-click-approval", "Changed page")).result(5)
            harness.resume_interrupt(started["id"], InterruptDecisionRequest(
                interrupt_id=approval["interrupt_id"], namespace=approval["namespace"],
                decisions=[{"type": "approve"}]), require_interrupt_identity=True)
            final = wait_for_run(self.client, started["id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(effects, [])
        self.assertEqual(final["tool_outcomes"]["old-click"]["outcome"], "not_dispatched")

    def test_closed_browser_invalidates_old_approved_click_without_changing_approval_identity(self):
        reset_received_prompts()
        effects = []
        async def click(element: str, target: str):
            """Click the chosen element."""
            effects.append(target)
            return "clicked"
        tool = StructuredTool.from_function(coroutine=click, name="browser_click")
        harness = self.app.state.harness
        @asynccontextmanager
        async def tools(_run):
            yield [tool]
        self.scripted = ScriptedChatModel([
            helper_fixture.call("browser_click", {"element": "Submit", "target": "old-page-ref"}, "before-close"),
            AIMessage(content="Reconsidered fresh tabs"),
        ])
        with patch.object(harness, "_worker_tools_context", tools):
            started = self._start(thread_id="browser-close-approval", presented_tools=["browser_click"], approval_mode="ask")
            approval = self._wait_for_pending_interrupt(started["id"])["pending_interrupt"]
            self.submit(harness.invalidate_browser_state("browser-close-approval",
                "Browser was closed. FRESH-TABS-91: the next browser action starts fresh pages with retained sign-ins.")).result(5)
            invalidated = harness.get_run(started["id"])
            self.assertEqual(invalidated.browser_control, "agent")
            self.assertEqual(invalidated.browser_revision, 1)
            self.assertEqual(invalidated.pending_interrupt.interrupt_id, approval["interrupt_id"])
            self.assertEqual(invalidated.pending_interrupt.namespace, approval["namespace"])
            harness.resume_interrupt(started["id"], InterruptDecisionRequest(
                interrupt_id=approval["interrupt_id"], namespace=approval["namespace"],
                decisions=[{"type": "approve"}]), require_interrupt_identity=True)
            final = wait_for_run(self.client, started["id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(effects, [])
        self.assertEqual(final["tool_outcomes"]["before-close"]["outcome"], "not_dispatched")
        self.assertTrue(any("FRESH-TABS-91" in prompt for prompt in RECEIVED_PROMPTS))

    def test_browser_action_settles_before_control_and_is_never_repeated_on_return(self):
        entered, release = threading.Event(), threading.Event()
        effects = []
        async def click(element: str, target: str):
            """Click the chosen element."""
            entered.set()
            await asyncio.to_thread(release.wait, 5)
            effects.append(target)
            return "clicked"
        tool = StructuredTool.from_function(coroutine=click, name="browser_click")
        harness = self.app.state.harness
        @asynccontextmanager
        async def tools(_run):
            yield [tool]
        self.scripted = ScriptedChatModel([
            helper_fixture.call("browser_click", {"element": "Submit", "target": "live-ref"}, "active-click"),
            AIMessage(content="Done after the action"),
        ])
        try:
            with patch.object(harness, "_worker_tools_context", tools):
                started = self._start(thread_id="browser-action", presented_tools=["browser_click"], approval_mode="full_access")
                self.assertTrue(entered.wait(5))
                takeover = self.submit(harness.request_browser_takeover("browser-action"))
                self.wait_for_control(started["id"], "taking_control")
                self.assertFalse(takeover.done(), "The live external action still owns control")
                release.set()
                takeover.result(5)
                self._wait_for_pending_interrupt(started["id"])
                self.assertEqual(effects, ["live-ref"])
                self.submit(harness.release_browser_takeover("browser-action", "Observed completed click")).result(5)
                final = wait_for_run(self.client, started["id"])
            self.assertEqual(final["status"], "completed", final.get("error"))
            self.assertEqual(effects, ["live-ref"])
            self.assertEqual(final["dispatched_tool_calls"], 1)
        finally:
            release.set()

    def test_parallel_tool_boundaries_resume_without_duplicate_dispatch(self):
        release = threading.Event()
        set_generate_hold(release)
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[
                {"name": "echo", "args": {"text": "one"}, "id": "parallel-one"},
                {"name": "echo", "args": {"text": "two"}, "id": "parallel-two"}]),
            AIMessage(content="Both finished"),
        ])
        harness = self.app.state.harness
        try:
            started = self._start(thread_id="browser-parallel", presented_tools=["echo"])
            wait_for_generate_hold(timeout=5)
            takeover = self.submit(harness.request_browser_takeover("browser-parallel"))
            self.wait_for_control(started["id"], "taking_control")
            release.set()
            takeover.result(5)
            paused = self._wait_for_pending_interrupt(started["id"])
            self.assertEqual(paused["dispatched_tool_calls"], 0)
            self.submit(harness.release_browser_takeover("browser-parallel", "Fresh page")).result(5)
            final = wait_for_run(self.client, started["id"])
            self.assertEqual(final["status"], "completed", final.get("error"))
            self.assertEqual(final["dispatched_tool_calls"], 2)
            self.assertEqual(set(final["tool_outcomes"]), {"parallel-one", "parallel-two"})
        finally:
            release.set()
            set_generate_hold(None)

    def test_persisted_native_browser_interrupt_survives_reconstruction_and_resumes_once(self):
        release = threading.Event()
        set_generate_hold(release)
        harness = self.app.state.harness
        try:
            started = self._start(thread_id="browser-restart", presented_tools=["echo"])
            wait_for_generate_hold(timeout=5)
            takeover = self.submit(harness.request_browser_takeover("browser-restart"))
            self.wait_for_control(started["id"], "taking_control")
            release.set()
            takeover.result(5)
            self._wait_for_pending_interrupt(started["id"])
            retained = harness.get_run(started["id"])
            # Retire the first fixture owner without resuming its graph. Restore
            # its saved live record to model a process loss at that checkpoint.
            harness.cancel(started["id"])
            self.assertEqual(wait_for_run(self.client, started["id"])["dispatched_tool_calls"], 0)
            harness.close()
            harness.store.put_run(retained)
            restarted = harness_fixture.HarnessApiTests._restart_harness(self)
            recovered = restarted.get_run(started["id"])
            self.assertEqual(recovered.browser_control, "user")
            self.assertEqual(recovered.pending_interrupt.kind, "browser_control")
            self.assertEqual(recovered.dispatched_tool_calls, 0)
            self.submit(restarted.release_browser_takeover("browser-restart", "Fresh restarted page")).result(5)
            with restarted._updates:
                deadline = time.monotonic() + 5
                while restarted._runs[started["id"]].status in {"running", "queued", "cancel_requested"}:
                    remaining = deadline - time.monotonic()
                    self.assertGreater(remaining, 0)
                    restarted._updates.wait(timeout=remaining)
            final = restarted.get_run(started["id"])
            self.assertEqual(final.status, "completed", final.error)
            self.assertEqual(final.dispatched_tool_calls, 1)
            self.assertIsNone(final.pending_interrupt)
        finally:
            release.set()
            set_generate_hold(None)


class BrowserHelperHandoffTests(unittest.TestCase):
    setUp = helper_fixture.AgentCapabilitiesTests.setUp
    tearDown = helper_fixture.AgentCapabilitiesTests.tearDown
    post = helper_fixture.AgentCapabilitiesTests.post
    setup = helper_fixture.AgentCapabilitiesTests.setup
    harness = helper_fixture.AgentCapabilitiesTests.harness
    start = helper_fixture.AgentCapabilitiesTests.start

    def test_helper_generation_drains_then_parent_and_helper_resume_same_native_task(self):
        entered, release = threading.Event(), threading.Event()
        helper = self.setup(presented_tools=["echo"])
        main = ScriptedChatModel([
            helper_fixture.call("task", {"subagent_type": helper["id"], "description": "Return an echo"}, "delegate"),
            AIMessage(content="Parent done"),
        ])
        class HeldChildModel(ScriptedChatModel):
            async def _agenerate(self, *args, **kwargs):
                entered.set()
                await asyncio.to_thread(release.wait, 5)
                return await super()._agenerate(*args, **kwargs)
        child = HeldChildModel([
            helper_fixture.call("echo", {"text": "child output"}, "child-echo"),
            AIMessage(content="Child done"),
        ])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        owner = self.app.state.harness
        try:
            started = self.start(thread_id="browser-helper", presented_tools=["echo"], helper_agent_ids=[helper["id"]])
            self.assertTrue(entered.wait(5))
            pending = submit_checkpoint_task(owner.manager.paths.checkpoints_db,
                owner.request_browser_takeover("browser-helper"))
            deadline = time.monotonic() + 5
            with owner._updates:
                while owner._runs[started["id"]].browser_control != "taking_control":
                    remaining = deadline - time.monotonic()
                    self.assertGreater(remaining, 0)
                    owner._updates.wait(timeout=remaining)
            self.assertFalse(pending.done())
            release.set()
            pending.result(5)
            paused = harness_fixture.HarnessApiTests._wait_for_pending_interrupt(self, started["id"])
            self.assertEqual(paused["pending_interrupt"]["kind"], "browser_control")
            self.assertEqual(len(paused["child_runs"]), 1)
            submit_checkpoint_task(owner.manager.paths.checkpoints_db,
                owner.release_browser_takeover("browser-helper", "Fresh helper page")).result(5)
            final = wait_for_run(self.client, started["id"])
            self.assertEqual(final["status"], "completed", final.get("error"))
            self.assertEqual(final["child_runs"][0]["status"], "completed")
            saved = owner.get_run(final["child_runs"][0]["run_id"])
            self.assertEqual([item["name"] for item in saved.tool_invocations], ["echo"])
        finally:
            release.set()
