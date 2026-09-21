"""A clean restore activates only after validation and receives fresh authorization."""
import json
import tempfile
import unittest
import threading
from pathlib import Path
from types import SimpleNamespace

from workbench_backend.local_trust import ensure_shared_secret
from workbench_backend.paths import WorkbenchPaths, resolve_data_root
from workbench_backend.state.activation import register_restore, prepare_activation
from workbench_backend.state.backup import BackupService, BackupCreateRequest, BackupRestoreRequest, BackupError, MaintenanceGate
from workbench_backend.state.store import ApplicationStore
from workbench_backend.state.preferences import PreferenceStore
from workbench_backend.lab.snapshot import capture_project_snapshot, verify_snapshot_tree
from workbench_backend.lab.schemas import SnapshotManifest
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.inference.ids import utc_now
from tests.support import close_workbench_sqlite


class RestoreActivationTests(unittest.TestCase):
    def test_backup_waits_for_owned_work_with_new_mutations_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = WorkbenchPaths(Path(temporary) / "data").ensure()
            store = ApplicationStore(paths)
            gate = MaintenanceGate()
            observed, release = threading.Event(), threading.Event()
            reconciled = []
            results, errors = [], []
            def active_work():
                observed.set()
                return [] if release.is_set() else ["owned-run"]
            service = BackupService(paths, store, maintenance_gate=gate, active_work=active_work,
                reconcile=lambda: reconciled.append(True), quiescence_timeout=3)
            def create():
                try:
                    results.append(service.create_backup(BackupCreateRequest(destination=str(Path(temporary) / "safe.zip"))))
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=create)
            worker.start()
            try:
                self.assertTrue(observed.wait(2))
                with self.assertRaises(BackupError):
                    with gate.mutation():
                        self.fail("New work entered maintenance")
                release.set()
                worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(results), 1)
                self.assertEqual(reconciled, [True])
            finally:
                release.set()
                worker.join(5)
                close_workbench_sqlite(store)

    def test_restore_rebases_owned_workspace_and_complete_snapshot_tree_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = WorkbenchPaths(Path(temporary) / "original").ensure()
            workspace = paths.workspaces / "branch"
            workspace.mkdir()
            (workspace / "kept.txt").write_text("branch bytes", encoding="utf-8")
            snapshot = capture_project_snapshot(paths, workspace_id="branch", project_root=workspace, kind="starting")
            store = ApplicationStore(paths)
            try:
                store.put_conversation(ChatConversation(id="branch", deployment_id="model", project_path=str(workspace),
                    area_kind="project", area_project_path=str(workspace), created_at=utc_now(), updated_at=utc_now()))
                service = BackupService(paths, store)
                archive = service.create_backup(BackupCreateRequest(destination=str(Path(temporary) / "saved.zip")))
                destination = Path(temporary) / "restored"
                service.restore_backup(BackupRestoreRequest(archive_path=archive.archive_path, destination_root=str(destination)))
                restored_manifest = SnapshotManifest.model_validate_json((destination / "snapshots" / snapshot.id / "manifest.json").read_text())
                self.assertEqual(Path(restored_manifest.tree_path), destination / "snapshots" / snapshot.id / "tree")
                verify_snapshot_tree(Path(restored_manifest.tree_path), restored_manifest.included_files)
                restored = ApplicationStore(WorkbenchPaths(destination))
                try:
                    conversation = restored.get_conversation("branch")
                    self.assertEqual(Path(conversation.project_path), destination / "workspaces" / "branch")
                    self.assertEqual(conversation.area_project_path, str(workspace))
                    self.assertEqual((Path(conversation.project_path) / "kept.txt").read_text(), "branch bytes")
                finally:
                    close_workbench_sqlite(restored)
            finally:
                close_workbench_sqlite(store)

    def test_verified_restore_activation_preserves_original_and_uses_new_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = WorkbenchPaths(Path(temporary) / "original").ensure()
            store = ApplicationStore(paths)
            try:
                old_token = ensure_shared_secret(paths)
                service = BackupService(paths, store)
                archive = service.create_backup(BackupCreateRequest(destination=str(Path(temporary) / "saved.zip")))
                result = service.restore_backup(BackupRestoreRequest(archive_path=archive.archive_path,
                    destination_root=str(Path(temporary) / "restored")))
                state = SimpleNamespace(manager=SimpleNamespace(paths=paths), app_store=store)
                with self.assertRaises(BackupError):
                    prepare_activation(state, result.destination_root)
                self.assertFalse((paths.state / "active-data-root.json").exists())
                register_restore(store, result)
                activated = prepare_activation(state, result.destination_root)
                self.assertEqual(resolve_data_root(environ={"WORKBENCH_DATA_ROOT": str(paths.root)}), Path(activated))
                self.assertNotEqual(ensure_shared_secret(WorkbenchPaths(Path(activated))), old_token)
                self.assertTrue(paths.application_db.exists())
                self.assertTrue(Path(archive.archive_path).exists())
            finally:
                close_workbench_sqlite(store)

    def test_invalid_activation_chain_does_not_silently_create_an_empty_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = WorkbenchPaths(Path(temporary)).ensure()
            (paths.state / "active-data-root.json").write_text(json.dumps({"version": 1,
                "destination_root": str(paths.root / "missing")}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unavailable"):
                resolve_data_root(environ={"WORKBENCH_DATA_ROOT": str(paths.root)})

    def test_notification_claim_is_durable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = WorkbenchPaths(Path(temporary)).ensure()
            store = ApplicationStore(paths)
            try:
                preferences = PreferenceStore(store)
                self.assertTrue(preferences.notification_claim("run:question:one"))
                self.assertFalse(preferences.notification_claim("run:question:one"))
            finally:
                close_workbench_sqlite(store)
            store = ApplicationStore(paths)
            try:
                preferences = PreferenceStore(store)
                self.assertTrue(preferences.notification_sent("run:question:one"))
                self.assertFalse(preferences.notification_claim("run:question:one"))
                self.assertTrue(preferences.notification_claim("run:question:two"))
            finally:
                close_workbench_sqlite(store)
