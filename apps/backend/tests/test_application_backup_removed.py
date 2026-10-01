"""Application backup and restore are gone. Checkpoints and existing files stay."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workbench_backend.app import create_app
from workbench_backend.paths import WorkbenchPaths, resolve_data_root
from workbench_backend.state.checkpointer import checkpoint_head_id, open_sqlite_checkpointer
from tests.support import close_workbench_sqlite, offline_workbench_client


class ApplicationBackupRemovedTests(unittest.TestCase):
    def test_backup_routes_are_gone_and_existing_files_stay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            archive = Path(temporary) / "already-saved.workbench-backup.zip"
            archive.write_bytes(b"existing-backup")
            weights = Path(temporary) / "weights.gguf"
            weights.write_bytes(b"weights")
            project = Path(temporary) / "project"
            project.mkdir()
            (project / "notes.txt").write_text("project file", encoding="utf-8")
            application = create_app(data_root=root)
            try:
                paths = application.state.manager.paths
                self.assertEqual(paths.checkpoints_db, paths.root / "checkpoints.sqlite")
                self.assertNotEqual(paths.checkpoints_db, paths.application_db)
                with offline_workbench_client(application) as client:
                    body = {
                        "destination": str(Path(temporary) / "new-backup.zip"),
                        "include_browser_profiles": True,
                        "archive_path": str(archive),
                        "destination_root": str(Path(temporary) / "restored"),
                    }
                    for path in ("/v1/backups", "/v1/backups/restore", "/v1/backups/activate"):
                        posted = client.post(path, json=body)
                        self.assertEqual(posted.status_code, 404, posted.text)
                        fetched = client.get(path)
                        self.assertEqual(fetched.status_code, 404, fetched.text)
                    routes = {getattr(route, "path", "") for route in application.routes}
                    self.assertFalse(any("backup" in path for path in routes))
                    self.assertFalse(hasattr(application.state, "backups"))
                open_sqlite_checkpointer(paths.checkpoints_db)
                self.assertIsNone(checkpoint_head_id(paths.checkpoints_db, "thread-without-history"))
                self.assertTrue(paths.checkpoints_db.is_file())
                self.assertTrue(paths.application_db.is_file())
            finally:
                close_workbench_sqlite(application)
            self.assertEqual(archive.read_bytes(), b"existing-backup")
            self.assertFalse((Path(temporary) / "new-backup.zip").exists())
            self.assertFalse((Path(temporary) / "restored").exists())
            self.assertEqual(weights.read_bytes(), b"weights")
            self.assertEqual((project / "notes.txt").read_text(encoding="utf-8"), "project file")

    def test_existing_data_root_pointer_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / "original"
            activated = Path(temporary) / "activated"
            original_paths = WorkbenchPaths(original).ensure()
            activated_paths = WorkbenchPaths(activated).ensure()
            original_paths.application_db.write_bytes(b"older-chats")
            activated_paths.application_db.write_bytes(b"live-chats")
            original_paths.checkpoints_db.write_bytes(b"older-checkpoints")
            activated_paths.checkpoints_db.write_bytes(b"live-checkpoints")
            (original_paths.models / "weight.gguf").write_bytes(b"original-weights")
            (activated_paths.models / "weight.gguf").write_bytes(b"activated-weights")
            destination = str(activated.resolve())
            marker = original_paths.state / "active-data-root.json"
            marker.write_text(json.dumps({"version": 1, "destination_root": destination}), encoding="utf-8")
            self.assertEqual(
                resolve_data_root(environ={"WORKBENCH_DATA_ROOT": str(original)}),
                Path(destination),
            )
            self.assertEqual(marker.read_text(encoding="utf-8"), json.dumps({"version": 1, "destination_root": destination}))
            self.assertEqual(original_paths.application_db.read_bytes(), b"older-chats")
            self.assertEqual(activated_paths.application_db.read_bytes(), b"live-chats")
            self.assertEqual(original_paths.checkpoints_db.read_bytes(), b"older-checkpoints")
            self.assertEqual(activated_paths.checkpoints_db.read_bytes(), b"live-checkpoints")
            self.assertEqual((original_paths.models / "weight.gguf").read_bytes(), b"original-weights")
            self.assertEqual((activated_paths.models / "weight.gguf").read_bytes(), b"activated-weights")
            missing = original_paths.root / "missing"
            marker.write_text(json.dumps({"version": 1, "destination_root": str(missing)}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unavailable"):
                resolve_data_root(environ={"WORKBENCH_DATA_ROOT": str(original)})
            self.assertFalse(missing.exists())
