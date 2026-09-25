"""Owned llama.cpp b11045 router and exact managed-configuration residency.

The router, rather than Workbench, schedules idle eviction at ``--models-max``.
Workbench owns its process, preset source and saved configuration records. All
observations use ``GET /models`` or ``GET /props?autoload=false``: opening the
application and reading status cannot load a model.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import mmproj_companion
from workbench_backend.inference.deployments import (
    _first_free_port,
    _require_valid_managed_startup,
    _verified_loaded_template,
    managed_argv,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.process import HttpProbe, ProcessSupervisor, wait_for_owned_health
from workbench_backend.inference.process_logs import deployment_log_path
from workbench_backend.inference.runtime import RuntimeService
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    ImportStatus,
    ManagementScope,
    ProcessIdentity,
    ResourceUsage,
)
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore

_STATE_KEY = "managed-router-state"
_MAX_KEY = "max-loaded-models"
_LOAD_TIMEOUT = 600.0


def _single_line(value: object, *, key: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text or "\x00" in text:
        raise ManagerError(
            f"Model setting {key} cannot contain a line break or NUL.",
            code="managed_startup_invalid", status_code=400,
        )
    return text


class ManagedRouter:
    def __init__(self, store: RecordStore, runtime: RuntimeService,
                 processes: ProcessSupervisor, probe: HttpProbe,
                 require_idle: Callable[[Deployment], None] | None = None) -> None:
        self.store = store
        self.runtime = runtime
        self.processes = processes
        self.probe = probe
        self.require_idle = require_idle
        self._lock = threading.RLock()
        self._preset_path = store.paths.state / "managed-router.ini"
        self._cache_root = store.paths.state / "managed-router-cache"
        self._template_path = store.paths.state / "managed-router-templates"

    def max_loaded_models(self) -> int:
        raw = self.store.get_setting(_MAX_KEY)
        if raw is None:
            return 1
        try:
            value = int(raw)
        except ValueError as exc:
            raise ManagerError("Saved maximum loaded models is invalid.",
                               code="max_loaded_models_invalid", status_code=409) from exc
        if value < 1:
            raise ManagerError("Saved maximum loaded models must be positive.",
                               code="max_loaded_models_invalid", status_code=409)
        return value

    def set_max_loaded_models(self, value: int) -> dict[str, Any]:
        if isinstance(value, bool) or value < 1:
            raise ManagerError("Maximum loaded models must be a positive number.",
                               code="max_loaded_models_invalid", status_code=400)
        with self._lock:
            if value == self.max_loaded_models():
                return self.status()
            if self.require_idle is not None:
                for deployment in self._managed_deployments():
                    self.require_idle(deployment)
            # The native limit is fixed when the router starts. Stop only an
            # identity-verified owned router after the execution-boundary guard.
            record = self._owned_record()
            if record is not None:
                self.processes.stop(record["identity"])
                self.store.put_setting(_STATE_KEY, "")
                self._mark_all_stopped()
            self.store.put_setting(_MAX_KEY, str(value))
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            record = self._owned_record()
            loaded: list[str] = []
            loading: list[str] = []
            status = "stopped"
            if record is None:
                if self._legacy_live():
                    status = "unhealthy"
                else:
                    self._mark_all_stopped()
            else:
                status = "running"
                try:
                    inventory = self._inventory(record["endpoint"])
                except ManagerError:
                    status = "unhealthy"
                else:
                    for deployment in self._managed_deployments():
                        model = inventory.get(deployment.id)
                        state = self._model_state(model)
                        if state == "loaded":
                            loaded.append(deployment.id)
                        elif state == "loading":
                            loading.append(deployment.id)
                        self._record_observation(deployment, record, model)
            return {
                "max_loaded_models": self.max_loaded_models(),
                "loaded_deployment_ids": loaded,
                "loading_deployment_ids": loading,
                "router_status": status,
            }

    def start(self, deployment_id: str) -> Deployment:
        with self._lock:
            deployment = self._require_managed(deployment_id)
            if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
                raise ManagerError("Reload this model to restore its previous configuration.",
                                   code="reconfigure_recovery_required", status_code=409)
            bundle = self.store.get_bundle(deployment.bundle_id or "")
            if bundle is None or bundle.status != ImportStatus.complete or not bundle.disk_matches:
                raise ManagerError("A complete model bundle is required.",
                                   code="bundle_not_deployable", status_code=409)
            _require_valid_managed_startup(resolve_bags(startup=deployment.requested_startup).startup)
            # Validate the selected bundle before generating the shared preset file.
            # A broken, unrelated bundle must not make this model unavailable.
            managed_argv("llama-server", bundle, deployment.applied_startup)
            record = self._ensure_router()
            endpoint = record["endpoint"]
            inventory = self._inventory(endpoint)
            model = inventory.get(deployment.id)
            if model is None:
                raise ManagerError("The saved configuration was not registered with llama.cpp.",
                                   code="router_preset_missing", status_code=409,
                                   details={"deployment_id": deployment.id})
            state = self._model_state(model)
            if state != "loaded":
                self._post(endpoint, "/models/load", {"model": deployment.id})
                deadline = time.monotonic() + _LOAD_TIMEOUT
                while True:
                    model = self._inventory(endpoint).get(deployment.id)
                    state = self._model_state(model)
                    if state == "loaded":
                        break
                    failure = (model or {}).get("status", {}) if isinstance(model, dict) else {}
                    if isinstance(failure, dict) and failure.get("failed"):
                        raise ManagerError("llama.cpp could not load this model configuration.",
                                           code="router_model_load_failed", status_code=409,
                                           details={"deployment_id": deployment.id,
                                                    "exit_code": failure.get("exit_code")})
                    if time.monotonic() >= deadline:
                        raise ManagerError("Timed out waiting for llama.cpp to load this model.",
                                           code="router_model_load_timeout", status_code=409,
                                           details={"deployment_id": deployment.id})
                    time.sleep(0.25)
            deadline = time.monotonic() + _LOAD_TIMEOUT
            while True:
                observed = self._record_observation(deployment, record, model)
                if observed.status == DeploymentStatus.running:
                    return observed
                if observed.status in {DeploymentStatus.stopped, DeploymentStatus.failed}:
                    raise ManagerError("The selected model stopped before it became ready.",
                                       code="router_model_not_ready", status_code=409,
                                       details={"deployment_id": deployment.id})
                if time.monotonic() >= deadline:
                    raise ManagerError("llama.cpp loaded the model but its model-specific properties are unavailable.",
                                       code="router_model_props_unavailable", status_code=409,
                                       details={"deployment_id": deployment.id})
                time.sleep(0.25)
                model = self._inventory(endpoint).get(deployment.id)

    def stop(self, deployment_id: str) -> Deployment:
        with self._lock:
            deployment = self._require_managed(deployment_id)
            if self.require_idle is not None:
                self.require_idle(deployment)
            record = self._owned_record()
            if record is None and self._legacy_live():
                raise ManagerError("An older managed process is still owned. Stop it with the previous runtime before switching.",
                                   code="legacy_managed_process_active", status_code=409)
            if record is not None:
                model = self._inventory(record["endpoint"]).get(deployment.id)
                if self._model_state(model) in {"loaded", "loading", "sleeping"}:
                    self._post(record["endpoint"], "/models/unload", {"model": deployment.id})
                    deadline = time.monotonic() + 30.0
                    while self._model_state(self._inventory(record["endpoint"]).get(deployment.id)) not in {"unloaded", None}:
                        if time.monotonic() >= deadline:
                            raise ManagerError("llama.cpp has not confirmed model unload.",
                                               code="router_model_unload_timeout", status_code=409)
                        time.sleep(0.2)
            return self._mark_stopped(deployment)

    def health(self, deployment_id: str) -> Deployment:
        with self._lock:
            deployment = self._require_managed(deployment_id)
            record = self._owned_record()
            if record is None:
                return deployment if self._legacy_live() else self._mark_stopped(deployment)
            try:
                model = self._inventory(record["endpoint"]).get(deployment.id)
            except ManagerError:
                return self.store.put_deployment(deployment.model_copy(update={
                    "status": DeploymentStatus.unhealthy,
                    "error": "Owned llama.cpp router is not responding.",
                    "updated_at": utc_now(),
                }))
            return self._record_observation(deployment, record, model)

    def reconcile(self) -> list[Deployment]:
        with self._lock:
            self.status()
            if self._owned_record() is None and not self._legacy_live():
                self._mark_all_stopped()
            return self._managed_deployments()

    def live_owned(self) -> list[Deployment]:
        with self._lock:
            if self._owned_record() is None:
                return []
            # Pinning the runtime must account for the router process even if
            # no child model is currently resident.
            return self._managed_deployments()[:1]

    def stop_router(self) -> None:
        with self._lock:
            if self.require_idle is not None:
                for deployment in self._managed_deployments():
                    self.require_idle(deployment)
            record = self._owned_record()
            if record is not None:
                self.processes.stop(record["identity"])
                self.store.put_setting(_STATE_KEY, "")
            self._mark_all_stopped()

    def refresh_presets(self) -> None:
        """Reconcile saved presets after a model record is removed, without warming.

        A temporary template probe, for example, unloads its model before
        deleting the record. Its preset must then disappear from the running
        router's model list as well. An absent router is left absent.
        """
        with self._lock:
            if self._owned_record() is not None:
                self._ensure_router()

    def _ensure_router(self) -> dict[str, Any]:
        record = self._owned_record()
        new_presets = self._presets()
        if record is not None:
            old_presets = self._preset_path.read_text(encoding="utf-8") if self._preset_path.is_file() else ""
            if old_presets != new_presets:
                if self.require_idle is not None:
                    old_sections = self._sections(old_presets)
                    new_sections = self._sections(new_presets)
                    for deployment in self._managed_deployments():
                        if (not old_presets or deployment.id in old_sections
                                and old_sections[deployment.id] != new_sections.get(deployment.id)):
                            self.require_idle(deployment)
                self._write_presets(new_presets)
                try:
                    self._inventory(record["endpoint"], reload=True)
                except Exception:
                    self._write_presets(old_presets)
                    raise
            return record
        old_processes = self._legacy_live()
        if old_processes:
            raise ManagerError("An older managed llama.cpp process is still owned. Stop it before starting the router.",
                               code="legacy_managed_process_active", status_code=409,
                               details={"deployment_ids": [item.id for item in old_processes]})
        self._write_presets(new_presets)
        executable = self.runtime.require_executable()
        host = "127.0.0.1"
        port = _first_free_port(host, 8080)
        endpoint = f"http://{host}:{port}/v1"
        self._cache_root.mkdir(parents=True, exist_ok=True)
        cache_path = self._cache_root / uuid4().hex
        cache_path.mkdir()
        # Ignore inherited llama-server model/router arguments and point the
        # cache at an empty Workbench-owned directory. Only our generated
        # presets are allowed to become discoverable models.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("LLAMA_ARG_") and key not in {"LLAMA_CACHE", "LLAMA_API_KEY"}}
        env["LLAMA_CACHE"] = str(cache_path)
        identity = self.processes.start(
            [str(executable), "--host", host, "--port", str(port),
             "--models-preset", str(self._preset_path),
             "--models-max", str(self.max_loaded_models())],
            cwd=Path(executable).parent,
            log_path=deployment_log_path(self.store.paths.logs, "managed-router"),
            env=env,
        )
        try:
            verdict, health, owns = wait_for_owned_health(
                self.probe, endpoint, self.processes, identity, port=port)
            if verdict != "match" or not self.processes.launched_still_running(identity.pid) or owns is not True or not health.healthy:
                raise ManagerError("The launched llama.cpp router did not become a verified owned endpoint.",
                                   code="router_not_ready", status_code=409)
            record = {"endpoint": endpoint, "identity": identity}
            self.store.put_setting(_STATE_KEY, json.dumps({
                "endpoint": endpoint, "identity": identity.model_dump(mode="json"),
            }))
            return record
        except Exception:
            # Only the exact newly launched identity can be stopped.
            self.processes.stop(identity)
            raise

    def _owned_record(self) -> dict[str, Any] | None:
        raw = self.store.get_setting(_STATE_KEY)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            identity = ProcessIdentity.model_validate(payload["identity"])
            endpoint = str(payload["endpoint"])
            if urlparse(endpoint).hostname != "127.0.0.1":
                raise ValueError("router endpoint is not local")
        except (ValueError, KeyError, TypeError):
            self.store.put_setting(_STATE_KEY, "")
            return None
        verdict = self.processes.classify(identity)
        if verdict == "unproven":
            raise ManagerError("Router process identity could not be verified.",
                               code="process_identity_unproven", status_code=409)
        if verdict != "match":
            self.store.put_setting(_STATE_KEY, "")
            return None
        port = urlparse(endpoint).port
        if port is None or self.processes.owns_listen(identity, port) is not True:
            raise ManagerError("The saved router process does not own its recorded listen port.",
                               code="router_endpoint_unowned", status_code=409)
        return {"endpoint": endpoint, "identity": identity}

    def _inventory(self, endpoint: str, *, reload: bool = False) -> dict[str, dict[str, Any]]:
        url = endpoint.removesuffix("/v1") + "/models"
        try:
            response = httpx.get(url, params={"reload": "1"} if reload else None, timeout=10.0)
            response.raise_for_status()
            data = response.json().get("data")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise ManagerError("Could not read llama.cpp router model status.",
                               code="router_status_unavailable", status_code=503) from exc
        if not isinstance(data, list):
            raise ManagerError("llama.cpp router returned an invalid model list.",
                               code="router_status_invalid", status_code=502)
        return {item["id"]: item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)}

    @staticmethod
    def _model_state(model: dict[str, Any] | None) -> str | None:
        status = model.get("status") if isinstance(model, dict) else None
        return status.get("value") if isinstance(status, dict) and isinstance(status.get("value"), str) else None

    @staticmethod
    def _post(endpoint: str, route: str, payload: dict[str, str]) -> None:
        try:
            response = httpx.post(endpoint.removesuffix("/v1") + route,
                                  json=payload, timeout=_LOAD_TIMEOUT if route.endswith("/load") else 30.0)
            response.raise_for_status()
            if response.json().get("success") is not True:
                raise ValueError("llama.cpp did not confirm the request")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise ManagerError("llama.cpp router rejected the model lifecycle request.",
                               code="router_model_request_failed", status_code=409,
                               details={"model": payload.get("model")}) from exc

    def _record_observation(self, deployment: Deployment, record: dict[str, Any],
                            model: dict[str, Any] | None) -> Deployment:
        state = self._model_state(model)
        if state == "loaded":
            status = DeploymentStatus.running
        elif state == "loading":
            status = DeploymentStatus.starting
        elif isinstance(model, dict) and isinstance(model.get("status"), dict) and model["status"].get("failed"):
            status = DeploymentStatus.failed
        else:
            status = DeploymentStatus.stopped
        props = self.probe.props(record["endpoint"], model=deployment.id) if status == DeploymentStatus.running else None
        if status == DeploymentStatus.running and props is None:
            status = DeploymentStatus.unhealthy
        bundle = self.store.get_bundle(deployment.bundle_id or "")
        template_origin = _verified_loaded_template(bundle, deployment.applied_startup, props) if bundle and props else None
        identity = record["identity"] if status in {DeploymentStatus.running, DeploymentStatus.starting, DeploymentStatus.unhealthy} else None
        parsed = urlparse(record["endpoint"])
        applied_startup = {**deployment.applied_startup,
                           "host": parsed.hostname or "127.0.0.1", "port": parsed.port or 8080}
        settings = deployment.settings.model_copy(update={
            "startup": deployment.settings.startup.model_copy(update={"applied": applied_startup})
        })
        return self.store.put_deployment(deployment.model_copy(update={
            "status": status, "endpoint": record["endpoint"],
            "router_preset_id": deployment.id,
            "applied_startup": applied_startup, "settings": settings,
            "pid": identity.pid if identity else None, "process_identity": identity,
            "health": self.probe.health(record["endpoint"]) if status == DeploymentStatus.running else None,
            "server_props": props, "loaded_chat_template_origin": template_origin,
            "resource_usage": self.processes.resource_usage(identity) if identity else ResourceUsage(available=False, reason="model not loaded"),
            "error": ("Model-specific llama.cpp properties are not available yet."
                      if status == DeploymentStatus.unhealthy else
                      "llama.cpp could not load this configuration."
                      if status == DeploymentStatus.failed else None),
            "updated_at": utc_now(),
        }))

    def _managed_deployments(self) -> list[Deployment]:
        return [item for item in self.store.list_deployments() if item.scope == ManagementScope.managed]

    def _legacy_live(self) -> list[Deployment]:
        return [deployment for deployment in self._managed_deployments()
                if deployment.process_identity is not None
                and self.processes.classify(deployment.process_identity) in {"match", "unproven"}]

    @staticmethod
    def _sections(content: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for line in content.splitlines():
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
                sections[current] = []
            elif current is not None:
                sections[current].append(line)
        return {key: "\n".join(value) for key, value in sections.items()}

    def _mark_stopped(self, deployment: Deployment) -> Deployment:
        return self.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.stopped,
            "pid": None, "process_identity": None, "health": None,
            "server_props": None, "loaded_chat_template_origin": None,
            "resource_usage": ResourceUsage(available=False, reason="model not loaded"),
            "error": None, "updated_at": utc_now(),
        }))

    def _mark_all_stopped(self) -> None:
        for deployment in self._managed_deployments():
            identity = deployment.process_identity
            if identity is not None and self.processes.classify(identity) in {"match", "unproven"}:
                continue  # Never erase ownership of a process we did not stop.
            if deployment.status != DeploymentStatus.stopped or deployment.pid is not None or deployment.process_identity is not None:
                self._mark_stopped(deployment)

    def _require_managed(self, deployment_id: str) -> Deployment:
        deployment = self.store.get_deployment(deployment_id)
        if deployment is None:
            raise ManagerError("Unknown deployment", code="deployment_missing", status_code=404)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError("Connected endpoints have external lifecycle.",
                               code="connected_no_lifecycle", status_code=409)
        return deployment

    def _write_presets(self, content: str) -> None:
        temp = self._preset_path.with_suffix(".ini.tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(self._preset_path)

    def _presets(self) -> str:
        lines = ["version = 1"]
        for deployment in self._managed_deployments():
            bundle = self.store.get_bundle(deployment.bundle_id or "")
            if bundle is None or bundle.status != ImportStatus.complete or not bundle.disk_matches:
                continue
            try:
                argv = managed_argv("llama-server", bundle, deployment.applied_startup)
            except ManagerError:
                # Keep invalid historical records out of the shared router.
                # start() reports the exact error when that model is selected.
                continue
            values: list[tuple[str, str]] = []
            index = 1
            while index < len(argv):
                flag = argv[index]
                key = flag.lstrip("-")
                if flag in {"--jinja", "--embedding", "--reasoning-preserve", "--no-reasoning-preserve"}:
                    value = "true"
                    index += 1
                else:
                    value = argv[index + 1]
                    index += 2
                if key in {"host", "port", "alias"}:
                    continue  # Router owns its listen port and preset identity.
                if key == "m":
                    key = "model"
                if key == "chat-template" and ("\n" in value or "\r" in value):
                    self._template_path.mkdir(parents=True, exist_ok=True)
                    template_file = self._template_path / f"{deployment.id}.jinja"
                    template_file.write_text(value, encoding="utf-8")
                    key, value = "chat-template-file", str(template_file)
                values.append((key, _single_line(value, key=key)))
            lines.extend(["", f"[{deployment.id}]", "load-on-startup = false"])
            lines.extend(f"{key} = {value}" for key, value in values)
        return "\n".join(lines) + "\n"
