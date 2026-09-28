"""Estimates remain advisory, bounded and separate from runtime authority."""
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

import httpx
import numpy as np
from gguf import GGUFWriter

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hardware import HardwareObserver
from workbench_backend.inference.memory_estimates import MemoryEstimator, IncompleteMetadata, parse_gguf_directory, dense_kv_bytes
from workbench_backend.inference.schemas import (HardwareDeviceMemory, HardwareMemoryObservation,
    LocalImportRequest, ModelEstimateRequest, HuggingFaceImportRequest, ImportJob, BundleSourceKind, ImportStatus)
from workbench_backend.inference.schemas import RuntimeManifest
from workbench_backend.inference.schemas import Deployment, HealthReport
from workbench_backend.inference.configurations import loaded_model_identity
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import resolve_bags, startup_cli_args
from workbench_backend.paths import WorkbenchPaths


def dense_fields():
    return {"general.architecture": "llama", "llama.block_count": 2, "llama.context_length": 16384,
        "llama.embedding_length": 256, "llama.attention.head_count": 8, "llama.attention.head_count_kv": 2}


def native_result(*, context=4096, parallel=4, unified=True, projector="not_selected", speculation="not_selected"):
    unit = 1024**2
    return json.dumps({"protocol": 1, "native_build": 11045, "native_commit": "2b1847030",
        "native_fingerprint": "native", "completeness": "partial" if "unavailable" in (projector, speculation) else "complete",
        "components": {"target": "measured", "projector": projector, "speculation": speculation},
        "unknown_reasons": ["Projector allocation is unknown."] if projector == "unavailable" else [],
        "devices": [
            {"id": "CUDA0", "weights_bytes": unit, "kv_bytes": 0, "runtime_overhead_bytes": 2*unit,
             "projector_bytes": None if projector == "unavailable" else unit if projector == "measured" else 0,
             "speculation_bytes": None if speculation == "unavailable" else 0,
             "total_bytes": None if "unavailable" in (projector, speculation) else (4 if projector == "measured" else 3)*unit},
            {"id": "Host", "weights_bytes": 3*unit, "kv_bytes": 4*unit, "runtime_overhead_bytes": unit,
             "projector_bytes": None if projector == "unavailable" else 0,
             "speculation_bytes": None if speculation == "unavailable" else 0,
             "total_bytes": None if "unavailable" in (projector, speculation) else 8*unit}],
        "evaluated_startup": {"ctx_size": context, "n_gpu_layers": 4, "parallel": parallel, "kv_unified": unified},
        "effective_context": context, "effective_context_per_slot": context if unified else context//parallel,
        "effective_parallel": parallel, "kv_unified": unified, "context_maximum": 16384})


class MemoryEstimateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(self.root / "data"))
        self.hardware = HardwareMemoryObservation(observed_at="2026-09-27T12:00:00Z", source="fixture",
            gpu_devices=[HardwareDeviceMemory(id="GPU-1", name="GPU", total_bytes=8*1024**3, available_bytes=1024**3)],
            ram_total_bytes=16*1024**3, ram_available_bytes=8*1024**3)
        self.manager.memory_estimator.hardware.observe = lambda **kwargs: self.hardware

    def native_manifest(self):
        return RuntimeManifest(platform="win-x64", flavor="cuda-13.4", release_tag="b11045",
            install_dir=str(self.root), executable=str(self.root/"llama-server.exe"), sha256="runtime",
            memory_planner_path=str(self.root/"workbench-memory-planner.exe"), memory_planner_sha256="helper",
            memory_planner_protocol=1, memory_planner_native_fingerprint="native")

    def model(self, *, extra_array_key=None):
        path = self.root / "model.gguf"
        writer = GGUFWriter(str(path), "llama")
        for key, value in dense_fields().items():
            if key != "general.architecture":
                writer.add_uint32(key, value)
        if extra_array_key:
            writer.add_array(extra_array_key, [1024, 2048])
        writer.add_tensor("token_embd.weight", np.zeros((4, 32), dtype=np.float32))
        writer.write_header_to_file(); writer.write_kv_data_to_file(); writer.write_tensors_to_file(); writer.close()
        return path

    def test_metadata_cache_sizes_use_native_quant_block_sizes(self):
        self.assertEqual(dense_kv_bytes(dense_fields(), 1024, "f16", "f16"), 524288)
        self.assertEqual(dense_kv_bytes(dense_fields(), 1024, "q8_0", "q8_0"), 278528)
        fields = {**dense_fields(), "llama.attention.sliding_window": 4096}
        self.assertIsNone(dense_kv_bytes(fields, 1024, "f16", "f16"))
        self.assertEqual(dense_kv_bytes({**dense_fields(), "llama.attention.sliding_window": 0}, 1024, "f16", "f16"), 524288)
        self.assertIsNone(dense_kv_bytes({**dense_fields(), "general.architecture":"qwen35"}, 1024, "f16", "f16"))

    def test_array_valued_layout_marker_never_looks_like_dense_cache(self):
        fields, _ = parse_gguf_directory(self.model(extra_array_key="llama.attention.sliding_window").read_bytes())
        self.assertIn("llama.attention.sliding_window", fields)
        self.assertIsNone(dense_kv_bytes(fields, 1024, "f16", "f16"))

    def test_directory_parser_never_needs_tensor_data(self):
        payload = self.model().read_bytes()
        fields, size = parse_gguf_directory(payload)
        self.assertEqual(fields["llama.block_count"], 2)
        self.assertEqual(size, 512)
        self.assertEqual(parse_gguf_directory(payload[:-512])[1], 512)
        with self.assertRaises(IncompleteMetadata):
            parse_gguf_directory(payload[:12])

    def test_unsupported_architecture_and_shortage_do_not_block_settings(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        startup = {"ctx_size":16384, "cache_type_k":"f16", "kv_offload":False}
        with patch.object(self.manager.memory_estimator, "_native_prediction", side_effect=ValueError("fixture has no native helper")):
            result = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, startup=startup))
        self.assertEqual(result.selected_startup, startup)
        self.assertEqual(result.ram_bytes, result.kv_bytes)
        self.assertIsNone(result.context_marker)
        self.assertIsNone(result.runtime_overhead_bytes)
        self.assertFalse(self.manager.list_deployments())

    def test_kv_placement_is_canonical_and_never_changes_weight_offload(self):
        bags = resolve_bags(startup={"kv_offload":False, "n_gpu_layers":8})
        argv = startup_cli_args(bags.startup.applied)
        self.assertIn("--no-kv-offload", argv)
        self.assertEqual(bags.startup.applied["n_gpu_layers"], 8)
        self.assertIn("--kv-offload", startup_cli_args(resolve_bags(startup={"kv_offload":True}).startup.applied))
        self.assertIn("kv_offload", resolve_bags(startup={"kv_offload":"somewhere"}).startup.unsupported)

    def test_native_prediction_preserves_requested_and_never_creates_deployment(self):
        path = self.model()
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(path))).bundle_id
        manifest = self.native_manifest()
        startup = {"ctx_size":4096, "n_gpu_layers":4, "kv_offload":False}
        with patch.object(self.manager.runtime, "current", return_value=manifest), \
             patch("workbench_backend.inference.memory_estimates.require_planner", return_value=Path(manifest.memory_planner_path)), \
             patch("workbench_backend.inference.memory_estimates._bounded_native", return_value=native_result()) as native:
            with patch("workbench_backend.inference.memory_estimates.utc_now", return_value="2026-09-27T12:00:00Z"):
                first = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, startup=startup))
            with patch("workbench_backend.inference.memory_estimates.utc_now", return_value="2026-09-27T12:00:10Z"):
                second = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, startup=startup))
        self.assertEqual(first.source, "native_prediction")
        self.assertEqual(first.selected_startup, startup)
        self.assertEqual(first.ram_bytes, 8 * 1024**2)
        self.assertEqual(first.gpu_bytes, 3 * 1024**2)
        self.assertEqual(native.call_count, 1)
        self.assertIn("--no-kv-offload", native.call_args.args[0])
        self.assertEqual(first.evaluated_startup["parallel"], 4)
        self.assertTrue(first.kv_unified)
        self.assertEqual(first.completeness, "complete")
        self.assertIn("Simultaneous requests share", " ".join(first.assumptions))
        self.assertIn("Dynamic driver", " ".join(first.unknown_reasons))
        self.assertEqual(second.devices, first.devices)
        self.assertEqual(second.estimated_at, first.estimated_at, "A cached prediction must retain its original time")
        self.assertFalse(self.manager.list_deployments())

    def test_native_explicit_and_automatic_parallel_return_actual_pool_and_per_chat_capacity(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        manifest = self.native_manifest()
        with patch.object(self.manager.runtime, "current", return_value=manifest), \
             patch("workbench_backend.inference.memory_estimates.require_planner", return_value=Path(manifest.memory_planner_path)), \
             patch("workbench_backend.inference.memory_estimates._bounded_native",
                side_effect=[native_result(context=16384, parallel=2, unified=False),
                             native_result(context=16384)]) as native:
            explicit = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id,
                startup={"parallel": 2, "kv_unified": False}))
            automatic = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id,
                startup={}))
        self.assertEqual(explicit.evaluated_startup["parallel"], 2)
        self.assertEqual(explicit.effective_context, 16384)
        self.assertEqual(explicit.context_marker, 8192)
        self.assertEqual(automatic.evaluated_startup["parallel"], 4)
        self.assertEqual(automatic.context_marker, 16384)
        self.assertEqual(automatic.selected_startup, {})
        self.assertIn("--parallel", native.call_args_list[0].args[0])

    def test_remote_ranges_are_bounded_and_ignored_range_aborts_before_body(self):
        client = Mock()
        response = Mock(status_code=200, headers={})
        client.stream.return_value.__enter__ = Mock(return_value=response)
        client.stream.return_value.__exit__ = Mock(return_value=False)
        with patch("workbench_backend.inference.memory_estimates.httpx.Client", return_value=client) as clients:
            clients.return_value.__enter__ = Mock(return_value=client)
            clients.return_value.__exit__ = Mock(return_value=False)
            with self.assertRaisesRegex(ValueError, "bounded"):
                self.manager.memory_estimator._remote_directories("org/model", "a"*40, ["model.gguf"], False)
        response.iter_bytes.assert_not_called()

    def test_native_predictor_survives_metadata_budget_and_omitted_layers_remain_auto(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        manifest = self.native_manifest()
        startup = {"ctx_size": 4096, "kv_offload": False}
        with patch.object(self.manager.runtime, "current", return_value=manifest), \
             patch("workbench_backend.inference.memory_estimates.require_planner", return_value=Path(manifest.memory_planner_path)), \
             patch.object(self.manager.memory_estimator, "_local_directory", side_effect=ValueError("Metadata budget exceeded")), \
             patch("workbench_backend.inference.memory_estimates._bounded_native",
                 return_value=native_result()) as native:
            result = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, startup=startup))
        self.assertEqual(result.source, "native_prediction")
        self.assertEqual(result.selected_startup, startup)
        self.assertEqual(result.evaluated_startup["n_gpu_layers"], 4)
        self.assertEqual(native.call_count, 1)
        argv = native.call_args.args[0]
        self.assertEqual(argv[argv.index("--n-gpu-layers") + 1], "auto")
        self.assertFalse(self.manager.list_deployments())

    def test_complete_projector_is_added_once_and_unknown_component_never_becomes_a_total(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        manifest = self.native_manifest()
        with patch.object(self.manager.runtime, "current", return_value=manifest), \
             patch("workbench_backend.inference.memory_estimates.require_planner", return_value=Path(manifest.memory_planner_path)), \
             patch("workbench_backend.inference.memory_estimates._bounded_native", side_effect=[
                 native_result(projector="measured"), native_result(projector="unavailable")]):
            complete = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id))
            partial = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, refresh=True))
        self.assertEqual(complete.projector_bytes, 1024**2)
        self.assertEqual(complete.gpu_bytes, 4*1024**2)
        self.assertEqual(partial.completeness, "partial")
        self.assertIsNone(partial.projector_bytes)
        self.assertIsNone(partial.gpu_bytes)
        self.assertIsNone(partial.ram_bytes)
        self.assertIsNone(partial.context_marker)

    def test_runtime_identity_mismatch_is_unavailable_and_keeps_the_selected_draft(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        manifest = self.native_manifest()
        bad = json.loads(native_result())
        bad["native_fingerprint"] = "different-runtime"
        startup = {"ctx_size":4096}
        with patch.object(self.manager.runtime, "current", return_value=manifest), \
             patch("workbench_backend.inference.memory_estimates.require_planner", return_value=Path(manifest.memory_planner_path)), \
             patch("workbench_backend.inference.memory_estimates._bounded_native", return_value=json.dumps(bad)):
            result = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, startup=startup))
        self.assertEqual(result.completeness, "unavailable")
        self.assertEqual(result.selected_startup, startup)
        self.assertEqual(result.source, "metadata")
        self.assertFalse(self.manager.list_deployments())

    def test_observation_matches_exact_loading_identity_and_ignores_response_choice(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        bundle = self.manager.get_bundle(bundle_id)
        startup = {"ctx_size":4096}
        bags = resolve_bags(startup=startup,per_request={"temperature":0.3})
        deployment = Deployment(id="live",display_name="Fixture",scope="managed",status="running",
            bundle_id=bundle_id,created_at="now",updated_at="observed",settings=bags,applied_startup=bags.startup.applied,
            health=HealthReport(healthy=True,checked="observed"),
            loaded_model_identity=loaded_model_identity(None,bundle,bags))
        self.manager.store.put_deployment(deployment)
        with patch.object(self.manager.memory_estimator,"_native_prediction",side_effect=ValueError("fixture")):
            exact = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id,startup=startup))
            other = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id,startup={"ctx_size":8192}))
        self.assertEqual(exact.observed_runtime["deployment_id"],"live")
        self.assertEqual(exact.observed_runtime["observed_at"],"observed")
        self.assertEqual(exact.observed_runtime["plan_identity"],exact.plan_identity)
        self.assertIsNone(other.observed_runtime)

    def test_current_runtime_cannot_prove_an_unbound_or_previous_runtime_observation(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        bundle = self.manager.get_bundle(bundle_id)
        startup = {"ctx_size": 4096}
        bags = resolve_bags(startup=startup)
        previous = self.native_manifest()
        current = previous.model_copy(update={"sha256": "replaced-runtime"})
        previous_identity = loaded_model_identity(previous, bundle, bags)
        candidate_identity = loaded_model_identity(current, bundle, bags)
        self.assertNotEqual(previous_identity, candidate_identity)
        for recorded_identity in (None, previous_identity):
            with self.subTest(recorded_identity=recorded_identity):
                self.manager.store.put_deployment(Deployment(id="live", display_name="Previous runtime",
                    scope="managed", status="running", bundle_id=bundle_id, created_at="before",
                    updated_at="observed", settings=bags, applied_startup=bags.startup.applied,
                    health=HealthReport(healthy=True, checked="observed"),
                    loaded_model_identity=recorded_identity))
                with patch.object(self.manager.runtime, "current", return_value=current), \
                        patch.object(self.manager.memory_estimator, "_native_prediction", side_effect=ValueError("fixture")):
                    result = self.manager.memory_estimator.estimate(ModelEstimateRequest(bundle_id=bundle_id, startup=startup))
                self.assertEqual(result.plan_identity, candidate_identity)
                self.assertIsNone(result.observed_runtime)

    def test_remote_success_is_cached_at_immutable_file_identity(self):
        payload = self.model().read_bytes()
        response = httpx.Response(206, headers={"Content-Range": f"bytes 0-{len(payload)-1}/{len(payload)}"}, content=payload,
            request=httpx.Request("GET", "https://huggingface.co/org/model"))
        transport = httpx.MockTransport(lambda request: response)
        original_client = httpx.Client
        with patch("workbench_backend.inference.memory_estimates.httpx.Client", side_effect=lambda **kwargs: original_client(transport=transport, **kwargs)):
            first = self.manager.memory_estimator._remote_directories("org/model", "a"*40, ["model.gguf"], False)
        with patch("workbench_backend.inference.memory_estimates.httpx.Client", side_effect=AssertionError("cached lookup must not transfer")):
            second = self.manager.memory_estimator._remote_directories("org/model", "a"*40, ["model.gguf"], False)
        self.assertEqual(first, second)

    def test_selected_shards_aggregate_tensor_bytes_without_pooling_gpu_budgets(self):
        payload = self.model().read_bytes()
        requests = []
        def ranged(request):
            requests.append(request.headers["range"])
            return httpx.Response(206, headers={"Content-Range": f"bytes 0-{len(payload)-1}/{len(payload)}"},
                content=payload, request=request)
        original_client = httpx.Client
        with patch("workbench_backend.inference.memory_estimates.httpx.Client", side_effect=lambda **kwargs:
                original_client(transport=httpx.MockTransport(ranged), **kwargs)):
            fields, weights = self.manager.memory_estimator._remote_directories("org/model", "a"*40,
                ["model-00001-of-00002.gguf", "model-00002-of-00002.gguf"], False)
        self.assertEqual(weights, 1024)
        self.assertEqual(fields["general.architecture"], "llama")
        self.assertEqual(len(requests), 2)
        self.hardware.gpu_devices.append(HardwareDeviceMemory(id="GPU-2", name="Second",
            total_bytes=8*1024**3, available_bytes=1024**3))
        from workbench_backend.inference.schemas import ModelMemoryEstimate
        result = ModelMemoryEstimate(source_identity="shards", estimated_at="now", hardware=self.hardware,
            weights_bytes=weights, projector_disk_bytes=0)
        self.manager.memory_estimator._metadata_prediction(fields, {"ctx_size": 4096}, result)
        self.assertIsNone(result.context_marker)
        self.assertIsNone(result.gpu_bytes, "Two devices must not become one fabricated placement")

    def test_remote_budget_is_aggregate_and_stops_before_another_range_request(self):
        requests = []
        chunk = bytes(1024**2)
        def ranged(request):
            start, end = (int(value) for value in request.headers["range"][6:].split("-"))
            requests.append((start, end))
            return httpx.Response(206, headers={"Content-Range": f"bytes {start}-{end}/{32*1024**2}"},
                content=chunk, request=request)
        original_client = httpx.Client
        with patch("workbench_backend.inference.memory_estimates.httpx.Client", side_effect=lambda **kwargs:
                original_client(transport=httpx.MockTransport(ranged), **kwargs)), \
             patch("workbench_backend.inference.memory_estimates.parse_gguf_directory", side_effect=IncompleteMetadata("directory incomplete")):
            with self.assertRaisesRegex(ValueError, "inspection budget"):
                self.manager.memory_estimator._remote_directories("org/model", "a"*40, ["huge.gguf"], False)
        self.assertEqual(len(requests), 16)
        self.assertEqual(sum(end - start + 1 for start, end in requests), 16 * 1024**2)

    def test_slow_headers_receive_remaining_budget_and_timeout_stops_ranges(self):
        clock = [0.0]
        timeouts = []
        chunk = bytes(1024**2)
        def ranged(request):
            timeout = request.extensions["timeout"]
            timeouts.append(timeout)
            if timeout["read"] < 4.9:
                clock[0] += timeout["read"]
                raise httpx.ReadTimeout("Slow headers exhausted remaining budget", request=request)
            clock[0] += 4.9
            start, end = (int(value) for value in request.headers["range"][6:].split("-"))
            return httpx.Response(206, headers={"Content-Range": f"bytes {start}-{end}/{32*1024**2}"},
                content=chunk, request=request)
        original_client = httpx.Client
        with patch("workbench_backend.inference.memory_estimates.httpx.Client", side_effect=lambda **kwargs:
                original_client(transport=httpx.MockTransport(ranged), **kwargs)), \
             patch("workbench_backend.inference.memory_estimates.time.monotonic", side_effect=lambda: clock[0]), \
             patch("workbench_backend.inference.memory_estimates.parse_gguf_directory", side_effect=IncompleteMetadata("more directory")):
            with self.assertRaises(httpx.ReadTimeout):
                self.manager.memory_estimator._remote_directories("org/model", "a"*40, ["huge.gguf"], False)
        self.assertEqual(len(timeouts), 4, "A timeout must not begin another range request")
        self.assertEqual(timeouts[0]["connect"], 3)
        self.assertEqual(timeouts[0]["read"], 5)
        for value in timeouts[-1].values():
            self.assertAlmostEqual(value, 0.3)
        self.assertAlmostEqual(clock[0], 15.0)

    def test_context_marker_excludes_stale_or_projector_budgets_and_overhead_stays_unknown(self):
        from workbench_backend.inference.schemas import ModelMemoryEstimate
        for stale, projector, expected in ((False, 0, True), (True, 0, False), (False, 1024, False)):
            result = ModelMemoryEstimate(source_identity="fixture", estimated_at="now", weights_bytes=512,
                projector_disk_bytes=projector, hardware=self.hardware.model_copy(update={"stale": stale}))
            self.manager.memory_estimator._metadata_prediction(dense_fields(), {"ctx_size": 4096}, result)
            self.assertEqual(result.context_marker is not None, expected)
            self.assertIsNone(result.runtime_overhead_bytes)
            if expected:
                self.assertEqual(result.context_marker_kind, "upper_bound")
                self.assertIn("excludes unknown overhead", " ".join(result.assumptions))

    def test_explicit_layer_placement_does_not_claim_full_gpu_budget(self):
        from workbench_backend.inference.schemas import ModelMemoryEstimate
        for cpu_kv in (False, True):
            result = ModelMemoryEstimate(source_identity="fixture", estimated_at="now", weights_bytes=512,
                projector_disk_bytes=0, hardware=self.hardware)
            self.manager.memory_estimator._metadata_prediction(dense_fields(),
                {"ctx_size": 4096, "n_gpu_layers": 1, "kv_offload": not cpu_kv}, result)
            self.assertIsNone(result.context_marker)
            self.assertIsNone(result.gpu_bytes)
            self.assertIsNone(result.runtime_overhead_bytes)
            self.assertEqual(result.ram_bytes, result.kv_bytes if cpu_kv else None)
            self.assertIn("Explicit layer placement", " ".join(result.unknown_reasons))

    def test_import_initial_settings_survive_configuration_recovery(self):
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.model()))).bundle_id
        bundle = self.manager.store.get_bundle(bundle_id)
        startup = {"ctx_size":16384, "cache_type_k":"q8_0", "cache_type_v":"q8_0", "kv_offload":False}
        job = ImportJob(id="chosen", kind=BundleSourceKind.huggingface, status=ImportStatus.complete, created_at="now", initial_startup=startup)
        self.manager.imports._create_initial_configuration(job, bundle)
        first = self.manager.list_model_configurations(bundle_id)
        self.manager.imports._create_initial_configuration(job, bundle)
        self.assertEqual(first, self.manager.list_model_configurations(bundle_id))
        selected = self.manager.store.get_bundle(bundle_id).default_configuration_id
        self.assertEqual(self.manager.store.get_profile(selected).bags.startup.requested, startup)


class HardwareTelemetryTests(unittest.TestCase):
    def test_each_gpu_has_its_own_budget_and_unavailable_telemetry_is_unknown(self):
        output = SimpleNamespace(returncode=0, stdout="GPU-one, First, 8192, 4096\nGPU-two, Second, 4096, 2048\n")
        with patch("workbench_backend.inference.hardware.shutil.which", return_value="nvidia-smi"), patch("workbench_backend.inference.hardware.subprocess.run", return_value=output) as run:
            observer = HardwareObserver()
            observation = observer.observe()
            observer.observe()
        self.assertEqual(len(observation.gpu_devices), 2)
        self.assertEqual(observation.gpu_devices[1].available_bytes, 2048*1024**2)
        self.assertEqual(run.call_count, 1)
        with patch("workbench_backend.inference.hardware.shutil.which", return_value="nvidia-smi"), patch("workbench_backend.inference.hardware.subprocess.run", side_effect=OSError("unavailable")):
            stale = observer.observe(refresh=True)
        self.assertTrue(stale.stale)
        self.assertEqual(stale.observed_at, observation.observed_at)
        self.assertTrue(stale.reasons)


if __name__ == "__main__":
    unittest.main()
