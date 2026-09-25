from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from gguf import GGUFWriter
from pathlib import Path

from workbench_backend.app import create_app
from workbench_backend.errors import ManagerError
from workbench_backend.inference.inspect import inspect_gguf_file
from workbench_backend.inference.inspect import read_gguf_runtime_metadata
from workbench_backend.inference.configuration_options import bundle_configuration_options
from workbench_backend.inference.schemas import GgufRuntimeMetadata
from workbench_backend.inference.schemas import LocalImportRequest, ManagedDeploymentRequest, ServerProperties
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import close_workbench_sqlite, workbench_client, write_tiny_gguf
from test_app import FakeHF


def set_first_tensor_type(path: Path, tensor_type: int) -> None:
    data = bytearray(path.read_bytes())
    marker = b"token_embd.weight"
    name_at = data.index(marker)
    cursor = name_at + len(marker)
    dims = int.from_bytes(data[cursor : cursor + 4], "little")
    cursor += 4 + (8 * dims)
    data[cursor : cursor + 4] = int(tensor_type).to_bytes(4, "little")
    path.write_bytes(data)


class BundleConfigurationOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths, hf=FakeHF(error=RuntimeError("boom")))
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.client = workbench_client(self.app)
        self.bundle_count = 0

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _bundle(
        self,
        *,
        context_length: int = 262144,
        block_count: int = 65,
        extra_uint32: dict[str, int] | None = None,
    ) -> str:
        self.bundle_count += 1
        gguf = write_tiny_gguf(
            self.root / "incoming" / f"tiny-options-{self.bundle_count}.gguf",
            context_length=context_length,
            block_count=block_count,
            extra_uint32=extra_uint32,
        )
        job = self.manager.import_local(LocalImportRequest(source_path=str(gguf)))
        return job.bundle_id or ""

    def test_context_and_gpu_options_come_from_gguf_metadata(self) -> None:
        bundle_id = self._bundle()
        body = self.client.get(f"/v1/bundles/{bundle_id}/configuration-options").json()

        self.assertEqual(body["bundle_id"], bundle_id)
        self.assertEqual(body["metadata"]["context_length"], 262144)
        self.assertEqual(body["metadata"]["block_count"], 65)
        self.assertEqual(body["context_size"]["flag"], "--ctx-size")
        self.assertIsNone(body["context_size"]["applied"])
        self.assertIsNone(body["context_size"]["observed"])
        context_values = [item["value"] for item in body["context_size"]["options"]]
        self.assertEqual(
            context_values,
            [None, 32768, 49152, 65536, 98304, 131072, 163840, 196608, 262144],
        )
        self.assertEqual(body["gpu_layers"]["flag"], "--n-gpu-layers")
        self.assertEqual(body["gpu_layers"]["applied"], -1)
        self.assertEqual(body["gpu_layers"]["maximum"], 66)
        gpu_values = [item["value"] for item in body["gpu_layers"]["options"]]
        self.assertEqual(gpu_values[:4], ["auto", "all", -1, 0])
        self.assertEqual(body["gpu_layers"]["options"][1]["label"], "All")
        self.assertEqual(body["gpu_layers"]["options"][2]["label"], "Automatic (legacy)")
        self.assertEqual(gpu_values[-1], 66)
        self.assertEqual(len(gpu_values), 70)
        self.assertEqual(body["startup_defaults"]["flash_attn"]["applied"], "on")
        self.assertEqual(body["startup_defaults"]["cache_type_k"]["applied"], "f16")
        self.assertEqual(body["startup_defaults"]["fit"]["applied"], "on")
        self.assertEqual(body["startup_defaults"]["threads"]["source"], "backend_recommendation")
        self.assertIsNotNone(body["startup_defaults"]["threads"]["recommended"])
        effort = body["per_request_defaults"]["reasoning_effort"]
        self.assertEqual(effort["source"], "unavailable")
        self.assertEqual(effort["applied"], "default")
        self.assertEqual(
            [item["value"] for item in effort["options"]],
            [],
        )

    def test_template_constrained_thinking_excludes_unsupported_levels(self) -> None:
        metadata = GgufRuntimeMetadata(architecture="qwen", chat_template="""
            {% set resolved_reasoning_effort = reasoning_effort|default('xhigh') %}
            {% if resolved_reasoning_effort == 'high' %}{% set resolved_reasoning_effort = 'xhigh' %}{% endif %}
            {% if resolved_reasoning_effort not in ('xhigh', 'medium', 'low') %}{{ raise_exception('Invalid') }}{% endif %}
            {% if enable_thinking %}Think{% endif %}
        """)
        report = bundle_configuration_options("bundle", metadata)
        self.assertEqual([o.value for o in report.per_request_defaults["reasoning_effort"].options], ["default", "low", "medium", "xhigh"])
        self.assertEqual(report.per_request_defaults["reasoning_effort"].accepted_values, ["high", "low", "medium", "xhigh"])
        self.assertTrue(report.per_request_defaults["reasoning"].supported)
        self.assertEqual(report.per_request_defaults["reasoning_effort"].default_value, "xhigh")
        self.assertEqual(report.per_request_defaults["reasoning_effort"].default_source, "gguf_template")

    def test_unknown_or_conflicting_template_default_stays_unknown(self) -> None:
        for template in ("{{ reasoning_effort }}", "{{ reasoning_effort|default('low') }} {{ reasoning_effort|default('high') }}"):
            report = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template=template))
            self.assertIsNone(report.per_request_defaults["reasoning_effort"].default_value)

    def test_template_default_thinking_is_proven_only_by_explicit_undefined_branch(self) -> None:
        report = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template="{% if enable_thinking is undefined or enable_thinking is true %}think{% endif %}"))
        self.assertEqual(report.per_request_defaults["reasoning"].default_value, "on")

    def test_thinking_history_requires_template_evidence(self) -> None:
        keep = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template=
            "{% if preserve_thinking is undefined or preserve_thinking is true %}{{ message.reasoning_content }}{% endif %}"))
        self.assertTrue(keep.startup_defaults["reasoning_preserve"].supported)
        self.assertIs(keep.startup_defaults["reasoning_preserve"].default_value, True)
        self.assertEqual(keep.startup_defaults["reasoning_preserve"].default_source, "gguf_template")
        unknown = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template=
            "{% if preserve_thinking %}{{ message.reasoning_content }}{% endif %}"))
        self.assertTrue(unknown.startup_defaults["reasoning_preserve"].supported)
        self.assertIsNone(unknown.startup_defaults["reasoning_preserve"].default_value)
        unsupported = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template="{{ messages }}"))
        self.assertIs(unsupported.startup_defaults["reasoning_preserve"].supported, False)
        missing = bundle_configuration_options("bundle", GgufRuntimeMetadata())
        self.assertIsNone(missing.startup_defaults["reasoning_preserve"].supported)

    def test_connected_configuration_options_uses_server_template_without_bundle(self) -> None:
        from workbench_backend.inference.schemas import Deployment, DeploymentStatus, ManagementScope
        deployment = Deployment(id="connected-template", display_name="Connected", scope=ManagementScope.connected,
            status=DeploymentStatus.running, created_at="now", updated_at="now", endpoint="http://127.0.0.1:9/v1",
            server_props=ServerProperties(fetched="now", source_url="fixture", n_ctx=98304,
                chat_template="{% set effort = reasoning_effort|default('xhigh') %}{% if enable_thinking is undefined or enable_thinking is true %}think{% endif %}",
                default_generation_settings={"params":{"temperature":0.6}}))
        self.manager.store.put_deployment(deployment)
        response = self.client.get(f"/v1/deployments/{deployment.id}/configuration-options")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body["bundle_id"])
        self.assertEqual(body["context_size"]["observed"], 98304)
        self.assertEqual(body["per_request_defaults"]["reasoning_effort"]["default_value"], "xhigh")
        self.assertEqual(body["per_request_defaults"]["reasoning"]["default_value"], "on")
        self.assertEqual(body["per_request_defaults"]["temperature"]["default_value"], 0.6)

    def test_missing_template_is_unverified_and_only_closed_constraints_define_accepted_values(self) -> None:
        unknown = bundle_configuration_options("bundle", GgufRuntimeMetadata())
        self.assertIsNone(unknown.per_request_defaults["reasoning_effort"].supported)
        self.assertIsNone(unknown.per_request_defaults["reasoning_effort"].accepted_values)
        open_levels = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template="{% if reasoning_effort == 'high' %}Think{% endif %}"))
        self.assertIsNone(open_levels.per_request_defaults["reasoning_effort"].accepted_values)
        plain = bundle_configuration_options("bundle", GgufRuntimeMetadata(chat_template="{{ messages }}"))
        self.assertIs(plain.per_request_defaults["reasoning_effort"].supported, False)
        self.assertEqual(plain.per_request_defaults["reasoning_effort"].accepted_values, [])

    def test_speculation_requires_head_evidence_and_exposes_numeric_control(self) -> None:
        without = bundle_configuration_options("bundle", GgufRuntimeMetadata(name="MTP Model", nextn_predict_layers=1))
        self.assertNotIn("draft-mtp", [o.value for o in without.startup_defaults["spec_type"].options])
        with_head = bundle_configuration_options("bundle", GgufRuntimeMetadata(has_mtp_tensors=True, nextn_predict_layers=1))
        self.assertIn("draft-mtp", [o.value for o in with_head.startup_defaults["spec_type"].options])
        self.assertEqual(with_head.startup_defaults["spec_draft_n_max"].applied, 3)

    def test_mtp_head_and_thinking_template_are_read_from_file_directory(self) -> None:
        path = self.root / "model-with-head.gguf"
        writer = GGUFWriter(str(path), "qwen35")
        writer.add_context_length(32768)
        writer.add_block_count(4)
        writer.add_uint32("qwen35.nextn_predict_layers", 1)
        writer.add_chat_template("{% if reasoning_effort not in ('low', 'medium', 'xhigh') %}{{ raise_exception('Invalid') }}{% endif %}")
        writer.add_tensor("blk.3.nextn.eh_proj.weight", np.zeros((2, 2), dtype=np.float32))
        writer.write_header_to_file(); writer.write_kv_data_to_file(); writer.write_tensors_to_file(); writer.close()
        metadata = read_gguf_runtime_metadata(path)
        self.assertTrue(metadata.has_mtp_tensors)
        self.assertEqual(metadata.nextn_predict_layers, 1)
        self.assertIn("reasoning_effort", metadata.chat_template)

    def test_missing_file_does_not_return_cached_details(self) -> None:
        bundle_id = self._bundle()
        self.manager.get_bundle_configuration_options(bundle_id)
        Path(self.manager.store.get_bundle(bundle_id).primary_path).unlink()
        response = self.client.get(f"/v1/bundles/{bundle_id}/configuration-options")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "model_inspection_unavailable")

    def test_inspection_reused_after_restart_refreshed_and_invalidated(self) -> None:
        bundle_id = self._bundle()
        with patch("workbench_backend.inference.service.read_gguf_runtime_metadata", wraps=read_gguf_runtime_metadata) as reader:
            first = self.manager.get_bundle_configuration_options(bundle_id)
            second = self.manager.get_bundle_configuration_options(bundle_id)
            restarted = ModelManager(self.paths)
            third = restarted.get_bundle_configuration_options(bundle_id)
            self.assertEqual(reader.call_count, 1)
            self.assertFalse(first.metadata["inspection_cached"])
            self.assertTrue(second.metadata["inspection_cached"])
            self.assertTrue(third.metadata["inspection_cached"])
            restarted.get_bundle_configuration_options(bundle_id, refresh=True)
            self.assertEqual(reader.call_count, 2)
            with patch("workbench_backend.inference.inspection_cache.INSPECTION_SCHEMA", 999):
                restarted.get_bundle_configuration_options(bundle_id)
            self.assertEqual(reader.call_count, 3)
            path = Path(self.manager.store.get_bundle(bundle_id).primary_path)
            data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
            restarted.get_bundle_configuration_options(bundle_id)
            self.assertEqual(reader.call_count, 4)
            self.assertFalse(restarted.store.get_bundle(bundle_id).disk_matches)

    def test_library_reuses_persistent_verification_but_launch_is_strict(self) -> None:
        bundle_id = self._bundle()
        self.manager.list_bundles()
        restarted = ModelManager(self.paths)
        with patch("workbench_backend.inference.bundles.cached_sha256_file", side_effect=AssertionError("cold cache rehash")):
            self.assertTrue(restarted.list_bundles()[0].disk_matches)
        with patch("workbench_backend.inference.bundles.sha256_file", side_effect=RuntimeError("strict launch verification")):
            with self.assertRaisesRegex(RuntimeError, "strict launch verification"):
                restarted.create_managed(ManagedDeploymentRequest(bundle_id=bundle_id, auto_start=False))

    def test_small_context_models_get_small_options(self) -> None:
        bundle_id = self._bundle(context_length=8192, block_count=4)
        body = self.client.get(f"/v1/bundles/{bundle_id}/configuration-options").json()
        context_values = [item["value"] for item in body["context_size"]["options"]]
        self.assertEqual(context_values, [None, 1024, 2048, 4096, 8192])

    def test_metadata_uses_general_architecture_specific_keys(self) -> None:
        bundle_id = self._bundle(
            context_length=8192,
            block_count=4,
            extra_uint32={"vision.context_length": 999999, "vision.block_count": 999},
        )
        body = self.client.get(f"/v1/bundles/{bundle_id}/configuration-options").json()
        self.assertEqual(body["metadata"]["context_length"], 8192)
        self.assertEqual(body["metadata"]["block_count"], 4)
        self.assertEqual(body["gpu_layers"]["maximum"], 5)

    def test_runtime_metadata_does_not_build_tensors(self) -> None:
        gguf = write_tiny_gguf(
            self.root / "incoming" / "unknown-tensor-type.gguf",
            context_length=8192,
            block_count=4,
        )
        set_first_tensor_type(gguf, 143)
        job = self.manager.import_local(LocalImportRequest(source_path=str(gguf)))
        bundle_id = job.bundle_id or ""

        body = self.client.get(f"/v1/bundles/{bundle_id}/configuration-options").json()

        self.assertEqual(body["metadata"]["context_length"], 8192)
        self.assertEqual(body["metadata"]["block_count"], 4)
        bundle = self.manager.get_bundle(bundle_id)
        with self.assertRaises(ManagerError) as caught:
            inspect_gguf_file(Path(bundle.primary_path or ""), bundle_id=bundle_id)
        self.assertEqual(caught.exception.code, "gguf_inspect_unsupported")

    def test_observed_context_comes_from_selected_deployment_props(self) -> None:
        bundle_id = self._bundle(context_length=65536, block_count=8)
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=bundle_id, startup={"port": 18191}, auto_start=False)
        )
        updated = deployment.model_copy(
            update={
                "server_props": ServerProperties(
                    fetched="2026-09-20T00:00:00+00:00",
                    source_url="http://127.0.0.1:9/props",
                    n_ctx=32768,
                )
            }
        )
        self.manager.store.put_deployment(updated)

        body = self.client.get(
            f"/v1/bundles/{bundle_id}/configuration-options",
            params={"deployment_id": deployment.id},
        ).json()

        self.assertEqual(body["deployment_id"], deployment.id)
        self.assertEqual(body["context_size"]["observed"], 32768)

    def test_deployment_must_belong_to_requested_bundle(self) -> None:
        first = self._bundle(context_length=8192, block_count=4)
        second = self._bundle(context_length=16384, block_count=8)
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=first, startup={"port": 18192}, auto_start=False)
        )

        response = self.client.get(
            f"/v1/bundles/{second}/configuration-options",
            params={"deployment_id": deployment.id},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "deployment_bundle_mismatch")


if __name__ == "__main__":
    unittest.main()
