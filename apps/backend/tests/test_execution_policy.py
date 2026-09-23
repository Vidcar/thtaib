"""Receiver-side policy regressions for Work/Plan, Access and explicit budgets."""
from __future__ import annotations

import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from workbench_backend.agents.host_shell import interrupt_on_for_run
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun, AgentBudgets
from workbench_backend.inference.ids import utc_now


def run_fixture(**overrides):
    now = utc_now()
    return AgentRun(id="policy", deployment_id="model", task="task", enabled_tools=[],
        presented_tools=["write_file", "edit_file", "rename_file", "delete_file", "execute"],
        created_at=now, updated_at=now, **overrides)


def request(name, args=None, ident="call"):
    return SimpleNamespace(tool_call={"name": name, "args": args or {}, "id": ident})


class ExecutionPolicyTests(unittest.TestCase):
    def test_ask_pauses_every_file_mutation(self):
        gates = interrupt_on_for_run(run_fixture(project_path=".")) or {}
        for name in ("write_file", "edit_file", "rename_file", "delete_file"):
            with self.subTest(tool=name):
                self.assertIn(name, gates)
                self.assertTrue(gates[name]["when"](request(name, {"file_path": "a.txt"})))

    def test_approve_for_me_does_not_auto_allow_shell(self):
        gates = interrupt_on_for_run(run_fixture(project_path=".", approval_mode="approve_for_me"))
        self.assertTrue(gates["execute"]["when"](request("execute", {"command": "git status"})))

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

    def test_approve_for_me_only_auto_allows_captured_text(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "small.txt").write_text("original", encoding="utf-8")
            Path(directory, "binary.bin").write_bytes(b"\x00not text")
            gates = interrupt_on_for_run(run_fixture(project_path=directory, approval_mode="approve_for_me"))
            self.assertFalse(gates["edit_file"]["when"](request("edit_file", {"file_path": "small.txt", "old_string": "original", "new_string": "changed"})))
            self.assertTrue(gates["delete_file"]["when"](request("delete_file", {"file_path": "binary.bin"})))
            self.assertTrue(gates["write_file"]["when"](request("write_file", {"file_path": "/large_tool_results/result.txt", "content": "scratch"})))
