"""UI acceptance fixtures retain real admission, graphs, trust and process owners."""

from pathlib import Path
import os
import subprocess
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

# Keep the import-time app in tests.__init__'s session root, rather than in a
# per-test directory that is removed before its registered session cleanup.
from workbench_backend.app import create_app as _isolated_import_time_app

from tests_ui import REPO_ROOT, configure_environment, require_unredirected_directory
from tests_ui.fixture import ApplicationFixture


class UIFixtureTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        self.original_tempdir = tempfile.tempdir
        self.tmp = tempfile.TemporaryDirectory(dir=REPO_ROOT / ".scratch", prefix="ui-fixture-test-")
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, tempfile, "tempdir", self.original_tempdir)
        self.fixture = ApplicationFixture(self.root)
        self.client = TestClient(self.fixture.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.addCleanup(self.fixture.close)
        self.headers = {"X-Workbench-Local-Token": self.fixture.app.state.local_trust_token}

    def post(self, path, body):
        response = self.client.post(path, json=body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def seed(self, scenario="baseline"):
        return self.post("/__test__/seed", {"scenario": scenario})

    def wait(self, predicate, label):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.02)
        self.fail(f"UI fixture did not reach {label}: {self.fixture.state()}")

    def view(self, seed):
        response = self.client.get(f"/v1/chat/conversations/{seed['conversation_id']}", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_root_and_control_routes_require_disposable_storage_and_real_token(self):
        with self.assertRaises(ValueError):
            configure_environment(REPO_ROOT / "unsafe-ui-data")
        response = self.client.post("/__test__/scenario", json={"scenario": "approval"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.fixture.scenario, "baseline")
        response = self.client.post("/__test__/scenario", json={"scenario": "approval"}, headers={"X-Workbench-Local-Token": "wrong"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fixture.scenario, "baseline")

    def test_existing_junctions_cannot_redirect_scratch_or_temporary_writes(self):
        disposable = tempfile.TemporaryDirectory(dir=REPO_ROOT / ".scratch", prefix="ui-isolation-test-")
        self.addCleanup(disposable.cleanup)
        guard_root = Path(disposable.name)

        def junction(name, target):
            path = guard_root / name
            if os.name == "nt":
                subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(path), str(target)],
                               check=True, capture_output=True, text=True)
            else:
                path.symlink_to(target, target_is_directory=True)
            self.addCleanup(path.rmdir if os.name == "nt" else path.unlink)
            return path

        redirected = junction("redirected-root", REPO_ROOT / "apps")
        with self.assertRaisesRegex(ValueError, "must not redirect"):
            require_unredirected_directory(redirected, "Checkout scratch directory")
        with self.assertRaisesRegex(ValueError, "must remain a child"):
            configure_environment(redirected / "new-data")

        temporary_root = guard_root / "data"
        temporary_root.mkdir()
        temporary = temporary_root / "temporary"
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(temporary), str(self.root)],
                           check=True, capture_output=True, text=True)
        else:
            temporary.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(temporary.rmdir if os.name == "nt" else temporary.unlink)
        with self.assertRaisesRegex(ValueError, "temporary directory must remain a child"):
            configure_environment(temporary_root)
        self.assertFalse((REPO_ROOT / "apps" / "new-data").exists())

    def test_seed_executes_native_graph_and_retains_history_with_one_owned_model(self):
        seed = self.seed()
        view = self.view(seed)
        self.assertEqual([message["content"] for message in view["transcript"]], ["Saved baseline question", "Saved baseline answer"])
        self.assertEqual(view["current_run"]["status"], "completed")
        run = self.fixture.app.state.harness.get_run(seed["seed_run_ids"][0])
        self.assertTrue(run.checkpoint_ids)
        self.assertEqual(self.fixture.state()["run_count"], 0)
        deployment, = self.fixture.state()["deployments"]
        self.assertTrue(deployment["process_alive"])
        self.assertEqual(deployment["status"], "running")

    def test_cleanup_reports_failures_and_still_stops_actual_owned_model(self):
        self.seed()
        self.assertTrue(self.fixture.state()["deployments"][0]["process_alive"])
        with patch.object(self.fixture.app.state.harness, "close", side_effect=RuntimeError("injected worker cleanup failure")) as workers, \
                patch.object(self.fixture.app.state.managed_commands, "shutdown", side_effect=RuntimeError("injected command cleanup failure")) as commands:
            with self.assertRaises(ExceptionGroup) as caught:
                self.fixture.close()
            workers.assert_called_once()
            commands.assert_called_once()
        self.assertEqual(len(caught.exception.exceptions), 2)
        self.assertEqual(len(self.fixture.cleanup_errors), 2)
        self.assertFalse(self.fixture._closed)
        self.assertFalse(self.fixture.state()["deployments"][0]["process_alive"])
        self.assertEqual(self.fixture.state()["deployments"][0]["status"], "stopped")
        self.fixture.close()
        self.assertTrue(self.fixture._closed)
        self.assertEqual(self.fixture.cleanup_errors, [])

    def test_lost_acknowledgement_occurs_after_actual_acceptance(self):
        seed = self.seed()
        self.post("/__test__/scenario", {"scenario": "lost_ack", "lose_next_ack": True})
        response = self.client.post(f"/v1/chat/conversations/{seed['conversation_id']}/start", json={"task": "One accepted baseline input", "input_message_id": "baseline-stable-input"}, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.wait(lambda: self.view(seed)["current_run"]["status"] == "completed", "native completion after acknowledgement loss")
        state = self.fixture.state()
        self.assertEqual(state["run_count"], 1)
        self.assertEqual(state["input_ids"], ["baseline-stable-input"])
        self.assertEqual(state["faults"]["lost_acknowledgements"], 1)
        self.assertIn("Baseline response completed", [message["content"] for message in self.view(seed)["transcript"]])

    def test_pre_accept_rejection_records_original_payload_without_executing(self):
        self.seed()
        binding = self.post("/v1/agent-interaction/threads", {"source_surface": "agent"})
        self.post("/__test__/scenario", {"reject_next_submit": True})
        command = {"id": "rejected-command", "method": "run.start", "params": {
            "input": {"messages": [{"id": "rejected-input", "type": "human", "content": "Keep the rejected authored task"}]},
            "metadata": {"workbench": {"deployment_id": self.fixture.seed_data["deployment_id"]}}, "multitaskStrategy": "reject"}}
        response = self.client.post(f"/v1/agent-interaction/threads/{binding['thread_id']}/commands", json=command, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["id"], command["id"])
        self.assertEqual(response.json()["error"], "fixture_rejected")
        self.assertEqual(self.fixture.state()["run_count"], 0)
        self.assertEqual(self.fixture.state()["submissions"], [{"thread_id": binding["thread_id"], "payload": command}])

    def test_transient_state_failure_does_not_change_authoritative_binding(self):
        seed = self.seed()
        binding = self.post("/v1/agent-interaction/threads", {"source_surface": "chat", "conversation_id": seed["conversation_id"]})
        route = f"/v1/agent-interaction/threads/{binding['thread_id']}/state"
        before = self.client.get(route, headers=self.headers).json()
        self.post("/__test__/scenario", {"fail_state_reads": 1})
        self.assertEqual(self.client.get(route, headers=self.headers).status_code, 503)
        after = self.client.get(route, headers=self.headers)
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.json()["values"], before["values"])
        self.assertEqual(self.fixture.state()["run_count"], 0)

    def test_failed_chat_lookup_targets_product_read_and_keeps_control_evidence(self):
        seed = self.seed()
        self.post("/__test__/scenario", {"fail_state_reads": 1})
        state = self.client.get("/__test__/state", headers=self.headers)
        self.assertEqual(state.status_code, 200)
        failed = self.client.get(f"/v1/chat/conversations/{seed['conversation_id']}", headers=self.headers)
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(self.fixture.state()["faults"]["state_lookup_failures"], 1)
        self.assertEqual(self.fixture.state()["failed_lookup_paths"], [f"/v1/chat/conversations/{seed['conversation_id']}"])
        self.assertEqual(self.view(seed)["current_run"]["status"], "completed")

    def test_duplicate_negative_control_executes_two_actual_graphs(self):
        self.seed()
        binding = self.post("/v1/agent-interaction/threads", {"source_surface": "agent"})
        self.post("/__test__/scenario", {"negative_control": "duplicate_execution"})
        command = {"id": "duplicate-control", "method": "run.start", "params": {
            "input": {"messages": [{"id": "one-original-input", "type": "human", "content": "Expose a duplicated graph"}]},
            "metadata": {"workbench": {"deployment_id": self.fixture.seed_data["deployment_id"]}}, "multitaskStrategy": "reject"}}
        self.post(f"/v1/agent-interaction/threads/{binding['thread_id']}/commands", command)
        self.wait(lambda: len(self.fixture.state()["runs"]) == 2 and all(run["status"] == "completed" for run in self.fixture.state()["runs"]), "two deliberately duplicated real graph executions")
        state = self.fixture.state()
        self.assertEqual(state["run_count"], 2)
        for run_id in state["run_ids"]:
            self.assertEqual(state["model_factory_run_ids"].count(run_id), 1)

    def test_required_real_inference_missing_assets_never_uses_fake_fallback(self):
        from tests_integration.assets import SmokeAssetsUnavailable
        other_root = self.root / "required-real-case"
        real_fixture = ApplicationFixture(other_root, inference="real")
        with TestClient(real_fixture.app):
            try:
                with patch("tests_integration.assets.resolve_assets", side_effect=SmokeAssetsUnavailable("required fixture unavailable")):
                    with self.assertRaisesRegex(SmokeAssetsUnavailable, "required fixture unavailable"):
                        real_fixture.seed()
                self.assertEqual(real_fixture.inference, "real")
                self.assertEqual(real_fixture.state()["run_count"], 0)
                self.assertIsNone(real_fixture.real_server)
                self.assertFalse((other_root / "baseline-model.gguf").exists())
            finally:
                real_fixture.close()

    def test_held_native_admission_releases_without_replacing_payload(self):
        self.seed()
        binding = self.post("/v1/agent-interaction/threads", {"source_surface": "agent"})
        self.post("/__test__/scenario", {"hold_submit": True})
        command = {"id": "held-command", "method": "run.start", "params": {
            "input": {"messages": [{"id": "held-input", "type": "human", "content": "Frozen original held task"}]},
            "metadata": {"workbench": {"deployment_id": self.fixture.seed_data["deployment_id"]}}, "multitaskStrategy": "reject"}}
        results = []
        worker = threading.Thread(target=lambda: results.append(self.client.post(f"/v1/agent-interaction/threads/{binding['thread_id']}/commands", json=command, headers=self.headers)))
        worker.start()
        try:
            self.wait(lambda: len(self.fixture.state()["submissions"]) == 1, "actual held command ingress")
            self.assertEqual(self.fixture.state()["run_count"], 0)
        finally:
            self.fixture.submit_release.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0].status_code, 200, results[0].text)
        self.wait(lambda: self.fixture.state()["runs"][0]["status"] == "completed", "held command completion")
        self.assertEqual(self.fixture.state()["input_ids"], ["held-input"])
        self.assertEqual(self.fixture.state()["submissions"][0]["payload"], command)

    def test_stream_fault_closes_only_observation_and_keeps_native_headers(self):
        seed = self.seed()
        binding = self.post("/v1/agent-interaction/threads", {
            "source_surface": "chat", "conversation_id": seed["conversation_id"],
        })
        self.post("/__test__/scenario", {"disconnect_next_stream": True})
        response = self.client.post(
            f"/v1/agent-interaction/threads/{binding['thread_id']}/stream/events",
            json={"channels": ["values", "lifecycle"]},
            headers={**self.headers, "Origin": "http://127.0.0.1:5173"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5173")
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn("data:", response.text)
        self.assertEqual(self.fixture.state()["faults"]["stream_disconnects"], 1)
        self.assertEqual(self.fixture.state()["run_count"], 0)
        self.assertEqual(self.view(seed)["current_run"]["status"], "completed")

    def test_shutdown_finishes_an_open_actual_http_observer(self):
        from tests.test_event_stream import loopback_app_server, read_loopback_interaction_events

        seed = self.seed()
        binding = self.post("/v1/agent-interaction/threads", {
            "source_surface": "chat", "conversation_id": seed["conversation_id"],
        })
        opened = threading.Event()
        finished = threading.Event()
        received, errors = [], []
        with loopback_app_server(self.fixture.app) as origin:
            def observe():
                try:
                    received.extend(read_loopback_interaction_events(
                        origin, token=self.fixture.app.state.local_trust_token,
                        thread_id=binding["thread_id"], body={"channels": ["values", "lifecycle"]},
                        stop=lambda events: False, timeout=5, opened=opened,
                    ))
                except Exception as exc:
                    errors.append(exc)
                finally:
                    finished.set()

            observer = threading.Thread(target=observe, daemon=True)
            observer.start()
            try:
                self.assertTrue(opened.wait(3), "The actual HTTP observer did not open")
                self.post("/__test__/shutdown", {})
                self.assertTrue(finished.wait(3), "Native shutdown did not finish its open observer")
                self.assertEqual(errors, [])
                self.assertTrue(received, "The observer did not receive native stream events")
            finally:
                self.fixture.app.state.shutdown_requested.set()
                observer.join(timeout=5)
                self.assertFalse(observer.is_alive(), "The HTTP observer worker did not stop")

    def test_exact_approval_gates_real_file_effect(self):
        seed = self.seed("approval")
        self.post(f"/v1/chat/conversations/{seed['conversation_id']}/start", {"task": "Create the approved baseline file"})
        pending = self.wait(lambda: self.view(seed)["current_run"].get("pending_interrupt"), "native file approval")
        self.assertFalse(Path(seed["owned_effect_path"]).exists())
        run_id = self.view(seed)["current_run"]["id"]
        wrong = self.client.post(f"/v1/agent-runs/{run_id}/interrupt-decision", json={"interrupt_id": pending["interrupt_id"], "namespace": ["foreign"], "decisions": [{"type": "approve"}]}, headers=self.headers)
        self.assertEqual(wrong.status_code, 409)
        self.assertFalse(Path(seed["owned_effect_path"]).exists())
        self.post(f"/v1/agent-runs/{run_id}/interrupt-decision", {"interrupt_id": pending["interrupt_id"], "namespace": pending.get("namespace", []), "decisions": [{"type": "approve"}]})
        self.wait(lambda: self.view(seed)["current_run"]["status"] == "completed", "approved file completion")
        self.assertEqual(Path(seed["owned_effect_path"]).read_text(), "Approved baseline output")
        invocations = self.fixture.state()["runs"][0]["tool_invocations"]
        self.assertEqual([item["name"] for item in invocations], ["write_file"])

    def test_stop_confirms_owned_command_process_is_gone(self):
        seed = self.seed("command")
        self.post("/__test__/scenario", {"hold_model": True})
        self.post(f"/v1/chat/conversations/{seed['conversation_id']}/start", {"task": "Start the owned baseline command", "approval_mode": "full_access"})
        pending = self.wait(lambda: self.view(seed)["current_run"].get("pending_interrupt"), "native computer command confirmation")
        run_id = self.view(seed)["current_run"]["id"]
        self.post(f"/v1/agent-runs/{run_id}/interrupt-decision", {"interrupt_id": pending["interrupt_id"], "namespace": pending.get("namespace", []), "decisions": [{"type": "approve"}]})
        command = self.wait(lambda: next((item for item in self.fixture.state()["commands"] if item["alive"]), None), "owned command process")
        self.assertTrue(command["alive"])
        self.post(f"/v1/chat/conversations/{seed['conversation_id']}/cancel", {})
        self.wait(lambda: not self.fixture.state()["commands"][0]["alive"], "confirmed process stop")
        self.wait(lambda: self.view(seed)["current_run"]["status"] == "cancelled", "native cancelled run")
        self.assertEqual(self.fixture.state()["runs"][0]["stop_reason"], "cancelled")

    def test_retained_output_is_verified_and_does_not_follow_changed_source(self):
        seed = self.seed("retained")
        asset_id, = seed["retained_asset_ids"]
        self.post("/__test__/scenario", {"change_source": True})
        response = self.client.get(f"/v1/assets/{asset_id}/preview", params={"session_id": seed["conversation_id"]}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["preview"], "Retained baseline output")
        self.assertEqual(response.json()["source_status"], "changed")

    def test_failed_model_start_uses_native_failed_status_and_can_retry(self):
        seed = self.seed("model")
        original_process, = self.fixture.state()["model_processes"]
        self.assertTrue(original_process["alive"])
        self.post(f"/v1/deployments/{seed['deployment_id']}/stop", {})
        self.assertFalse(self.fixture.state()["model_processes"][0]["alive"])
        self.post("/__test__/scenario", {"fail_model_start": True})
        response = self.client.post(f"/v1/deployments/{seed['deployment_id']}/start", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("Baseline model load failed", response.json()["error"])
        self.assertFalse(self.fixture.state()["deployments"][0]["process_alive"])
        restarted = self.post(f"/v1/deployments/{seed['deployment_id']}/start", {})
        self.assertEqual(restarted["status"], "running")
        self.assertTrue(self.fixture.state()["deployments"][0]["process_alive"])
        self.assertFalse(self.fixture.state()["model_processes"][0]["alive"])
        self.assertTrue(self.fixture.state()["model_processes"][1]["alive"])
        self.assertNotEqual(self.fixture.state()["model_processes"][1]["create_time"], original_process["create_time"])

    def test_failed_shutdown_reports_failure_after_stopping_native_owners(self):
        self.seed()
        self.post("/__test__/scenario", {"fail_shutdown": True})
        response = self.client.post("/__test__/shutdown", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertIn("Baseline native shutdown failed", response.json()["detail"])
        self.assertTrue(self.fixture._closed)
        self.assertTrue(self.fixture.app.state.shutdown_requested.is_set())
        self.assertTrue(all(item["alive"] is False for item in self.fixture.model_process_evidence()))

    def test_restart_reopens_same_native_records_and_retained_bytes(self):
        seed = self.seed("retained")
        asset_id, = seed["retained_asset_ids"]
        self.post("/__test__/scenario", {"change_source": True})
        run_ids = self.view(seed)["run_ids"]
        self.fixture.close()
        self.client.__exit__(None, None, None)
        restarted = ApplicationFixture(self.root)
        with TestClient(restarted.app) as client:
            try:
                headers = {"X-Workbench-Local-Token": restarted.app.state.local_trust_token}
                reopened = client.post("/__test__/seed", json={"scenario": "retained"}, headers=headers)
                self.assertEqual(reopened.status_code, 200, reopened.text)
                self.assertEqual(reopened.json()["conversation_id"], seed["conversation_id"])
                self.assertEqual(reopened.json()["retained_asset_ids"], [asset_id])
                conversation = client.get(f"/v1/chat/conversations/{seed['conversation_id']}", headers=headers).json()
                self.assertEqual(conversation["run_ids"], run_ids)
                content = client.get(f"/v1/assets/{asset_id}/preview", params={"session_id": seed["conversation_id"]}, headers=headers).json()
                self.assertEqual(content["preview"], "Retained baseline output")
                self.assertEqual(content["source_status"], "changed")
                self.assertEqual(restarted.state()["run_count"], 0)
            finally:
                restarted.close()

    def test_compaction_fixture_retains_emitted_tool_results_through_repeated_summary_and_restart(self):
        seed = self.seed("compaction_history")
        binding = self.post("/v1/agent-interaction/threads", {
            "source_surface": "chat", "conversation_id": seed["conversation_id"],
        })
        data = seed["compaction"]
        self.post(f"/v1/chat/conversations/{seed['conversation_id']}/start", {
            "task": data["task"], "presented_tools": data["tools"], "approval_mode": "full_access",
            "per_request_overrides": data["request_settings"],
        })
        self.wait(lambda: self.view(seed)["current_run"]["status"] in {"completed", "failed"}, "compaction terminal result")
        self.assertEqual(self.view(seed)["current_run"]["status"], "completed", self.view(seed)["current_run"].get("error"))
        row, = self.fixture.state()["compaction"]["rows"]
        self.assertEqual(row["thread_id"], binding["thread_id"])
        self.assertGreaterEqual(row["native_summary_count"], 2, {
            "events": row["compacted_events"], "calls": row["model_calls"],
            "canonical_lengths": [(message.get("type"), len(str(message.get("content")))) for message in row["canonical"]]})
        self.assertGreater(row["cutoff_index"], 0)
        self.assertTrue(row["offload_readable"])
        self.assertEqual(row["write_count"], 1)
        self.assertEqual(row["read_count"], data["expected_read_count"])
        self.assertEqual(row["write_content"], data["write_content"])
        self.assertTrue(all(event["detail"]["owner"] == "deepagents-upstream" for event in row["compacted_events"]))
        self.assertEqual({call["purpose"] for call in row["model_calls"]}, {"summary", "work"})
        self.assertEqual(row["native_input_capture_errors"], [])
        counts = row["native_input_counts"]
        self.assertTrue(counts)
        self.assertEqual({count["basis"] for count in counts}, {"estimated"})
        self.assertTrue(any(count["purpose"] == "summary" for count in counts))
        self.assertGreater(max(count["input_tokens"] for count in counts if count["tools_sha256"]), 4096)
        first_result = next(message for message in row["archive"]
            if message["type"] == "tool" and data["tool_start_marker"] in str(message["content"]))
        original_by_id = {message["id"]: message for message in row["original_tool_results"]}
        for archived in (message for message in row["archive"] if message["type"] == "tool"):
            emitted = original_by_id[archived["id"]]
            self.assertEqual(archived["content"], emitted["content"])
            self.assertEqual(archived["tool_call_id"], emitted["tool_call_id"])
        self.assertIn(data["tool_end_marker"], first_result["content"])
        reduced = next(message for message in row["canonical"] if message["id"] == first_result["id"])
        self.assertLess(len(reduced["content"]), len(first_result["content"]))
        self.assertNotIn(data["internal_summary_marker"], str(row["archive"]))
        self.assertEqual(len({message["id"] for message in row["archive"]}), len(row["archive"]))
        original = row["archive"]
        self.fixture.close()
        self.client.__exit__(None, None, None)
        restarted = ApplicationFixture(self.root)
        with TestClient(restarted.app) as client:
            try:
                headers = {"X-Workbench-Local-Token": restarted.app.state.local_trust_token}
                reopened = client.post("/__test__/seed", json={"scenario": "compaction_history"}, headers=headers)
                self.assertEqual(reopened.status_code, 200, reopened.text)
                self.assertEqual(reopened.json()["conversation_id"], seed["conversation_id"])
                saved, = restarted.state()["compaction"]["rows"]
                self.assertEqual(saved["archive"], original)
                self.assertEqual(saved["model_calls"], row["model_calls"])
                self.assertEqual(saved["original_tool_results"], row["original_tool_results"])
                self.assertEqual(saved["native_input_counts"], row["native_input_counts"])
                self.assertEqual(saved["write_count"], 1)
                self.assertEqual(saved["read_count"], data["expected_read_count"])
                self.assertTrue(saved["offload_readable"])
            finally:
                restarted.close()

    def test_compaction_observation_negative_controls_keep_the_durable_oracle(self):
        seed = self.seed("compaction_history")
        binding = self.post("/v1/agent-interaction/threads", {
            "source_surface": "chat", "conversation_id": seed["conversation_id"],
        })
        original = self.client.get(f"/v1/agent-interaction/threads/{binding['thread_id']}/state", headers=self.headers).json()
        for control in ("compaction_overwritten_history", "compaction_visible_summary"):
            self.post("/__test__/scenario", {"negative_control": control})
            changed = self.client.get(f"/v1/agent-interaction/threads/{binding['thread_id']}/state", headers=self.headers).json()
            self.assertNotEqual(changed["values"]["messages"], original["values"]["messages"])
            self.assertEqual(self.fixture.app.state.interaction.state(binding["thread_id"])["values"]["messages"], original["values"]["messages"])
        self.post("/__test__/scenario", {"negative_control": None})

    def test_native_count_observer_preserves_one_call_returns_exceptions_and_capture_privacy(self):
        from workbench_backend.inference.telemetry import request_purpose
        original = Mock(return_value=8123)
        model = SimpleNamespace(count_input_tokens=original)
        run = SimpleNamespace(id="observed-native-run")
        self.fixture.observe_existing_native_counts(model, run)
        payload = {"messages": [{"role": "user", "content": "PRIVATE-COUNT-PAYLOAD"}],
            "tools": [{"type": "function", "function": {"name": "read_file"}}]}
        self.assertEqual(model.count_input_tokens(payload), 8123)
        original.assert_called_once_with(payload)
        original.return_value = None
        with request_purpose("summary"):
            self.assertIsNone(model.count_input_tokens({"messages": []}))
        self.assertEqual(original.call_count, 2)
        records = self.fixture.compaction_input_counts
        self.assertEqual([record["ordinal"] for record in records], [1, 2])
        self.assertEqual([record["purpose"] for record in records], ["work", "summary"])
        self.assertEqual([record["input_tokens"] for record in records], [8123, None])
        self.assertIsNotNone(records[0]["tools_sha256"])
        self.assertIsNone(records[1]["tools_sha256"])
        for record in records:
            self.assertEqual(set(record), {"ordinal", "run_id", "purpose", "input_tokens", "basis", "payload_sha256", "tools_sha256"})
            self.assertRegex(record["payload_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual([record["basis"] for record in records], ["native", "unavailable"])
        self.assertNotIn("PRIVATE-COUNT-PAYLOAD", self.fixture.compaction_counts_path.read_text(encoding="utf-8"))
        failure = RuntimeError("counter failure")
        original.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            model.count_input_tokens(payload)
        self.assertIs(caught.exception, failure)
        self.assertEqual(original.call_count, 3)
        self.assertEqual(len(records), 2)
        original.side_effect = None
        original.return_value = 731
        with patch.object(Path, "write_text", side_effect=OSError("capture cannot save")):
            self.assertEqual(model.count_input_tokens(payload), 731)
        self.assertEqual(original.call_count, 4)
        self.assertEqual(self.fixture.compaction_count_capture_errors, [{"run_id": run.id, "error_kind": "OSError"}])

    def test_deterministic_projection_observer_keeps_default_payload_and_estimated_basis(self):
        from langchain_core.messages import HumanMessage
        from tests_ui.fixture import FixtureModel
        from workbench_backend.agents.context import estimate_payload
        from workbench_backend.inference.request_projection import project_context_payload
        self.fixture.scenario = "compaction_history"
        run = SimpleNamespace(id="observed-estimated-run")
        model = FixtureModel(self.fixture, run, [])
        self.assertFalse(callable(getattr(model, "count_input_tokens", None)))
        messages = [HumanMessage(content="Only an estimated fixture payload")]
        payload = model.project_context_payload(messages)
        self.assertEqual(payload, project_context_payload(messages))
        record, = self.fixture.compaction_input_counts
        self.assertEqual(record["basis"], "estimated")
        self.assertEqual(record["input_tokens"], estimate_payload(payload))


if __name__ == "__main__":
    unittest.main()
