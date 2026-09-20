from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.app import create_app
from workbench_backend.errors import ManagerError
from workbench_backend.inference.inspect import inspect_gguf_file
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
        self.assertEqual(gpu_values[0], -1)
        self.assertEqual(gpu_values[1], 0)
        self.assertEqual(gpu_values[-1], 66)
        self.assertEqual(len(gpu_values), 68)
        self.assertEqual(body["startup_defaults"]["flash_attn"]["applied"], "on")
        self.assertEqual(body["startup_defaults"]["cache_type_k"]["applied"], "f16")
        self.assertEqual(body["startup_defaults"]["fit"]["applied"], "on")
        self.assertEqual(body["startup_defaults"]["threads"]["source"], "backend_recommendation")
        self.assertIsNotNone(body["startup_defaults"]["threads"]["recommended"])

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
