"""Shared test helpers for the model manager."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gguf import GGUFWriter

from workbench_backend.contracts.auth import WORKBENCH_LOCAL_TOKEN_HEADER
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.process import HttpProbe
from workbench_backend.inference.schemas import HealthReport, ServerProperties
from workbench_backend.state.checkpointer import close_all_sqlite_checkpointers
from workbench_backend.state.store import ApplicationStore


TERMINAL_RUN_STATUSES = {"completed", "cancelled", "failed"}


def wait_for_import(client: TestClient, job: dict[str, Any], timeout: float = 5) -> dict[str, Any]:
    """Observe the durable asynchronous API job, bounded by actual terminal state."""
    deadline = time.monotonic() + timeout
    while job["status"] in {"pending", "running", "stopping"}:
        if time.monotonic() >= deadline:
            raise AssertionError(f"Import did not terminate: {job}")
        time.sleep(0.01)
        response = client.get(f"/v1/imports/{job['id']}")
        response.raise_for_status()
        job = response.json()
    return job


def workbench_client(application: FastAPI, *, token: str | None = None) -> TestClient:
    """Test client that presents the local shared-secret token by default."""
    headers = {}
    if token != "":
        headers[WORKBENCH_LOCAL_TOKEN_HEADER] = token or application.state.local_trust_token
    return TestClient(application, headers=headers)


class OfflineProbe(HttpProbe):
    """Opt-in probe for scripted fixtures with no live local model server."""

    def health(self, endpoint: str) -> HealthReport:
        return HealthReport(
            healthy=False,
            endpoint=endpoint,
            checked=utc_now(),
            detail="scripted fixture: no live server",
        )

    def props(self, endpoint: str) -> ServerProperties | None:
        return None

    def smoke(self, endpoint: str) -> tuple[bool, str]:
        return False, "scripted fixture: no live server"


def offline_workbench_client(application: FastAPI, *, token: str | None = None) -> TestClient:
    """Client for scripted fixtures that intentionally have no live model server."""
    application.state.manager.deployments.probe = OfflineProbe()
    return workbench_client(application, token=token)


def close_workbench_sqlite(*objects: object) -> None:
    """Close application/checkpointer connections before TemporaryDirectory cleanup."""
    stores: list[ApplicationStore] = []
    for obj in objects:
        if obj is None:
            continue
        if isinstance(obj, ApplicationStore):
            stores.append(obj)
            continue
        app = getattr(obj, "app", None)
        if app is not None and getattr(app, "state", None) is not None:
            obj = app
        state = getattr(obj, "state", None)
        if state is None:
            continue
        manager = getattr(state, "manager", None)
        runner = getattr(manager, "imports", None)
        closer = getattr(runner, "close", None)
        if callable(closer):
            closer()
        store = getattr(state, "app_store", None)
        if isinstance(store, ApplicationStore):
            stores.append(store)
        for owner_name in ("harness", "chat"):
            owner = getattr(state, owner_name, None)
            if owner is None:
                continue
            owner_close = getattr(owner, "close", None)
            if callable(owner_close) and owner_name == "harness":
                owner_close()
            owned = getattr(owner, "_app_store", None)
            if isinstance(owned, ApplicationStore):
                stores.append(owned)
    seen: set[int] = set()
    for store in stores:
        marker = id(store)
        if marker in seen:
            continue
        seen.add(marker)
        store.close()
    close_all_sqlite_checkpointers()


def wait_for_run(client: TestClient, run_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") in TERMINAL_RUN_STATUSES:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish: {body}")


def wait_for_status(
    client: TestClient,
    run_id: str,
    status: str,
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") == status:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not reach {status}: {body}")


def wait_for_lab_result(client: TestClient, result_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/v1/lab/results/{result_id}")
        body = response.json()
        evidence = body.get("evidence") or {}
        if evidence.get("executable_checks") or body.get("judgement") or body.get("deviations"):
            run = client.get(f"/v1/agent-runs/{body['agent_run_id']}").json()
            if run.get("status") in TERMINAL_RUN_STATUSES:
                return client.get(f"/v1/lab/results/{result_id}").json()
        time.sleep(0.05)
    raise TimeoutError(f"lab result {result_id} did not finish: {body}")


def write_tiny_gguf(
    path: Path,
    *,
    name: str = "tiny-test",
    context_length: int | None = None,
    block_count: int | None = None,
    extra_uint32: dict[str, int] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = GGUFWriter(str(path), "llama")
    writer.add_name(name)
    writer.add_quantization_version(2)
    writer.add_file_type(0)
    if context_length is not None:
        writer.add_context_length(context_length)
    if block_count is not None:
        writer.add_block_count(block_count)
    for key, value in (extra_uint32 or {}).items():
        writer.add_uint32(key, value)
    writer.add_tensor("token_embd.weight", np.zeros((2, 2), dtype=np.float32))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return path
