"""Explicit activation of a verified clean-root restore on backend restart."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from workbench_backend.state.backup import BackupError, _verify_application_schema_compatible
from workbench_backend.inference.ids import utc_now
from workbench_backend.local_trust import ensure_shared_secret
from workbench_backend.paths import WorkbenchPaths


def register_restore(store, result) -> None:
    with store._lock, store._conn:
        store._conn.execute("INSERT OR REPLACE INTO restored_roots VALUES (?, ?, ?)",
            (str(Path(result.destination_root).resolve()), result.manifest.backup_id, utc_now()))


def prepare_activation(state, destination_root: str) -> str:
    destination = Path(destination_root).resolve()
    if destination == state.manager.paths.root:
        raise BackupError("This application root is already active.", code="restore_already_active")
    with state.app_store._lock:
        table = state.app_store._conn.execute("SELECT 1 FROM sqlite_master WHERE name='restored_roots'").fetchone()
        known = table and state.app_store._conn.execute("SELECT 1 FROM restored_roots WHERE root=?", (str(destination),)).fetchone()
    if not known:
        raise BackupError("Only a validated restore created by this application can be activated.", code="restore_not_registered")
    database = destination / "application.sqlite"
    if not database.is_file():
        raise BackupError("The restored database is missing.", code="restore_missing")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("The restored database failed its integrity check.", code="restore_integrity")
    _verify_application_schema_compatible(destination)
    ensure_shared_secret(WorkbenchPaths(destination))
    marker = state.manager.paths.state / "active-data-root.json"
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "destination_root": str(destination)}), encoding="utf-8")
    temporary.replace(marker)
    return str(destination)
