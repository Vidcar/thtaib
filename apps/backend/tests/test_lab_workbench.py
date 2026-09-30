"""Lab records, incremental samples, exact scoring and owned model lifecycle."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from langchain_core.messages import AIMessage
from workbench_backend.agents.harness import HarnessService

from workbench_backend.errors import LabError, ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import DeploymentStatus, LocalImportRequest, ManagedDeploymentRequest, PinRuntimeRequest, ServerProperties, ModelConfigurationWriteRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.lab.native import LabStopped, NativeLabClient, timing_sample
from workbench_backend.lab.needles import needle_task, needle_text, score_needle
from workbench_backend.lab.workbench import LabWorkbenchService
from workbench_backend.lab.workbench_schemas import ChallengeWrite, LabRunRequest
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore
from workbench_backend.state.checkpointer import close_sqlite_checkpointer
from tests.support import write_tiny_gguf
from tests.scripted_model import ScriptedChatModel


def sample(length=1024, generation=512):
    return {"content": "answer", "tokens_evaluated": length, "tokens_cached": length + generation - 1,
            "timings": {"prompt_n": length, "prompt_per_second": 50.0,
                        "predicted_n": generation, "predicted_per_second": 20.0}}


class FakeNative:
    calls = []
    block_length = None
    block_depth = None
    entered = threading.Event()
    in_flight = 0
    peak = 0

    def __init__(self, cancel):
        self.cancel = cancel

    async def performance_prompt(self, deployment, length, generation):
        return [length]

    async def memory_prompt(self, deployment, task, depth, context_size):
        self.expected = task.expected
        return [depth], {"needle_before_question": True}

    async def completion(self, deployment, prompt, generation, *, exact):
        self.calls.append({"deployment_id": deployment.id, "prompt": prompt, "exact": exact})
        FakeNative.in_flight += 1
        FakeNative.peak = max(FakeNative.peak, FakeNative.in_flight)
        try:
            if (exact and prompt[0] == self.block_length) or (not exact and prompt[0] == self.block_depth):
                self.entered.set()
                while not self.cancel.is_set():
                    await asyncio.sleep(0.01)
                raise LabStopped()
            await asyncio.sleep(0.03)
            return sample(prompt[0], generation) if exact else {"content": ", ".join(self.expected), "tokens_evaluated": 1500}
        finally:
            FakeNative.in_flight -= 1


class LabWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.manager = ModelManager(self.paths)
        gguf = write_tiny_gguf(Path(self.tmp.name) / "source" / "tiny.gguf", context_length=8192, block_count=8)
        imported = self.manager.import_local(LocalImportRequest(source_path=str(gguf)))
        self.bundle = self.manager.get_bundle(imported.bundle_id)
        self.configuration = self.manager.save_model_configuration(self.bundle.id, ModelConfigurationWriteRequest(display_name="Lab setup"))
        self.store = ApplicationStore(self.paths)
        self.service = LabWorkbenchService(lambda: self.manager, lambda: None, self.store, client_factory=FakeNative)
        self.service._recovered = True
        FakeNative.calls = []
        FakeNative.block_length = FakeNative.block_depth = None
        FakeNative.entered = threading.Event()
        FakeNative.in_flight = FakeNative.peak = 0
        self.load_patch = patch.object(self.manager, "prepare_lab_deployment", side_effect=self.load)
        self.load_patch.start()

    def tearDown(self):
        self.service.close()
        self.load_patch.stop()
        self.store.close()
        close_sqlite_checkpointer(self.paths.checkpoints_db)
        self.manager.imports.close()
        self.tmp.cleanup()

    def load(self, configuration_id, startup, *, owner, concurrent, deployment_id, cancelled=None):
        deployment = self.manager.get_deployment(deployment_id)
        return self.manager.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.running, "endpoint": "http://127.0.0.1:9/v1",
            "server_props": ServerProperties(fetched=utc_now(), source_url="fixture", n_ctx=8192)}))

    def request(self, **overrides):
        return LabRunRequest.model_validate({"kind": "performance", "configurations": [{"configuration_id": self.configuration.id}],
            "prompt_lengths": [1024], **overrides})

    def wait(self, run_id, predicate=lambda run: run.status not in {"queued", "running", "stopping"}):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = self.service.get_run(run_id)
            if predicate(run):
                return run
            time.sleep(0.01)
        self.fail("Lab did not reach the expected state")

    def test_persist_restart_delete_one_and_no_conversation(self):
        first = self.wait(self.service.start(self.request()).id)
        second = self.wait(self.service.start(self.request()).id)
        self.assertEqual(first.status, "completed")
        with ApplicationStore(self.paths) as restored:
            self.assertEqual(len(restored.list_lab_runs()), 2)
            self.assertEqual(restored.list_conversations(), [])
            restored.delete_lab_run(first.id)
            self.assertEqual([run.id for run in restored.list_lab_runs()], [second.id])
            self.assertEqual(len(restored.get_lab_run(second.id).measurements), 1)

    def test_finished_point_is_durable_before_second_and_stop_keeps_only_finished(self):
        FakeNative.block_length = 4096
        run = self.service.start(self.request(prompt_lengths=[1024, 4096, 8192]))
        self.assertTrue(FakeNative.entered.wait(5))
        with ApplicationStore(self.paths) as observer:
            self.assertEqual([row.requested_prompt_length for row in observer.get_lab_run(run.id).measurements], [1024])
        self.service.stop(run.id)
        stopped = self.wait(run.id)
        self.assertEqual(stopped.status, "stopped")
        self.assertEqual([row.requested_prompt_length for row in stopped.measurements], [1024])
        self.assertEqual([call["prompt"][0] for call in FakeNative.calls], [1024, 4096])

    def test_four_requests_overlap_and_keep_one_series(self):
        before = self.manager.store.get_profile(self.configuration.id).model_dump_json()
        run = self.wait(self.service.start(self.request(mode="concurrent", configurations=[{
            "configuration_id": self.configuration.id, "startup": {"ctx_size": 4096}, "concurrent_requests": 4}])).id)
        self.assertEqual(run.status, "completed", run.error)
        self.assertEqual(FakeNative.peak, 4)
        self.assertEqual(len(run.series), 1)
        self.assertEqual(len(run.measurements[0].samples), 4)
        self.assertTrue(all(call["exact"] for call in FakeNative.calls))
        self.assertEqual(self.manager.store.get_profile(self.configuration.id).model_dump_json(), before)
        self.assertEqual(self.manager.deployments.router.max_loaded_models(), 1)

    def test_distinct_saved_configurations_can_share_one_loaded_plan(self):
        other = self.manager.store.put_profile(self.configuration.model_copy(update={"id": "other-configuration", "display_name": "Another response setup"}))
        run = self.wait(self.service.start(self.request(mode="concurrent", configurations=[
            {"configuration_id": self.configuration.id}, {"configuration_id": other.id}])).id)
        self.assertEqual(run.status, "completed", run.error)
        self.assertEqual(len(run.series), 2)
        self.assertEqual(len({series.deployment_id for series in run.series}), 1)
        self.assertEqual(self.manager.prepare_lab_deployment.call_count, 1)
        self.assertTrue(all(series.startup["parallel"] == 2 for series in run.series))
        self.assertEqual(self.manager.get_deployment(run.series[0].deployment_id).applied_startup["parallel"], 2)
        self.assertEqual({row.series_id for row in run.measurements}, {series.id for series in run.series})

    def test_memory_finishes_each_depth_then_stop_skips_unstarted(self):
        FakeNative.block_depth = 25
        run = self.service.start(self.request(kind="memory", prompt_lengths=[], memory_test="multi_value"))
        self.assertTrue(FakeNative.entered.wait(5))
        finished = self.service.get_run(run.id)
        self.assertEqual([row.depth for row in finished.measurements], [0])
        self.assertTrue(finished.measurements[0].found)
        self.service.stop(run.id)
        self.assertEqual([row.depth for row in self.wait(run.id).measurements], [0])

    def test_missing_timings_fail_without_zero_measurement(self):
        async def broken(*args, **kwargs):
            return {"tokens_evaluated": 1024}
        with patch.object(FakeNative, "completion", broken):
            run = self.wait(self.service.start(self.request()).id)
        self.assertEqual(run.status, "failed")
        self.assertIn("context tokens", run.measurements[0].error)
        self.assertIsNone(run.measurements[0].generation_tps)

    def test_load_failure_stops_before_measurements(self):
        self.load_patch.stop()
        self.load_patch = patch.object(self.manager, "prepare_lab_deployment", side_effect=RuntimeError("out of memory"))
        self.load_patch.start()
        run = self.wait(self.service.start(self.request()).id)
        self.assertEqual(run.status, "failed")
        self.assertIn("out of memory", run.error)
        self.assertEqual(run.measurements, [])

    def test_context_and_controls_are_server_validated(self):
        with self.assertRaises(LabError):
            self.service.start(self.request(prompt_lengths=[16384]))
        with self.assertRaises(LabError):
            self.service.start(self.request(configurations=[{"configuration_id": self.configuration.id, "startup": {"host": "example.org"}}]))

    def test_auto_full_and_numeric_context_are_legal(self):
        for context in ("auto", 0, 3072):
            with self.subTest(context=context):
                run = self.wait(self.service.start(self.request(configurations=[{
                    "configuration_id": self.configuration.id, "startup": {"ctx_size": context}}])).id)
                self.assertEqual(run.status, "completed", run.error)
                self.assertEqual(run.series[0].requested_context_size, 3072 if context == 3072 else 8192)

    def test_stale_leave_only_stops_its_selected_owners(self):
        old = self.wait(self.service.start(self.request()).id)
        FakeNative.block_length = 4096
        current = self.service.start(self.request(prompt_lengths=[4096]))
        self.assertTrue(FakeNative.entered.wait(5))
        self.service.leave([old.id])
        self.assertEqual(self.service.get_run(current.id).status, "running")
        self.service.leave([current.id])
        self.assertEqual(self.wait(current.id).status, "stopped")

    def test_seed_only_once_add_many_and_snapshot_not_edited(self):
        seed = self.service.list_challenges()[0]
        request = self.request(kind="challenge", prompt_lengths=[], challenge_id=seed.id)
        # Exercise actual acceptance/snapshot while keeping model harness out of
        # this storage test. Shared harness tool security is tested separately.
        self.service._challenge = lambda *_: None
        run = self.wait(self.service.start(request).id)
        for index in range(51):
            self.service.save_challenge(ChallengeWrite(name=f"Case {index}", task="Say hello", required_text="hello"))
        self.assertEqual(len(self.service.list_challenges()), 52)
        self.service.save_challenge(ChallengeWrite(name=seed.name, task=seed.task, required_text="changed"), seed.id)
        self.assertEqual(self.service.get_run(run.id).challenge_snapshot.required_text, "lab-echo-ok")
        next_run = self.wait(self.service.start(request).id)
        self.assertEqual(next_run.challenge_snapshot.required_text, "changed")
        for challenge in self.service.list_challenges():
            self.service.delete_challenge(challenge.id)
        self.assertEqual(self.service.list_challenges(), [])
        with ApplicationStore(self.paths) as restored:
            self.assertEqual(restored.list_lab_challenges(), [])

    def test_real_harness_scoring_missing_tool_and_edited_check(self):
        seed = self.service.list_challenges()[0]
        responses = [AIMessage(content="lab-echo-ok")]
        harness = HarnessService(lambda: self.manager, app_store=self.store,
            model_factory=lambda _run, _sink: ScriptedChatModel(list(responses)))
        self.service._harness_provider = lambda: harness
        request = self.request(kind="challenge", prompt_lengths=[], challenge_id=seed.id)
        try:
            with patch.object(self.manager, "ensure_deployment_ready", side_effect=self.manager.get_deployment):
                no_tool = self.wait(self.service.start(request).id)
                self.assertEqual(no_tool.status, "completed", no_tool.error)
                self.assertFalse(no_tool.measurements[0].passed)
                self.assertEqual(no_tool.measurements[0].tool_calls, [])
                responses[:] = [AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "lab-echo-ok"}, "id": "echo-call"}]),
                                AIMessage(content="lab-echo-ok")]
                passed = self.wait(self.service.start(request).id)
                self.assertTrue(passed.measurements[0].passed, passed.model_dump())
                self.service.save_challenge(ChallengeWrite(name=seed.name, task=seed.task,
                    required_text="new-code", required_tool="echo"), seed.id)
                edited = self.wait(self.service.start(request).id)
                self.assertFalse(edited.measurements[0].passed)
                self.assertEqual(edited.measurements[0].missing, ["new-code"])
                retained = self.service.get_run(passed.id)
                self.assertTrue(retained.measurements[0].passed)
                self.assertEqual(retained.challenge_snapshot.required_text, "lab-echo-ok")
                self.assertEqual(self.store.list_conversations(), [])
        finally:
            harness.close()

    def test_intermediate_text_does_not_satisfy_final_answer(self):
        seed = self.service.list_challenges()[0]
        harness = HarnessService(lambda: self.manager, app_store=self.store,
            model_factory=lambda _run, _sink: ScriptedChatModel([
                AIMessage(content="I will echo lab-echo-ok", tool_calls=[{"name": "echo", "args": {"text": "lab-echo-ok"}, "id": "call"}]),
                AIMessage(content="Finished.")]))
        self.service._harness_provider = lambda: harness
        try:
            with patch.object(self.manager, "ensure_deployment_ready", side_effect=self.manager.get_deployment):
                run = self.wait(self.service.start(self.request(kind="challenge", prompt_lengths=[], challenge_id=seed.id)).id)
            self.assertFalse(run.measurements[0].passed)
            self.assertEqual(run.measurements[0].answer, "Finished.")
        finally:
            harness.close()


class NeedleTests(unittest.TestCase):
    def test_generated_shapes_and_exact_missing_values(self):
        single = needle_task("uuid")
        multi_key = needle_task("multi_key")
        multi_value = needle_task("multi_value")
        self.assertEqual(len(single.expected), 1)
        self.assertNotIn("code", single.filler)
        self.assertIn("Record 127: code", multi_key.filler)
        self.assertEqual(len(multi_value.expected), 4)
        text = needle_text(multi_value, 4096, 100)
        self.assertLess(text.index(multi_value.needle), text.index("Question:"))
        found, missing = score_needle(" ".join(multi_value.expected[:3]), multi_value.expected)
        self.assertFalse(found)
        self.assertEqual(missing, multi_value.expected[3:])

    def test_exact_native_flags_and_reported_lengths(self):
        from types import SimpleNamespace
        class Capture(NativeLabClient):
            async def post(self, deployment, route, body):
                self.body, self.route = body, route
                return sample(1008, 512)
        client = Capture(threading.Event())
        payload = asyncio.run(client.completion(SimpleNamespace(), [1, 2], 512, exact=True))
        self.assertEqual(client.route, "/completion")
        self.assertEqual(client.body["n_predict"], 512)
        self.assertTrue(client.body["ignore_eos"])
        self.assertFalse(client.body["cache_prompt"])
        result = timing_sample(payload, 512)
        self.assertEqual(result["prompt_tokens"], 1008)
        self.assertEqual(result["context_tokens"], 1519)
        with self.assertRaisesRegex(LabError, "not a complete speed sample"):
            timing_sample(sample(1008, 12), 512)


class LabOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.manager = ModelManager(self.paths)
        imported = self.manager.import_local(LocalImportRequest(source_path=str(write_tiny_gguf(Path(self.tmp.name) / "source.gguf"))))
        self.bundle_id = imported.bundle_id
        self.config = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Lab setup"))
        self.normal = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, profile_id=self.config.id, auto_start=False))

    def tearDown(self):
        self.manager.imports.close()
        self.tmp.cleanup()

    def test_overflow_uses_existing_loader_and_cleanup_is_exact(self):
        self.manager.store.put_setting("max-loaded-models", "1")
        def ready(ident):
            return self.manager.get_deployment(ident)
        with patch.object(self.manager, "managed_model_runtime", return_value={"loaded_deployment_ids": ["ordinary"], "loading_deployment_ids": [], "max_loaded_models": 1}), patch.object(self.manager, "ensure_deployment_ready", side_effect=ready):
            extra = self.manager.prepare_lab_deployment(self.config.id, {}, owner="bench", concurrent=True, deployment_id=self.normal.id)
        self.assertEqual(extra.benchmark_owner, "bench")
        self.assertNotEqual(extra.id, self.normal.id)
        self.assertNotIn(extra.id, self.manager.deployments.router._presets())
        self.assertEqual(self.manager.compatible_deployment(self.bundle_id, self.normal.settings).id, self.normal.id)
        with self.manager.reserve_deployment(self.normal.id), patch.object(self.manager.deployments, "_stop_locked") as stop:
            self.manager.release_lab_deployments("bench")
        stop.assert_called_once_with(extra.id)
        self.assertIsNotNone(self.manager.store.get_deployment(self.normal.id))
        self.assertIsNone(self.manager.store.get_deployment(extra.id))
        self.assertEqual(self.manager.deployments.router.max_loaded_models(), 1)

    def test_restart_releases_owned_extras_and_preserves_finished_records(self):
        extra = self.manager.store.put_deployment(self.normal.model_copy(update={"id": "extra", "benchmark_owner": "old-run"}))
        with ApplicationStore(self.paths) as store, patch.object(self.manager.deployments, "_stop_locked") as stop:
            service = LabWorkbenchService(lambda: self.manager, lambda: None, store)
            service.recover()
        stop.assert_called_once_with(extra.id)
        self.assertIsNotNone(self.manager.store.get_deployment(self.normal.id))

    def test_runtime_pin_stop_first_releases_extra_and_router(self):
        extra = self.manager.store.put_deployment(self.normal.model_copy(update={"id": "extra", "benchmark_owner": "old-run"}))
        with patch.object(self.manager.deployments, "reconcile"), patch.object(self.manager.deployments, "live_owned", return_value=[self.normal, extra]), \
             patch.object(self.manager.deployments, "_router_enabled", return_value=True), patch.object(self.manager.deployments, "_stop_locked") as stop, \
             patch.object(self.manager.deployments.router, "stop_router") as router_stop, patch.object(self.manager.runtime, "pin") as pin:
            self.manager.pin_runtime(PinRuntimeRequest(stop_first=True))
        stop.assert_called_once_with(extra.id)
        router_stop.assert_called_once()
        pin.assert_called_once()
        self.assertIsNone(self.manager.store.get_deployment(extra.id))

    def test_detached_stale_extra_does_not_block_restart(self):
        extra = self.manager.store.put_deployment(self.normal.model_copy(update={"id": "extra", "benchmark_owner": "old-run"}))
        with patch.object(self.manager.deployments, "_stop_locked", side_effect=ManagerError("Reused PID", code="process_identity_mismatch", status_code=409)):
            self.manager.release_lab_deployments()
        self.assertIsNone(self.manager.store.get_deployment(extra.id))

    def test_held_normal_model_cannot_be_unloaded_mid_measurement(self):
        router = self.manager.deployments.router
        router.hold_for_lab("bench", self.normal.id)
        with self.assertRaisesRegex(ManagerError, "Lab measurement"):
            router.stop(self.normal.id)
        with self.assertRaisesRegex(ManagerError, "Lab measurement"):
            router.set_max_loaded_models(2)
        router.release_lab_holds("other-bench")
        self.assertIn("bench", router._lab_holds)
        router.release_lab_holds("bench")
        self.assertEqual(router._lab_holds, {})


if __name__ == "__main__":
    unittest.main()
