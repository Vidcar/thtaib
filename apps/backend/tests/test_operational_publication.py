"""Live observations never serialize, copy or normalize captured requests."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, GenerationObservation, ModelRequestCapture
from workbench_backend.interaction.projection import event
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore
from tests.large_run_history import synthetic_large_run


class HostileDiagnosticBody:
    def __deepcopy__(self, _memo):
        raise AssertionError("operational observation copied diagnostic content")


@contextmanager
def forbid_diagnostic_processing():
    with ExitStack() as stack:
        for target in (
            "workbench_backend.knowledge.diagnostics.apply_run_diagnostic_policy",
            "workbench_backend.knowledge.diagnostics.redact_structured",
            "workbench_backend.state.store.apply_run_diagnostic_policy",
            "workbench_backend.state.store.apply_capture_policy",
        ):
            stack.enter_context(patch(target, side_effect=AssertionError("operational observation enforced diagnostic policy")))
        yield


class OperationalPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ApplicationStore(WorkbenchPaths(Path(self.temporary.name)))
        self.run = AgentRun(id="publication_fixture", thread_id="graph_fixture", deployment_id="fixture",
            task="task", enabled_tools=[], presented_tools=[], status=AgentRunStatus.running,
            created_at="2026-09-27T12:00:00Z", updated_at="2026-09-27T12:00:00Z")
        self.store.put_run(self.run)
        self.run.model_requests.append(ModelRequestCapture(at=self.run.created_at,
            messages=[{"content": HostileDiagnosticBody()}]))
        self.harness = HarnessService.__new__(HarnessService)
        self.harness._app_store = self.store
        self.harness._manager_provider = lambda: SimpleNamespace(paths=self.store.paths)
        self.harness._knowledge_provider = None
        self.harness._lock = threading.RLock()
        self.harness._runs = {self.run.id: self.run}
        self.harness._reconcile_startup_once = lambda: None
        self.service = InteractionService(self.store, lambda: self.harness, lambda: None)
        self.harness._interaction_observer = self.service.observe
        self.store.register_interaction("display_fixture", "agent", self.run.thread_id, None,
            {"messages": [], "workbench": {"run": None}})

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def assert_capture_free(self, value):
        self.assertNotIn("model_requests", value)
        self.assertNotIn("privacy_fingerprint", json.dumps(value))

    def test_hostile_diagnostics_would_fail_if_serialized_or_deep_copied(self):
        with self.assertRaises(ValueError):
            self.run.model_dump(mode="json")
        with self.assertRaisesRegex(AssertionError, "copied diagnostic"):
            self.run.model_copy(deep=True)

    def test_saved_public_snapshot_excludes_legacy_captures_before_copy(self):
        snapshot = {"messages": [], "workbench": {"run": {
            **self.run.model_dump(mode="json", exclude={"model_requests"}),
            "model_requests": [HostileDiagnosticBody()],
        }}}
        with forbid_diagnostic_processing():
            public = self.service.display_values(snapshot)
        self.assert_capture_free(public["workbench"]["run"])
        self.assertEqual(len(snapshot["workbench"]["run"]["model_requests"]), 1)

    def test_harness_operational_views_exclude_captures_before_conversion(self):
        with forbid_diagnostic_processing():
            self.assert_capture_free(self.harness.get_run_operational(self.run.id).model_dump(mode="json"))
            self.assert_capture_free(self.harness.projection_run(self.run.id))
            self.assertEqual(self.harness.get_run_lifecycle(self.run.id).status, AgentRunStatus.running)
        self.assertEqual(len(self.run.model_requests), 1)

    def test_measurement_excludes_legacy_captures_before_publication(self):
        binding = self.store.get_interaction("display_fixture")
        binding["snapshot"]["workbench"]["run"] = {
            **self.run.model_dump(mode="json", exclude={"model_requests"}),
            "model_requests": [HostileDiagnosticBody()],
        }
        with forbid_diagnostic_processing():
            self.service._observe_measurement(binding, self.run)
            stored = self.store.get_interaction("display_fixture")
        self.assert_capture_free(stored["snapshot"]["workbench"]["run"])
        self.assertEqual(len(binding["snapshot"]["workbench"]["run"]["model_requests"]), 1)

    def test_lifecycle_measurement_native_tokens_and_state_all_exclude_captures(self):
        with forbid_diagnostic_processing():
            self.harness._observe_interaction(self.run, None)
            self.run.generation_observation = GenerationObservation(request_id="call_fixture",
                phase="generating", output_tokens=5, elapsed_seconds=1, measured_at="2026-09-27T12:00:01Z")
            self.harness._observe_interaction(self.run, None, telemetry=True)
            for data in (
                {"event": "message-start", "id": "answer_fixture", "role": "ai"},
                {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": "Visible answer"}},
            ):
                self.harness._observe_interaction(self.run, event("messages", data))
            state = self.service.state("display_fixture")
            binding = self.store.get_interaction("display_fixture")
            self.assert_capture_free(state["values"]["workbench"]["run"])
            self.assert_capture_free(binding["snapshot"]["workbench"]["run"])
            self.assertEqual(state["values"]["messages"][-1]["content"], [{"type": "text", "text": "Visible answer"}])
            wires = list(self.service.replay("display_fixture", 0, binding["seq"]))
        measurements = [wire for wire in wires if wire["params"].get("measurement")]
        self.assertEqual(len(measurements), 1)
        self.assert_capture_free(measurements[0]["params"]["data"]["workbench"]["run"])
        self.assertNotIn("model_requests", json.dumps(wires))

    def test_cold_archived_registration_and_state_never_hydrate_diagnostics(self):
        archived = synthetic_large_run(id="cold_archived", status="completed", thread_id="cold_graph")
        self.store.put_run(archived)
        rows = self.store._diagnostic_rows_locked(archived.id)
        self.assertEqual(len(rows), 50)
        self.assertGreater(sum(len(payload.encode("utf-8")) for _, payload in rows), 10 * 1024 * 1024)
        self.harness._runs.clear()
        with forbid_diagnostic_processing(), \
                patch.object(self.store, "get_execution_run", side_effect=AssertionError("observation hydrated captures")), \
                patch.object(self.store, "normalize_run_diagnostics", side_effect=AssertionError("observation normalized captures")), \
                patch.object(ModelRequestCapture, "model_validate_json", side_effect=AssertionError("observation parsed captures")), \
                patch("workbench_backend.interaction.service.conversation_state", return_value={"messages": []}):
            registered = self.service.register({"source_surface": "agent", "run_id": archived.id})
            thread_id = registered["thread_id"]
            binding = self.store.get_interaction(thread_id)
            self.assertEqual(binding["snapshot"]["workbench"]["run"]["status"], "completed")
            self.assert_capture_free(binding["snapshot"]["workbench"]["run"])
            # Force terminal reconciliation on another cold read. The durable
            # completed boundary must replace this earlier running projection.
            binding["snapshot"]["workbench"]["run"]["status"] = "running"
            self.store.append_interaction(thread_id, [], snapshot=binding["snapshot"], run_id=archived.id)
            state = self.service.state(thread_id)
            self.assertEqual(state["values"]["workbench"]["run"]["status"], "completed")
            self.assert_capture_free(state["values"]["workbench"]["run"])
            self.assertEqual(self.harness._runs, {}, "observation must not create an execution owner")
        self.assertEqual(self.store._diagnostic_rows_locked(archived.id), rows)

    def test_run_read_lock_keeps_missing_run_error_without_hydration(self):
        with patch.object(self.store, "get_execution_run", side_effect=AssertionError("observation hydrated captures")):
            with self.assertRaisesRegex(Exception, "Unknown agent run") as missing:
                with self.harness.run_read_lock("missing_run"):
                    self.fail("a missing run cannot own a derived history read")
        self.assertEqual(missing.exception.code, "run_missing")


if __name__ == "__main__":
    unittest.main()
