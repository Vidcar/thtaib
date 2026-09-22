"""Reusable inspection evidence in the existing application settings store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError
from workbench_backend.errors import ManagerError

from workbench_backend.inference.hashes import _cache_key
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ModelBundle
from workbench_backend.inference.store import RecordStore

T = TypeVar("T", bound=BaseModel)
INSPECTION_SCHEMA = 1


def bundle_identity(bundle: ModelBundle) -> list[Any]:
    """Stat plus a small edge fingerprint invalidates edited/replaced files."""
    return [bundle.managed_root, bundle.primary_path, [[item.sha256, item.size_bytes, item.role.value,
        item.ownership, list(_cache_key(Path(item.path)))] for item in {item.path: item for item in [*bundle.files, *bundle.companions]}.values()]]


def cached_inspection(
    store: RecordStore, bundle: ModelBundle, kind: str, schema: type[T],
    read: Callable[[], T], *, refresh: bool = False,
) -> tuple[T, bool, str]:
    key = f"model-inspection:{bundle.id}:{kind}"
    try:
        identity = bundle_identity(bundle)
    except OSError:
        raise ManagerError("Model files are missing or unavailable. Verify the installation to continue.",
                           code="model_inspection_unavailable", status_code=409) from None
    if not refresh:
        raw = store.get_setting(key)
        if raw:
            try:
                record = json.loads(raw)
                if record["schema"] == INSPECTION_SCHEMA and record["identity"] == identity:
                    return schema.model_validate(record["value"]), True, str(record["inspected_at"])
            except (ValueError, KeyError, TypeError, ValidationError):
                pass
    value = read()
    inspected_at = utc_now()
    # Do not cache a read spanning a file replacement.
    try:
        unchanged = bundle_identity(bundle) == identity
    except OSError:
        unchanged = False
    if not unchanged:
        raise ManagerError("Model files changed during inspection. Refresh the model details to retry.",
                           code="model_changed_during_inspection", status_code=409)
    store.put_bundle_setting(bundle.id, key, json.dumps({"schema": INSPECTION_SCHEMA, "identity": identity,
        "value": value.model_dump(mode="json"), "inspected_at": inspected_at}))
    return value, False, inspected_at
