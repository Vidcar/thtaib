"""Managed router contract without touching a real model or desktop data."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from workbench_backend.errors import ManagerError
from workbench_backend.inference.adapter import adapter_target
from workbench_backend.inference.process import HttpProbe
from workbench_backend.inference.schemas import (
    DeploymentStatus, HealthReport, LocalImportRequest, ManagedDeploymentRequest,
    ProcessIdentity, ResourceUsage, ServerProperties,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf
from test_app import FakeHF


class RouterRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(root).ensure(), hf=FakeHF(error=RuntimeError("offline")))
        gguf = write_tiny_gguf(root / "incoming" / "tiny.gguf")
        bundle = self.manager.import_local(LocalImportRequest(source_path=str(gguf)))
        self.bundle_id = bundle.bundle_id or ""
        self.router = self.manager.deployments.router

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _deployment(self, *, ctx_size: int = 4096):
        return self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, startup={"ctx_size": ctx_size, "parallel": 2}, auto_start=False,
        ))

    def test_presets_use_exact_configuration_ids_and_do_not_autoload(self) -> None:
        first = self._deployment(ctx_size=4096)
        second = self._deployment(ctx_size=8192)
        content = self.router._presets()
        self.assertIn(f"[{first.id}]\nload-on-startup = false", content)
        self.assertIn(f"[{second.id}]\nload-on-startup = false", content)
        self.assertEqual(content.count("parallel = 2"), 2)
        self.assertIn("ctx-size = 4096", content)
        self.assertIn("ctx-size = 8192", content)
        self.assertEqual(content.count("model = "), 2)
        self.assertNotIn("host =", content)
        self.assertNotIn("port =", content)

    def test_default_policy_and_status_read_do_not_start_router(self) -> None:
        self._deployment()
        with patch.object(self.router.processes, "start") as start:
            status = self.router.status()
        self.assertEqual(status, {
            "max_loaded_models": 1,
            "loaded_deployment_ids": [],
            "loading_deployment_ids": [],
            "router_status": "stopped",
        })
        start.assert_not_called()

    def test_broken_unrelated_bundle_does_not_block_valid_preset(self) -> None:
        valid = self._deployment()
        incoming = write_tiny_gguf(Path(self.tmp.name) / "incoming" / "broken.gguf")
        imported = self.manager.import_local(LocalImportRequest(source_path=str(incoming)))
        broken_bundle = self.manager.get_bundle(imported.bundle_id or "")
        broken = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=broken_bundle.id, auto_start=False,
        ))
        Path(broken_bundle.primary_path or "").unlink()

        presets = self.router._presets()
        self.assertIn(f"[{valid.id}]", presets)
        self.assertNotIn(f"[{broken.id}]", presets)
        with patch.object(self.router, "_ensure_router") as ensure_router:
            with self.assertRaises(ManagerError) as caught:
                self.router.start(broken.id)
        self.assertEqual(caught.exception.code, "bundle_file_missing")
        ensure_router.assert_not_called()

    def test_explicit_start_loads_exact_preset_and_waits_for_model_props(self) -> None:
        deployment = self._deployment()
        identity = ProcessIdentity(pid=123, create_time=1.0, executable="llama-server")
        record = {"endpoint": "http://127.0.0.1:18080/v1", "identity": identity}
        unloaded = {"id": deployment.id, "status": {"value": "unloaded"}}
        loaded = {"id": deployment.id, "status": {"value": "loaded"}}
        props = ServerProperties(fetched=utc_now(), source_url="http://127.0.0.1:18080/props")
        health = HealthReport(healthy=True, endpoint=record["endpoint"], checked=utc_now(), detail="ok")
        with (patch.object(self.router, "_ensure_router", return_value=record),
              patch.object(self.router, "_inventory", side_effect=[{deployment.id: unloaded}, {deployment.id: loaded}]),
              patch.object(self.router, "_post") as post,
              patch.object(self.router.probe, "props", return_value=props) as props_probe,
              patch.object(self.router.probe, "health", return_value=health),
              patch.object(self.router.processes, "resource_usage", return_value=ResourceUsage(available=True))):
            started = self.router.start(deployment.id)
        self.assertEqual(started.status, DeploymentStatus.running)
        self.assertEqual(started.router_preset_id, deployment.id)
        self.assertEqual(started.applied_startup["port"], 18080)
        post.assert_called_once_with(record["endpoint"], "/models/load", {"model": deployment.id})
        props_probe.assert_called_once_with(record["endpoint"], model=deployment.id)

    def test_legacy_owned_process_is_never_orphaned_by_status_or_start(self) -> None:
        deployment = self._deployment()
        identity = ProcessIdentity(pid=123, create_time=1.0, executable="old-server")
        old = self.manager.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.running, "pid": identity.pid,
            "process_identity": identity,
        }))
        with patch.object(self.router.processes, "classify", return_value="match"), \
             patch.object(self.router, "_owned_record", return_value=None):
            self.assertEqual(self.router.status()["router_status"], "unhealthy")
            with self.assertRaises(ManagerError) as caught:
                self.router.start(deployment.id)
        self.assertEqual(caught.exception.code, "legacy_managed_process_active")
        retained = self.manager.store.get_deployment(deployment.id)
        self.assertEqual(retained.process_identity, old.process_identity)
        self.assertEqual(retained.status, DeploymentStatus.running)

    def test_limit_change_checks_active_consumers_inside_router(self) -> None:
        self._deployment()
        self.router.require_idle = lambda _deployment: (_ for _ in ()).throw(
            ManagerError("Model is active", code="deployment_active", status_code=409))
        with self.assertRaises(ManagerError) as caught:
            self.router.set_max_loaded_models(2)
        self.assertEqual(caught.exception.code, "deployment_active")
        self.assertEqual(self.router.max_loaded_models(), 1)

    def test_legacy_cutover_refuses_shared_router_identity(self) -> None:
        deployment = self._deployment()
        identity = ProcessIdentity(pid=123, create_time=1.0, executable="llama-server")
        self.manager.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.running, "pid": identity.pid,
            "process_identity": identity,
        }))
        record = {"endpoint": "http://127.0.0.1:8080/v1", "identity": identity}
        with patch.object(self.router, "_owned_record", return_value=record), \
             patch.object(self.router.processes, "stop") as stop:
            with self.assertRaises(ManagerError) as caught:
                self.manager.deployments.stop_legacy_owned(deployment.id)
        self.assertEqual(caught.exception.code, "legacy_managed_process_missing")
        stop.assert_not_called()

    def test_model_props_probe_does_not_autoload(self) -> None:
        payload = {"model_alias": "fixture"}
        with patch("workbench_backend.inference.process.httpx.get",
                   return_value=httpx.Response(200, json=payload)) as get:
            HttpProbe().props("http://127.0.0.1:8080/v1", model="deploy_123")
        url = get.call_args.args[0]
        self.assertIn("model=deploy_123", url)
        self.assertIn("autoload=false", url)

    def test_template_probe_routes_exact_model_then_removes_temporary_preset(self) -> None:
        bundle = self.manager.get_bundle(self.bundle_id)
        path = Path(self.tmp.name) / "template.jinja"
        path.write_text("{{ messages[0].content }}", encoding="utf-8")
        captured: list[str] = []

        def started(deployment_id: str):
            captured.append(deployment_id)
            deployment = self.manager.store.get_deployment(deployment_id)
            return deployment.model_copy(update={
                "status": DeploymentStatus.running,
                "endpoint": "http://127.0.0.1:18080/v1",
                "server_props": ServerProperties(
                    fetched=utc_now(), source_url="http://127.0.0.1:18080/props",
                    chat_template=path.read_text(encoding="utf-8"),
                ),
            })

        def stopped(deployment_id: str):
            return self.manager.store.get_deployment(deployment_id).model_copy(update={
                "status": DeploymentStatus.stopped,
                "pid": None, "process_identity": None,
            })

        response = httpx.Response(200, json={"prompt": "Template compatibility check"},
                                  request=httpx.Request("POST", "http://127.0.0.1:18080/apply-template"))
        with (patch.object(self.manager.deployments, "_router_enabled", return_value=True),
              patch.object(self.manager.deployments, "start", side_effect=started),
              patch.object(self.manager.deployments, "stop", side_effect=stopped),
              patch.object(self.router, "refresh_presets") as refresh,
              patch("workbench_backend.inference.service.httpx.post", return_value=response) as post):
            self.manager._probe_chat_template(bundle, path)
        self.assertEqual(len(captured), 1)
        self.assertEqual(post.call_args.kwargs["json"]["model"], captured[0])
        self.assertIsNone(self.manager.store.get_deployment(captured[0]))
        refresh.assert_called_once_with()

    def test_cap_one_parent_helper_parent_uses_exact_preset_each_time(self) -> None:
        parent = self._deployment(ctx_size=4096)
        helper = self._deployment(ctx_size=8192)
        identity = ProcessIdentity(pid=123, create_time=1.0, executable="llama-server")
        record = {"endpoint": "http://127.0.0.1:18080/v1", "identity": identity}
        resident: dict[str, str | None] = {"id": None}
        loads: list[str] = []

        def inventory(_endpoint: str, *, reload: bool = False):
            return {deployment.id: {
                "id": deployment.id,
                "status": {"value": "loaded" if resident["id"] == deployment.id else "unloaded"},
            } for deployment in (parent, helper)}

        def load(_endpoint: str, route: str, payload: dict[str, str]):
            self.assertEqual(route, "/models/load")
            loads.append(payload["model"])
            resident["id"] = payload["model"]

        props = ServerProperties(fetched=utc_now(), source_url="http://127.0.0.1:18080/props")
        health = HealthReport(healthy=True, endpoint=record["endpoint"], checked=utc_now(), detail="ok")
        with (patch.object(self.manager.deployments, "_router_enabled", return_value=True),
              patch.object(self.router, "_ensure_router", return_value=record),
              patch.object(self.router, "_inventory", side_effect=inventory),
              patch.object(self.router, "_post", side_effect=load),
              patch.object(self.router.probe, "props", return_value=props),
              patch.object(self.router.probe, "health", return_value=health),
              patch.object(self.router.processes, "resource_usage", return_value=ResourceUsage(available=True))):
            ready_parent = self.manager.ensure_deployment_ready(parent.id)
            ready_helper = self.manager.ensure_deployment_ready(helper.id)
            resumed_parent = self.manager.ensure_deployment_ready(parent.id)
        self.assertEqual(loads, [parent.id, helper.id, parent.id])
        self.assertEqual(ready_parent.status, DeploymentStatus.running)
        self.assertEqual(ready_helper.status, DeploymentStatus.running)
        self.assertEqual(adapter_target(resumed_parent)["model"], parent.id)

    def test_resident_turn_skips_full_hash_but_evicted_load_verifies_again(self) -> None:
        deployment = self._deployment()
        bundle = self.manager.get_bundle(self.bundle_id)
        identity = ProcessIdentity(pid=123, create_time=1.0, executable="llama-server")
        record = {"endpoint": "http://127.0.0.1:18080/v1", "identity": identity}
        resident = {"loaded": False}

        def inventory(_endpoint: str, *, reload: bool = False):
            return {deployment.id: {"id": deployment.id,
                "status": {"value": "loaded" if resident["loaded"] else "unloaded"}}}

        def load(_endpoint: str, route: str, payload: dict[str, str]):
            self.assertEqual(route, "/models/load")
            self.assertEqual(payload["model"], deployment.id)
            resident["loaded"] = True

        props = ServerProperties(fetched=utc_now(), source_url="http://127.0.0.1:18080/props")
        health = HealthReport(healthy=True, endpoint=record["endpoint"], checked=utc_now(), detail="ok")
        with (patch.object(self.manager.deployments, "_router_enabled", return_value=True),
              patch.object(self.router, "_ensure_router", return_value=record),
              patch.object(self.router, "_inventory", side_effect=inventory) as inventory_probe,
              patch.object(self.router, "_post", side_effect=load) as post,
              patch.object(self.router.probe, "props", return_value=props),
              patch.object(self.router.probe, "health", return_value=health),
              patch.object(self.router.processes, "resource_usage", return_value=ResourceUsage(available=True)),
              patch("workbench_backend.inference.bundles.sha256_file", wraps=sha256_file) as hash_file):
            self.manager.ensure_deployment_ready(deployment.id)
            self.assertEqual(hash_file.call_count, 1)
            self.assertEqual(post.call_count, 1)

            self.manager.ensure_deployment_ready(deployment.id)
            self.assertEqual(hash_file.call_count, 1)
            self.assertEqual(post.call_count, 1)

            resident["loaded"] = False
            self.manager.ensure_deployment_ready(deployment.id)
            self.assertEqual(hash_file.call_count, 2)
            self.assertEqual(post.call_count, 2)

            path = Path(bundle.primary_path or "")
            with path.open("r+b") as handle:
                handle.write(b"X")
            inventories_before = inventory_probe.call_count
            with self.assertRaises(ManagerError) as caught:
                self.manager.ensure_deployment_ready(deployment.id)
            self.assertEqual(caught.exception.code, "bundle_not_deployable")
            self.assertEqual(inventory_probe.call_count, inventories_before)
            self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
