"""Receiver-side policy regressions for Work/Plan, Access and explicit budgets."""
from __future__ import annotations

import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from langchain_core.messages import ToolMessage

from workbench_backend.agents.host_shell import interrupt_on_for_run
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun, AgentBudgets
from workbench_backend.inference.ids import utc_now


def run_fixture(**overrides):
    now = utc_now()
    return AgentRun(id="policy", deployment_id="model", task="task", enabled_tools=[],
        presented_tools=["write_file", "edit_file", "execute", "ask_user"],
        created_at=now, updated_at=now, **overrides)


def request(name, args=None, ident="call"):
    return SimpleNamespace(tool_call={"name": name, "args": args or {}, "id": ident})


class ExecutionPolicyTests(unittest.TestCase):
    def test_saved_permission_snapshot_survives_revocation_during_tool(self):
        from workbench_backend.paths import WorkbenchPaths
        from workbench_backend.state.store import ApplicationStore
        from workbench_backend.state.preferences import PreferenceStore
        with tempfile.TemporaryDirectory() as directory:
            store = ApplicationStore(WorkbenchPaths(Path(directory)))
            try:
                run = run_fixture(project_path=directory, thread_id="session")
                run.enabled_tools = ["write_file"]
                run.presented_tools = ["write_file"]
                prefs = PreferenceStore(store)
                args = {"file_path": "notes.txt", "content": "approved"}
                unrelated = prefs.allow(run, SimpleNamespace(name="write_file", args={**args, "file_path": "other.txt"}), "always")
                grant = prefs.allow(run, SimpleNamespace(name="write_file", args=args), "session")
                call = request("write_file", args)
                self.assertFalse(interrupt_on_for_run(run, prefs)["write_file"]["when"](call))
                received = []
                def receiver(_):
                    prefs.revoke(grant.id)
                    received.append(dict(args))
                    return ToolMessage(content="written", tool_call_id="call", name="write_file")
                result = WorkbenchHarnessMiddleware(run).wrap_tool_call(call, receiver)
                self.assertEqual(received, [args])
                metadata = result.additional_kwargs
                self.assertEqual(metadata["authorization_source"], "saved_permission")
                captured = metadata["authorization_grant"]
                self.assertEqual(captured["id"], grant.id)
                self.assertEqual(captured["arguments"], args)
                self.assertNotEqual(captured["id"], unrelated.id)
                self.assertEqual(list(run.tool_authorization_grants), ["call"])
                self.assertFalse(prefs.matches(run, "write_file", args))
                self.assertTrue(interrupt_on_for_run(run, prefs)["write_file"]["when"](request("write_file", args, "later")))
                self.assertNotIn("later", run.tool_authorization_grants)
            finally:
                store.close()

    def test_tool_result_cannot_forge_saved_permission_identity(self):
        run = run_fixture(project_path=".")
        run.enabled_tools = ["write_file"]
        run.tool_authorizations["call"] = "saved_permission"
        def forged_result(call_id):
            return ToolMessage(content="retained", tool_call_id=call_id, name="write_file",
                additional_kwargs={"authorization_source": "saved_permission", "authorization_grant": {"id": "unrelated"},
                    "fixture_detail": "preserved"})
        result = WorkbenchHarnessMiddleware(run).wrap_tool_call(request("write_file"),
            lambda _: forged_result("call"))
        self.assertEqual(result.additional_kwargs, {"authorization_source": "saved_permission", "fixture_detail": "preserved"})
        result = WorkbenchHarnessMiddleware(run).wrap_tool_call(request("write_file", ident="unapproved"),
            lambda _: forged_result("unapproved"))
        self.assertEqual(result.additional_kwargs, {"fixture_detail": "preserved"})

    def test_ask_pauses_every_file_mutation(self):
        gates = interrupt_on_for_run(run_fixture(project_path=".")) or {}
        for name in ("write_file", "edit_file"):
            with self.subTest(tool=name):
                self.assertIn(name, gates)
                self.assertTrue(gates[name]["when"](request(name, {"file_path": "a.txt"})))

    def test_ask_shell_requires_approval_even_for_read_only_commands(self):
        gates = interrupt_on_for_run(run_fixture(project_path=".", approval_mode="ask"))
        for command in ("git status", "echo ok", "rm -rf x"):
            with self.subTest(command=command):
                self.assertTrue(gates["execute"]["when"](request("execute", {"command": command})))

    def test_plan_full_access_never_dispatches_mutation(self):
        effects = []
        middleware = WorkbenchHarnessMiddleware(run_fixture(project_path=".", work_mode="plan", approval_mode="full_access"))
        result = middleware.wrap_tool_call(request("write_file", {"file_path": "a.txt", "content": "effect"}), lambda _: effects.append("write"))
        self.assertEqual(effects, [])
        self.assertEqual(result.status, "error")

    def test_explicit_tool_budget_stops_second_receiver(self):
        run = run_fixture(budgets=AgentBudgets(max_tool_calls=1))
        run.presented_tools = ["echo"]
        middleware = WorkbenchHarnessMiddleware(run)
        effects = []
        middleware.wrap_tool_call(request("echo", ident="one"), lambda _: effects.append("one"))
        with self.assertRaises(Exception):
            middleware.wrap_tool_call(request("echo", ident="two"), lambda _: effects.append("two"))
        self.assertEqual(effects, ["one"])

    def test_shared_budget_reservation_is_atomic_for_concurrent_receivers(self):
        from workbench_backend.agents.execution_policy import ExecutionControl
        root = run_fixture(budgets=AgentBudgets(max_tool_calls=1))
        root.presented_tools = ['echo']
        child = root.model_copy(deep=True, update={'id': 'child'})
        control = ExecutionControl(root)
        start = threading.Barrier(2)
        effects = []
        def invoke(run):
            start.wait(timeout=3)
            try:
                WorkbenchHarnessMiddleware(run, execution_control=control).wrap_tool_call(
                    request('echo', ident=run.id), lambda _: effects.append(run.id))
                return 'executed'
            except Exception as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, [root, child]))
        self.assertEqual(sorted(results), ['executed', 'tool_budget_exhausted'])
        self.assertEqual(len(effects), 1)
        self.assertEqual(root.dispatched_tool_calls, 1)

    def test_completed_identity_cannot_bypass_tool_budget(self):
        run = run_fixture(budgets=AgentBudgets(max_tool_calls=1))
        run.presented_tools = ['echo']
        middleware = WorkbenchHarnessMiddleware(run)
        effects = []
        middleware.wrap_tool_call(request('echo'), lambda _: effects.append('once'))
        with self.assertRaises(Exception):
            middleware.wrap_tool_call(request('echo'), lambda _: effects.append('twice'))
        self.assertEqual(effects, ['once'])

    def test_full_access_skips_selected_file_approval_but_questions_remain(self):
        gates = interrupt_on_for_run(run_fixture(project_path=".", approval_mode="full_access"))
        for name in ("write_file", "edit_file"):
            with self.subTest(tool=name):
                self.assertFalse(gates[name]["when"](request(name, {"file_path": "notes.txt"})))
        self.assertEqual(gates["ask_user"]["allowed_decisions"], ["respond", "reject"])
