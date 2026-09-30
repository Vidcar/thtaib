"""Live system reads share Models' observer without acquiring model authority."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.support import close_workbench_sqlite, workbench_client
from workbench_backend.app import create_app
from workbench_backend.inference.hardware import HardwareObserver
from workbench_backend.inference.schemas import HardwareMemoryObservation

MIB = 1024**2
GIB = 1024**3


class SystemHardwareTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.ram = SimpleNamespace(total=64*GIB, available=32*GIB)
        self.output = SimpleNamespace(returncode=0, stdout="GPU-one, First GPU, 8192, 4096, 3900\nGPU-two, Second GPU, 4096, 1024, 3000\n")
        self.run = self.enterContext(patch("workbench_backend.inference.hardware.subprocess.run", return_value=self.output))
        self.enterContext(patch("workbench_backend.inference.hardware.shutil.which", return_value="nvidia-smi"))
        self.memory = self.enterContext(patch("workbench_backend.inference.hardware.psutil.virtual_memory", side_effect=lambda: self.ram))
        self.enterContext(patch("workbench_backend.inference.hardware.time.monotonic", side_effect=lambda: self.now))
        self.enterContext(patch("workbench_backend.inference.hardware.utc_now", side_effect=lambda: (datetime(2026, 9, 30, tzinfo=timezone.utc)+timedelta(seconds=self.now)).isoformat()))
        self.observer = HardwareObserver()

    def test_reported_used_is_not_total_minus_available(self):
        data = self.observer.observe()
        gpu = data.gpu_devices[0]
        self.assertEqual(gpu.used_bytes, 3900*MIB)
        self.assertEqual(gpu.available_bytes, 4096*MIB)
        self.assertNotEqual(gpu.used_bytes, gpu.total_bytes-gpu.available_bytes)
        self.assertEqual(data.ram_available_bytes, 32*GIB)
        self.assertFalse(data.gpu_stale)
        self.assertFalse(data.ram_stale)
        self.assertIn("memory.used", self.run.call_args.args[0][1])
        self.assertEqual(self.run.call_args.kwargs["timeout"], 2)

    def test_live_and_models_consumers_share_cache_and_return_independent_copies(self):
        first = self.observer.observe()
        first.gpu_devices[0].available_bytes = 0
        self.now += 1.9
        self.assertEqual(self.observer.observe(max_age=2).gpu_devices[0].available_bytes, 4096*MIB)
        self.assertEqual(self.run.call_count, 1)
        self.now += .2
        self.observer.observe()  # Existing Models callers retain their five-second budget.
        self.assertEqual(self.run.call_count, 1)
        self.observer.observe(max_age=2)
        self.assertEqual(self.run.call_count, 2)
        self.observer.observe()
        self.assertEqual(self.run.call_count, 2)

    def test_gpu_failure_dates_retained_gpu_but_ram_is_current_and_recovers(self):
        first = self.observer.observe()
        self.now += 3
        self.run.side_effect = TimeoutExpired("nvidia-smi", 2)
        self.ram = SimpleNamespace(total=64*GIB, available=20*GIB)
        failed = self.observer.observe(max_age=2)
        self.assertTrue(failed.stale)
        self.assertTrue(failed.gpu_stale)
        self.assertFalse(failed.ram_stale)
        self.assertEqual(failed.observed_at, first.observed_at)
        self.assertEqual(failed.gpu_observed_at, first.gpu_observed_at)
        self.assertGreater(failed.ram_observed_at, first.ram_observed_at)
        self.assertEqual(failed.gpu_devices, first.gpu_devices)
        self.assertEqual(failed.ram_available_bytes, 20*GIB)
        self.now += 3
        self.run.side_effect = None
        recovered = self.observer.observe(max_age=2)
        self.assertFalse(recovered.stale)
        self.assertFalse(recovered.gpu_stale)
        self.assertGreater(recovered.gpu_observed_at, first.gpu_observed_at)

    def test_ram_failure_does_not_turn_retained_ram_into_a_fresh_models_budget(self):
        first = self.observer.observe()
        self.now += 3
        self.memory.side_effect = OSError("unavailable")
        failed = self.observer.observe(max_age=2)
        self.assertFalse(failed.gpu_stale)
        self.assertTrue(failed.ram_stale)
        self.assertIsNone(failed.ram_total_bytes)
        self.assertIsNone(failed.ram_available_bytes)
        self.assertEqual(failed.ram_observed_at, first.ram_observed_at)
        self.assertGreater(failed.gpu_observed_at, first.gpu_observed_at)

    def test_unknown_used_keeps_valid_available_memory_for_models(self):
        self.output.stdout = "GPU-one, First GPU, 8192, 4096, N/A\n"
        result = self.observer.observe()
        self.assertFalse(result.stale)
        self.assertTrue(result.gpu_stale)
        self.assertIsNone(result.gpu_observed_at)
        self.assertEqual(result.gpu_devices[0].available_bytes, 4096*MIB)
        self.assertIsNone(result.gpu_devices[0].used_bytes)

    def test_missing_tool_leaves_ram_usable_without_zero_gpu(self):
        with patch("workbench_backend.inference.hardware.shutil.which", return_value=None), patch("workbench_backend.inference.hardware.Path.is_file", return_value=False):
            result = self.observer.observe()
        self.assertEqual(result.gpu_devices, [])
        self.assertTrue(result.gpu_stale)
        self.assertFalse(result.ram_stale)
        self.run.assert_not_called()

    def test_malformed_gpu_quantities_never_become_valid_readings(self):
        for value in ["N/A", "nan", "inf", "-1", "999999999"]:
            with self.subTest(value=value):
                self.output.stdout = f"GPU-one, First GPU, 8192, 4096, {value}\n"
                result = self.observer.observe(refresh=True)
                self.assertTrue(result.gpu_stale)
                self.assertIsNone(result.gpu_devices[0].used_bytes)
                self.assertEqual(result.gpu_devices[0].available_bytes, 4096*MIB)
        self.output.stdout = "bad row\n"
        result = HardwareObserver().observe()
        self.assertEqual(result.gpu_devices, [])
        self.assertTrue(result.gpu_stale)

    def test_zero_and_full_gpu_usage_are_valid_but_zero_total_is_unknown(self):
        for used in [0, 8192]:
            self.output.stdout = f"GPU-one, First GPU, 8192, 0, {used}\n"
            result = self.observer.observe(refresh=True)
            self.assertEqual(result.gpu_devices[0].used_bytes, used*MIB)
            self.assertFalse(result.gpu_stale)
        self.output.stdout = "GPU-one, First GPU, 0, 0, 0\n"
        result = self.observer.observe(refresh=True)
        self.assertTrue(result.gpu_stale)
        self.assertIsNone(result.gpu_devices[0].total_bytes)

    def test_partial_gpu_row_failure_does_not_claim_a_complete_current_usage(self):
        first = self.observer.observe()
        self.now += 3
        self.output.stdout = "GPU-one, First GPU, 8192, 4096, 3900\nGPU-two, Second GPU, 4096, 1024\n"
        failed = self.observer.observe(max_age=2)
        self.assertTrue(failed.gpu_stale)
        self.assertEqual(failed.gpu_observed_at, first.gpu_observed_at)
        self.assertFalse(failed.ram_stale)
        self.assertGreater(failed.ram_observed_at, first.ram_observed_at)
        self.assertFalse(failed.stale)  # Valid free-memory facts retain Models' budget semantics.
        self.assertEqual(failed.gpu_devices[0].available_bytes, 4096*MIB)
        self.assertEqual(failed.gpu_devices[1].available_bytes, 1024*MIB)
        self.now += 3
        self.output.stdout = self.output.stdout.rstrip("\n") + ", 3000\n"
        recovered = self.observer.observe(max_age=2)
        self.assertFalse(recovered.gpu_stale)
        self.assertGreater(recovered.gpu_observed_at, first.gpu_observed_at)

    def test_unrecoverable_partial_gpu_rows_cannot_be_a_current_single_gpu_budget(self):
        first = self.observer.observe()
        self.now += 3
        self.output.stdout = "GPU-one, First GPU, 8192, 4096, 3900\nbad row\n"
        failed = self.observer.observe(max_age=2)
        self.assertTrue(failed.stale)
        self.assertTrue(failed.gpu_stale)
        self.assertEqual(failed.gpu_observed_at, first.gpu_observed_at)
        self.assertEqual(failed.observed_at, first.observed_at)
        self.assertFalse(failed.ram_stale)

    def test_bad_ram_quantities_are_unavailable(self):
        for total, available in [(0, 0), (100, -1), (100, 101)]:
            self.ram = SimpleNamespace(total=total, available=available)
            result = self.observer.observe(refresh=True)
            self.assertTrue(result.ram_stale)
            self.assertIsNone(result.ram_total_bytes)
            self.assertIsNone(result.ram_available_bytes)

    def test_concurrent_readers_share_one_probe(self):
        barrier = threading.Barrier(8)
        def observe(_index):
            barrier.wait(timeout=5)
            return self.observer.observe(max_age=2)
        with ThreadPoolExecutor(max_workers=8) as executor:
            answers = list(executor.map(observe, range(8)))
        self.assertEqual(len(answers), 8)
        self.assertEqual(self.run.call_count, 1)
        self.assertTrue(all(answer.gpu_devices[0].used_bytes == 3900*MIB for answer in answers))


class SystemResourceRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app(data_root=Path(self.tmp.name))
        self.client = workbench_client(self.app)
        self.addCleanup(lambda: close_workbench_sqlite(self.app, self.client))

    def test_authentication_precedes_observation_and_read_has_no_model_side_effect(self):
        snapshot = HardwareMemoryObservation(observed_at="2026-09-30T00:00:00Z", source="fixture", ram_total_bytes=64*GIB,
            ram_available_bytes=32*GIB, ram_observed_at="2026-09-30T00:00:00Z", gpu_stale=True)
        manager = self.app.state.manager
        with patch.object(manager.memory_estimator.hardware, "observe", return_value=snapshot) as observe, patch.object(manager.memory_estimator, "estimate", side_effect=AssertionError("must not estimate")) as estimate:
            with TestClient(self.app) as anonymous:
                self.assertEqual(anonymous.get("/v1/system/resources").status_code, 401)
                self.assertEqual(anonymous.get("/v1/system/resources", headers={"X-Workbench-Local-Token": "wrong"}).status_code, 403)
            observe.assert_not_called()
            response = self.client.get("/v1/system/resources")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["ram_available_bytes"], 32*GIB)
            self.assertTrue(response.json()["gpu_stale"])
            observe.assert_called_once_with(max_age=2.0)
            estimate.assert_not_called()
            self.assertEqual(manager.list_deployments(), [])


if __name__ == "__main__":
    unittest.main()
