"""Backup restore and activation reject incompatible application schemas safely."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.activation import prepare_activation, register_restore
from workbench_backend.state.backup import (
    BackupCreateRequest,
    BackupError,
    BackupRestoreRequest,
    BackupService,
    _verify_application_schema_compatible,
)
from workbench_backend.state.store import ApplicationStore

from tests.support import close_workbench_sqlite


class BackupSchemaCompatibilityTests(unittest.TestCase):
    def test_schema_validation_preserves_live_wal_sidecars_and_committed_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = WorkbenchPaths(root / "source").ensure()
            store = ApplicationStore(paths)
            close_workbench_sqlite(store)

            keeper = sqlite3.connect(str(paths.application_db))
            try:
                keeper.execute("PRAGMA journal_mode=WAL")
                keeper.execute(
                    "CREATE TABLE IF NOT EXISTS wal_probe(id TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                keeper.execute("INSERT INTO wal_probe VALUES ('probe', 'committed-in-wal')")
                keeper.commit()
                wal_path = paths.application_db.with_name(f"{paths.application_db.name}-wal")
                self.assertTrue(wal_path.exists())

                _verify_application_schema_compatible(paths.root)

                self.assertTrue(wal_path.exists())
                row = keeper.execute("SELECT value FROM wal_probe WHERE id='probe'").fetchone()
                self.assertEqual(row[0], "committed-in-wal")
            finally:
                keeper.close()

    def test_restore_rejects_future_application_schema_without_copying_or_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = WorkbenchPaths(root / "source").ensure()
            store = ApplicationStore(paths)
            try:
                service = BackupService(paths, store)
                archive = service.create_backup(BackupCreateRequest(destination=str(root / "backup.zip")))
            finally:
                close_workbench_sqlite(store)

            incompatible = root / "future-schema.zip"
            _rewrite_archive_application_db(
                Path(archive.archive_path),
                incompatible,
                root / "future-work",
                lambda conn: conn.execute("UPDATE schema_meta SET value='99' WHERE key='schema_version'"),
            )
            archive_hash_before = sha256_file(incompatible)
            destination = root / "restore-future"

            reopened = ApplicationStore(paths)
            try:
                with self.assertRaises(BackupError) as error:
                    BackupService(paths, reopened).restore_backup(
                        BackupRestoreRequest(archive_path=str(incompatible), destination_root=str(destination))
                    )
            finally:
                close_workbench_sqlite(reopened)

            self.assertEqual(error.exception.code, "application_schema_incompatible")
            self.assertFalse(destination.exists())
            self.assertEqual(sha256_file(incompatible), archive_hash_before)
            self.assertEqual(_schema_version(paths.application_db), "2")

    def test_restore_migrates_supported_v1_application_schema_before_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = WorkbenchPaths(root / "source").ensure()
            project = paths.root / "missing-project"
            project.mkdir()
            now = utc_now()
            store = ApplicationStore(paths)
            try:
                store.put_conversation(
                    ChatConversation(
                        id="chat_v1_restore",
                        deployment_id="dep",
                        project_path=str(project),
                        area_kind="project",
                        area_project_path=str(project),
                        thread_id="thread_v1",
                        transcript=[ChatMessage(role="user", content="hello", at=now)],
                        created_at=now,
                        updated_at=now,
                    )
                )
                service = BackupService(paths, store)
                archive = service.create_backup(BackupCreateRequest(destination=str(root / "backup.zip")))
            finally:
                close_workbench_sqlite(store)

            legacy = root / "v1-schema.zip"
            _rewrite_archive_application_db(
                Path(archive.archive_path),
                legacy,
                root / "v1-work",
                _downgrade_chat_identity_to_v1,
            )
            destination = root / "restore-v1"
            reopened = ApplicationStore(paths)
            try:
                BackupService(paths, reopened).restore_backup(
                    BackupRestoreRequest(archive_path=str(legacy), destination_root=str(destination))
                )
            finally:
                close_workbench_sqlite(reopened)

            self.assertEqual(_schema_version(destination / "application.sqlite"), "2")
            restored = ApplicationStore(WorkbenchPaths(destination))
            try:
                conversation = restored.get_conversation("chat_v1_restore")
                self.assertIsNotNone(conversation)
                assert conversation is not None
                self.assertEqual(conversation.area_kind, "project")
                self.assertEqual(conversation.area_id, str(project))
                self.assertEqual(conversation.area_project_path, str(project))
                self.assertEqual(conversation.thread_id, "thread_v1")
                self.assertEqual(conversation.transcript[0].content, "hello")
            finally:
                close_workbench_sqlite(restored)

    def test_restore_rejects_invalid_v1_application_schema_without_activating_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = WorkbenchPaths(root / "source").ensure()
            store = ApplicationStore(paths)
            try:
                service = BackupService(paths, store)
                archive = service.create_backup(BackupCreateRequest(destination=str(root / "backup.zip")))
            finally:
                close_workbench_sqlite(store)

            invalid = root / "invalid-v1.zip"
            _rewrite_archive_application_db(
                Path(archive.archive_path),
                invalid,
                root / "invalid-work",
                _insert_invalid_v1_conversation,
            )
            destination = root / "restore-invalid"
            reopened = ApplicationStore(paths)
            try:
                with self.assertRaises(BackupError) as error:
                    BackupService(paths, reopened).restore_backup(
                        BackupRestoreRequest(archive_path=str(invalid), destination_root=str(destination))
                    )
            finally:
                close_workbench_sqlite(reopened)

            self.assertEqual(error.exception.code, "application_db_invalid")
            self.assertFalse(destination.exists())

    def test_activation_rejects_registered_future_schema_without_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = WorkbenchPaths(root / "source").ensure()
            store = ApplicationStore(paths)
            try:
                service = BackupService(paths, store)
                archive = service.create_backup(BackupCreateRequest(destination=str(root / "backup.zip")))
                result = service.restore_backup(
                    BackupRestoreRequest(
                        archive_path=archive.archive_path,
                        destination_root=str(root / "restored"),
                    )
                )
                register_restore(store, result)
                _set_schema_version(Path(result.destination_root) / "application.sqlite", "99")
                state = SimpleNamespace(manager=SimpleNamespace(paths=paths), app_store=store)

                with self.assertRaises(BackupError) as error:
                    prepare_activation(state, result.destination_root)

                self.assertEqual(error.exception.code, "application_schema_incompatible")
                self.assertFalse((paths.state / "active-data-root.json").exists())
            finally:
                close_workbench_sqlite(store)


def _rewrite_archive_application_db(
    source_archive: Path,
    destination_archive: Path,
    workdir: Path,
    mutate: Callable[[sqlite3.Connection], object],
) -> None:
    if workdir.exists():
        raise AssertionError(f"Fixture rewrite directory already exists: {workdir}")
    workdir.mkdir()
    with zipfile.ZipFile(source_archive, "r") as zf:
        zf.extractall(workdir)
    conn = sqlite3.connect(str(workdir / "application.sqlite"))
    try:
        mutate(conn)
        conn.commit()
    finally:
        conn.close()
    _refresh_manifest_hashes(workdir)
    with zipfile.ZipFile(destination_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(workdir.rglob("*"), key=lambda item: item.as_posix()):
            relative = path.relative_to(workdir).as_posix()
            if path.is_dir():
                if not any(path.iterdir()):
                    zf.writestr(f"{relative}/", b"")
                continue
            zf.write(path, relative)


def _refresh_manifest_hashes(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = root / item["path"]
        item["size_bytes"] = path.stat().st_size
        item["sha256"] = sha256_file(path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _downgrade_chat_identity_to_v1(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE schema_meta SET value='1' WHERE key='schema_version'")
    row = conn.execute("SELECT id, payload FROM conversations WHERE id='chat_v1_restore'").fetchone()
    assert row is not None
    payload = json.loads(row[1])
    for key in ("area_kind", "area_id", "area_label", "area_project_path", "area_workspace_id"):
        payload.pop(key, None)
    conn.execute("UPDATE conversations SET payload=? WHERE id=?", (json.dumps(payload), row[0]))


def _insert_invalid_v1_conversation(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE schema_meta SET value='1' WHERE key='schema_version'")
    now = utc_now()
    payload = {
        "id": "chat_invalid_v1",
        "deployment_id": "dep",
        "transcript": [{"role": "user", "content": "missing timestamp"}],
        "created_at": now,
        "updated_at": now,
    }
    conn.execute(
        "INSERT INTO conversations(id, payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (payload["id"], json.dumps(payload), now, now),
    )


def _schema_version(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        assert row is not None
        return str(row[0])
    finally:
        conn.close()


def _set_schema_version(path: Path, version: str) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("UPDATE schema_meta SET value=? WHERE key='schema_version'", (version,))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
