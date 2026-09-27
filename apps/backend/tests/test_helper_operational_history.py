"""Helper admission and recovery exclude the parent's captured history."""

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from workbench_backend.agents.helper_execution import _child_run
from workbench_backend.agents.setup_schemas import FrozenHelperSelection, SetupConfiguration
from tests import test_agent_capabilities as helper_fixture
from tests.large_run_history import synthetic_large_run


class _UncopyableDiagnostic:
    def __deepcopy__(self, _memo):
        raise AssertionError("Helper admission copied captured model history")


class HelperOperationalHistoryTests(unittest.TestCase):
    setUp = helper_fixture.AgentCapabilitiesTests.setUp
    tearDown = helper_fixture.AgentCapabilitiesTests.tearDown

    def test_work_and_plan_helpers_admit_and_reload_without_parent_diagnostic_work(self):
        owner = self.app.state.harness
        for mode in ("work", "plan"):
            with self.subTest(mode=mode):
                parent = synthetic_large_run(
                    id="parent_" + mode, deployment_id=self.deployment.id,
                    project_path=str(self.folder), work_mode=mode,
                    enabled_tools=["echo", "task", "read_file", "write_file"],
                    presented_tools=["echo", "task", "read_file", "write_file"],
                )
                owner.store.put_run(parent)
                self.assertGreaterEqual(len(parent.model_requests), 50)
                self.assertGreaterEqual(sum(len(capture.instructions or "") for capture in parent.model_requests), 10 * 1024 * 1024)
                parent.model_requests[0].messages.append({"content": _UncopyableDiagnostic()})
                snapshot = FrozenHelperSelection(
                    agent_id="helper_synthetic", version_id="helper_version", name="Synthetic helper",
                    configuration=SetupConfiguration(presented_tools=["echo", "read_file", "write_file"]),
                )
                payload = {"messages": [HumanMessage(content="Read and report")]}
                with patch.object(owner.store, "get_run", side_effect=AssertionError("Helper admission inspected diagnostics")):
                    child = _child_run(owner, parent, snapshot, "call_" + mode, payload)
                    self.assertEqual(child.model_requests, [])
                    self.assertEqual(child.parent_run_id, parent.id)
                    self.assertEqual(child.work_mode, mode)
                    self.assertEqual(child.task, "Read and report")
                    self.assertEqual("write_file" in child.presented_tools, mode == "work")
                    owner.store.put_execution_run(child)
                    recovered = _child_run(owner, parent, snapshot, "call_" + mode, payload)
                    self.assertEqual(recovered.id, child.id)
                    self.assertEqual(recovered.presented_tools, child.presented_tools)
                    self.assertEqual(recovered.model_requests, [])


if __name__ == "__main__":
    unittest.main()
