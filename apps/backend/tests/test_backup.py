"""STATE-011 manual backup and clean-root restore tests."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.backup import (
    BackupCreateRequest,
    BackupError,
    BackupRestoreRequest,
    BackupService,
    MaintenanceGate,
)
from workbench_backend.state.checkpointer import copy_checkpoints_for_backup
from workbench_backend.state.store import ApplicationStore
from workbench_backend.inference.hashes import sha256_file

from tests.support import close_workbench_sqlite
from tests.test_retained_assets import b64


class BackupServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "source"
        self.paths = WorkbenchPaths(self.root).ensure()
        self.store = ApplicationStore(self.paths)
        self.gate = MaintenanceGate()
        self.service = BackupService(self.paths, self.store, maintenance_gate=self.gate)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.store)
        self.tmp.cleanup()

    def put_conversation(self, conversation_id: str, *, project_path: str | None = None) -> None:
        self.store.put_conversation(
            ChatConversation(
                id=conversation_id,
                deployment_id="dep",
                area_kind="project" if project_path else "general",
                area_project_path=project_path,
                project_path=project_path,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

    def test_backup_restore_captures_application_db_checkpoints_assets_and_json_records(self) -> None:
        project = self.root.parent / "missing-project"
        self.put_conversation("chat_backup", project_path=str(project))
        RetainedAssetService(self.store).retain_upload(
            RetainedUploadRequest(
                session_id="chat_backup",
                filename="notes.txt",
                content_type="text/plain",
                content_base64=b64("retained bytes"),
            )
        )
        (self.paths.knowledge / "entries.json").write_text("[]", encoding="utf-8")
        (self.paths.state / "bundles.json").write_text("[]", encoding="utf-8")
        (self.paths.cases / "case.json").write_text('{"case": true}', encoding="utf-8")
        (self.paths.snapshots / "snap_1").mkdir()
        (self.paths.snapshots / "snap_1" / "manifest.json").write_text("{}", encoding="utf-8")
        sqlite3.connect(self.paths.checkpoints_db).close()

        archive = self.root.parent / "backup.zip"
        result = self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        self.assertTrue(archive.is_file())
        self.assertIn("application.sqlite", result.manifest.included_roots)
        self.assertIn("checkpoints.sqlite", result.manifest.included_roots)
        self.assertIn("knowledge", result.manifest.included_roots)
        self.assertIn("state/bundles.json", result.manifest.included_roots)
        self.assertTrue(result.manifest.credentials_excluded)

        restore_root = self.root.parent / "restore"
        restored = self.service.restore_backup(
            BackupRestoreRequest(archive_path=str(archive), destination_root=str(restore_root))
        )
        self.assertFalse(restored.activated)
        self.assertEqual(len(restored.missing_dependencies), 1)
        self.assertEqual(restored.missing_dependencies[0].kind, "project")
        self.assertTrue((restore_root / "application.sqlite").is_file())
        self.assertTrue((restore_root / "checkpoints.sqlite").is_file())
        self.assertTrue((restore_root / "knowledge" / "entries.json").is_file())
        self.assertTrue((restore_root / "cases" / "case.json").is_file())
        self.assertTrue((restore_root / "snapshots" / "snap_1" / "manifest.json").is_file())

        conn = sqlite3.connect(str(restore_root / "application.sqlite"))
        try:
            row = conn.execute("SELECT content FROM retained_assets").fetchone()
        finally:
            conn.close()
        self.assertEqual(bytes(row[0]), b"retained bytes")

    def test_backup_captures_runtime_and_state_records_and_empty_snapshot_dirs(self) -> None:
        (self.paths.state / "bundles.json").write_text("[]", encoding="utf-8")
        (self.paths.state / "profiles.json").write_text("[]", encoding="utf-8")
        (self.paths.state / "deployments.json").write_text("[]", encoding="utf-8")
        (self.paths.state / "import_jobs.json").write_text("[]", encoding="utf-8")
        (self.paths.runtimes / "runtime-manifest.json").write_text('{"runtime": true}', encoding="utf-8")
        (self.paths.snapshots / "snap_empty" / "tree").mkdir(parents=True)
        (self.paths.workspaces / "ws_branch" / "project").mkdir(parents=True)
        (self.paths.workspaces / "ws_branch" / "project" / "file.txt").write_text("owned", encoding="utf-8")

        archive = self.root.parent / "records.zip"
        result = self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        self.assertIn("state/bundles.json", result.manifest.included_roots)
        self.assertIn("state/profiles.json", result.manifest.included_roots)
        self.assertIn("state/deployments.json", result.manifest.included_roots)
        self.assertIn("state/import_jobs.json", result.manifest.included_roots)
        self.assertIn("runtimes/runtime-manifest.json", result.manifest.included_roots)
        self.assertIn("workspaces", result.manifest.included_roots)
        self.assertIn("snapshots/snap_empty/tree", result.manifest.directories)

        restore_root = self.root.parent / "records-restore"
        self.service.restore_backup(
            BackupRestoreRequest(archive_path=str(archive), destination_root=str(restore_root))
        )
        self.assertTrue((restore_root / "state" / "bundles.json").is_file())
        self.assertTrue((restore_root / "runtimes" / "runtime-manifest.json").is_file())
        self.assertTrue((restore_root / "snapshots" / "snap_empty" / "tree").is_dir())
        self.assertEqual((restore_root / "workspaces" / "ws_branch" / "project" / "file.txt").read_text(encoding="utf-8"), "owned")

    def test_backup_rejects_active_work_and_gate_blocks_mutations_when_active(self) -> None:
        service = BackupService(
            self.paths,
            self.store,
            maintenance_gate=self.gate,
            active_work=lambda: ["run_active"],
            quiescence_timeout=0,
        )
        with self.assertRaises(BackupError) as active:
            service.create_backup(BackupCreateRequest(destination=str(self.root.parent / "backup.zip")))
        self.assertEqual(active.exception.code, "backup_not_quiescent")

        self.gate.begin("test")
        try:
            with self.assertRaises(BackupError) as blocked:
                self.gate.reject_if_active()
            self.assertEqual(blocked.exception.code, "maintenance_gate_active")
        finally:
            self.gate.end()

    def test_backup_gate_failure_does_not_leave_staging_directory(self) -> None:
        self.gate.begin("already_active")
        try:
            with self.assertRaises(BackupError) as error:
                self.service.create_backup(BackupCreateRequest(destination=str(self.root.parent / "blocked.zip")))
            self.assertEqual(error.exception.code, "maintenance_active")
        finally:
            self.gate.end()
        staging_root = self.paths.state / "backup-staging"
        self.assertFalse(staging_root.exists() and any(staging_root.iterdir()))

    def test_backup_external_references_include_archived_conversations(self) -> None:
        missing_project = self.root.parent / "archived-project"
        self.store.put_conversation(
            ChatConversation(
                id="chat_archived",
                deployment_id="dep",
                area_kind="project",
                area_project_path=str(missing_project),
                project_path=str(missing_project),
                archived=True,
                archived_at=utc_now(),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

        result = self.service.create_backup(BackupCreateRequest(destination=str(self.root.parent / "archived.zip")))

        project_refs = [ref for ref in result.manifest.external_references if ref.kind == "project"]
        self.assertEqual(len(project_refs), 1)
        self.assertEqual(project_refs[0].path, str(missing_project))
        self.assertTrue(project_refs[0].missing)

    def test_maintenance_gate_waits_for_mutation_then_rechecks_active_work(self) -> None:
        release = threading.Event()
        entered = threading.Event()

        def mutate() -> None:
            with self.gate.mutation():
                entered.set()
                release.wait(timeout=5)

        thread = threading.Thread(target=mutate)
        thread.start()
        self.assertTrue(entered.wait(timeout=2))
        active_after_gate = {"value": True}
        service = BackupService(
            self.paths,
            self.store,
            maintenance_gate=self.gate,
            active_work=lambda: ["run_after_gate"] if active_after_gate["value"] else [],
            quiescence_timeout=0,
        )
        errors: list[BackupError] = []

        def backup() -> None:
            try:
                service.create_backup(BackupCreateRequest(destination=str(self.root.parent / "race.zip")))
            except BackupError as exc:
                errors.append(exc)

        backup_thread = threading.Thread(target=backup)
        backup_thread.start()
        time.sleep(0.1)
        self.assertEqual(self.gate.active_reason, "manual_backup")
        with self.assertRaises(BackupError) as blocked:
            with self.gate.mutation():
                pass
        self.assertEqual(blocked.exception.code, "maintenance_gate_active")
        release.set()
        thread.join(timeout=2)
        backup_thread.join(timeout=2)
        self.assertEqual(errors[0].code, "backup_not_quiescent")

    def test_restore_rejects_dirty_destination_traversal_and_corruption(self) -> None:
        archive = self.root.parent / "backup.zip"
        self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        with self.assertRaises(BackupError) as exists:
            self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        self.assertEqual(exists.exception.code, "backup_archive_exists")

        dirty = self.root.parent / "dirty"
        dirty.mkdir()
        (dirty / "file.txt").write_text("occupied", encoding="utf-8")
        with self.assertRaises(BackupError) as dirty_error:
            self.service.restore_backup(BackupRestoreRequest(archive_path=str(archive), destination_root=str(dirty)))
        self.assertEqual(dirty_error.exception.code, "restore_destination_not_clean")

        traversal = self.root.parent / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as zf:
            zf.writestr("../escape.txt", "bad")
        with self.assertRaises(BackupError) as traversal_error:
            self.service.restore_backup(
                BackupRestoreRequest(
                    archive_path=str(traversal),
                    destination_root=str(self.root.parent / "restore-traversal"),
                )
            )
        self.assertEqual(traversal_error.exception.code, "unsafe_backup_path")

        unsafe = self.root.parent / "unsafe.zip"
        with zipfile.ZipFile(unsafe, "w") as zf:
            zf.writestr("state/con:bad.txt", "bad")
        with self.assertRaises(BackupError) as unsafe_error:
            self.service.restore_backup(
                BackupRestoreRequest(
                    archive_path=str(unsafe),
                    destination_root=str(self.root.parent / "restore-unsafe"),
                )
            )
        self.assertEqual(unsafe_error.exception.code, "unsafe_backup_path")

        duplicate = self.root.parent / "duplicate.zip"
        with zipfile.ZipFile(duplicate, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("manifest.json", "{}")
        with self.assertRaises(BackupError) as duplicate_error:
            self.service.restore_backup(
                BackupRestoreRequest(
                    archive_path=str(duplicate),
                    destination_root=str(self.root.parent / "restore-duplicate"),
                )
            )
        self.assertEqual(duplicate_error.exception.code, "restore_duplicate_member")

        collision = self.root.parent / "collision.zip"
        with zipfile.ZipFile(collision, "w") as zf:
            zf.writestr("state", "file")
            zf.writestr("state/bundles.json", "[]")
        with self.assertRaises(BackupError) as collision_error:
            self.service.restore_backup(
                BackupRestoreRequest(
                    archive_path=str(collision),
                    destination_root=str(self.root.parent / "restore-collision"),
                )
            )
        self.assertEqual(collision_error.exception.code, "restore_path_collision")

        corrupt = self.root.parent / "corrupt.zip"
        with zipfile.ZipFile(archive, "r") as source, zipfile.ZipFile(corrupt, "w") as dest:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "application.sqlite":
                    data += b"corrupt"
                dest.writestr(info, data)
        with self.assertRaises(BackupError) as corrupt_error:
            self.service.restore_backup(
                BackupRestoreRequest(
                    archive_path=str(corrupt),
                    destination_root=str(self.root.parent / "restore-corrupt"),
                )
            )
        self.assertEqual(corrupt_error.exception.code, "backup_integrity_mismatch")

    def test_restore_rejects_corrupted_application_linkages(self) -> None:
        self.put_conversation("chat_valid")
        archive = self.root.parent / "backup.zip"
        self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        broken = self.root.parent / "broken-linkage.zip"
        _rewrite_archive_application_db(
            archive,
            broken,
            self.root.parent / "rewrite-linkage",
            "INSERT INTO run_checkpoints(run_id, checkpoint_id, thread_id, recorded_at) VALUES ('missing_run', 'cp', 'thread', 'now')",
        )

        with self.assertRaises(BackupError) as linkage:
            self.service.restore_backup(
                BackupRestoreRequest(
                    archive_path=str(broken),
                    destination_root=str(self.root.parent / "restore-linkage"),
                )
            )
        self.assertEqual(linkage.exception.code, "application_linkage_invalid")

    def test_restore_does_not_delete_preexisting_destination_on_failure(self) -> None:
        archive = self.root.parent / "backup.zip"
        self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        destination = self.root.parent / "restore-owned"
        destination.mkdir()
        marker = destination / "marker.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(BackupError):
            self.service.restore_backup(
                BackupRestoreRequest(archive_path=str(archive), destination_root=str(destination))
            )
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_checkpointer_backup_helper_accepts_missing_checkpoint_file(self) -> None:
        dest = self.root.parent / "copy.sqlite"
        copy_checkpoints_for_backup(self.paths.checkpoints_db, dest)
        self.assertFalse(dest.exists())

def _rewrite_archive_application_db(source_archive: Path, destination_archive: Path, workdir: Path, sql: str) -> None:
    if workdir.exists():
        raise AssertionError(f"Fixture rewrite directory already exists: {workdir}")
    workdir.mkdir()
    with zipfile.ZipFile(source_archive, "r") as zf:
        zf.extractall(workdir)
    conn = sqlite3.connect(str(workdir / "application.sqlite"))
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()
    manifest_path = workdir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = workdir / item["path"]
        item["size_bytes"] = path.stat().st_size
        item["sha256"] = sha256_file(path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(destination_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(workdir.rglob("*"), key=lambda item: item.as_posix()):
            relative = path.relative_to(workdir).as_posix()
            if path.is_dir():
                if not any(path.iterdir()):
                    zf.writestr(f"{relative}/", b"")
                continue
            zf.write(path, relative)


if __name__ == "__main__":
    unittest.main()
