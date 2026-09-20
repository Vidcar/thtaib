"""Shared test helpers for the model manager."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gguf import GGUFWriter

from workbench_backend.contracts.auth import WORKBENCH_LOCAL_TOKEN_HEADER
from workbench_backend.state.checkpointer import close_all_sqlite_checkpointers
from workbench_backend.state.store import ApplicationStore


def workbench_client(application: FastAPI, *, token: str | None = None) -> TestClient:
    """Test client that presents the local shared-secret token by default."""
    headers = {}
    if token != "":
        headers[WORKBENCH_LOCAL_TOKEN_HEADER] = token or application.state.local_trust_token
    return TestClient(application, headers=headers)


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
