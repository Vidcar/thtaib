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
from workbench_backend.inference.schemas import RuntimeManifest, ModelBundle, BundleFile, BundleSource
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.store import RecordStore
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

    def test_connection_versions_restore_without_credential_values(self) -> None:
        from workbench_backend.connections.service import ConnectionService
        from workbench_backend.connections.schemas import ConnectionWrite
        from tests.test_connections import MemoryVault
        connections = ConnectionService(self.store, vault=MemoryVault())
        record = connections.create(ConnectionWrite(name="Private docs", kind="mcp", transport="http", url="https://example.test/mcp"))
        saved = connections.replace_credential(record.id, "backup-must-never-contain-this-secret")
        archive = self.root.parent / "connections.zip"
        created = self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        self.assertTrue(any(ref.id == saved.credential_ref and ref.kind == "credential" and ref.missing for ref in created.manifest.external_references))
        with zipfile.ZipFile(archive) as bundle:
            self.assertFalse(any(b"backup-must-never-contain-this-secret" in bundle.read(name) for name in bundle.namelist() if not name.endswith("/")))
        target = self.root.parent / "restored-connections"
        restored = self.service.restore_backup(BackupRestoreRequest(archive_path=str(archive), destination_root=str(target)))
        self.assertTrue(any(ref.id == saved.credential_ref for ref in restored.missing_dependencies))
        restored_store = ApplicationStore(WorkbenchPaths(target))
        try:
            reopened = ConnectionService(restored_store, vault=MemoryVault()).get(saved.id)
            self.assertEqual(reopened.version, saved.version)
            self.assertEqual(reopened.credential_ref, saved.credential_ref)
            self.assertFalse(reopened.credential_present)
        finally:
            restored_store.close()

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

    def test_restore_reports_missing_bundle_files_without_deployment_history(self) -> None:
        primary = self.root.parent / "weights" / "model.gguf"
        primary.parent.mkdir()
        primary.write_bytes(b"primary weights")
        shard = self.root.parent / "weights" / "model-00002-of-00002.gguf"
        shard.mkdir()
        companion = self.root.parent / "weights" / "mmproj.gguf"
        bundle = {
            "id": "bundle-never-run",
            "display_name": "Never run bundle",
            "format": "gguf",
            "quantization": None,
            "source": {
                "kind": "local",
                "repo_id": None,
                "requested_revision": None,
                "resolved_revision": None,
                "original_path": str(primary),
            },
            "files": [
                {
                    "role": "primary_weights",
                    "name": primary.name,
                    "path": str(primary),
                    "sha256": "primary",
                    "size_bytes": primary.stat().st_size,
                    "ownership": "external",
                }
            ],
            "shards": [
                {
                    "role": "shard",
                    "name": shard.name,
                    "path": str(shard),
                    "sha256": "shard",
                    "size_bytes": 10,
                    "ownership": "external",
                }
            ],
            "companions": [
                {
                    "role": "companion",
                    "name": companion.name,
                    "path": str(companion),
                    "sha256": "companion",
                    "size_bytes": 11,
                    "ownership": "external",
                }
            ],
            "primary_path": str(primary),
            "managed_root": None,
            "created_at": utc_now(),
            "status": "complete",
            "disk_matches": True,
        }
        (self.paths.state / "bundles.json").write_text(json.dumps([{"id": "corrupt-record"}, bundle]), encoding="utf-8")

        archive = self.root.parent / "bundle-refs.zip"
        result = self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        model_refs = sorted(
            ref.path for ref in result.manifest.external_references if ref.kind == "model" and ref.path
        )

        self.assertEqual(model_refs, sorted([str(primary), str(shard), str(companion)]))
        self.assertEqual(len([ref for ref in result.manifest.external_references if ref.kind == "model"]), 3)
        with zipfile.ZipFile(archive, "r") as zf:
            names = set(zf.namelist())
        self.assertNotIn("weights/model.gguf", names)
        self.assertNotIn("weights/model-00002-of-00002.gguf", names)
        self.assertNotIn("weights/mmproj.gguf", names)

        restore_root = self.root.parent / "bundle-refs-restore"
        restored = self.service.restore_backup(
            BackupRestoreRequest(archive_path=str(archive), destination_root=str(restore_root))
        )

        missing_model_paths = sorted(
            ref.path for ref in restored.missing_dependencies if ref.kind == "model" and ref.path
        )
        self.assertEqual(missing_model_paths, sorted([str(shard), str(companion)]))

    def test_restore_reports_missing_runtime_files_without_copying_runtime_or_credentials(self) -> None:
        install_dir = self.root.parent / "runtime-install"
        install_dir.mkdir()
        executable = install_dir / "llama-server.exe"
        executable.write_bytes(b"runtime binary")
        # RuntimeManager retains downloaded release archives next to the
        # manifest, while extracted binaries live in a separate install folder.
        archive_asset = self.paths.runtimes / "llama-b11045.zip"
        archive_asset.write_bytes(b"downloaded release")
        companion_asset = self.paths.runtimes / "cudart64_134.zip"
        manifest = RuntimeManifest(
            platform="windows",
            flavor="cuda-13.4",
            release_tag="b11045",
            source_url="https://example.invalid/llama-b11045.zip",
            asset_name=archive_asset.name,
            sha256="archive",
            install_dir=str(install_dir),
            executable=str(executable),
            companion_asset_name=companion_asset.name,
            companion_sha256="companion",
        )
        (self.paths.runtimes / "runtime-manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
        (self.paths.state / "desktop_backend_shared_secret").write_text("secret", encoding="utf-8")

        archive = self.root.parent / "runtime-refs.zip"
        result = self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        runtime_refs = sorted(
            ref.path
            for ref in result.manifest.external_references
            if ref.kind == "runtime" and ref.path and not ref.path.endswith("runtime-manifest.json")
        )

        self.assertEqual(runtime_refs, sorted([str(executable), str(archive_asset), str(companion_asset)]))
        with zipfile.ZipFile(archive, "r") as zf:
            names = set(zf.namelist())
        self.assertIn("runtimes/runtime-manifest.json", names)
        self.assertNotIn("runtimes/desktop_backend_shared_secret", names)
        self.assertNotIn("runtime-install/llama-server.exe", names)
        self.assertNotIn("runtime-install/llama-b11045.zip", names)
        self.assertNotIn("runtime-install/cudart64_134.zip", names)

        restore_root = self.root.parent / "runtime-refs-restore"
        restored = self.service.restore_backup(
            BackupRestoreRequest(archive_path=str(archive), destination_root=str(restore_root))
        )

        missing_runtime_paths = sorted(
            ref.path for ref in restored.missing_dependencies if ref.kind == "runtime" and ref.path
        )
        self.assertEqual(missing_runtime_paths, [str(companion_asset)])

    def test_restored_models_verify_as_external_references_to_preserved_weights(self) -> None:
        weights = self.paths.models / "model.gguf"
        weights.write_bytes(b"preserved model bytes")
        bundle = ModelBundle(id="bundle_restore", display_name="Restore model",
            source=BundleSource(kind="local", original_path=str(weights)),
            files=[BundleFile(role="primary_weights", name=weights.name, path=str(weights),
                sha256=sha256_file(weights), size_bytes=weights.stat().st_size, ownership="managed")],
            primary_path=str(weights), created_at=utc_now())
        RecordStore(self.paths).put_bundle(bundle)
        archive = self.root.parent / "model-ownership.zip"
        self.service.create_backup(BackupCreateRequest(destination=str(archive)))
        destination = self.root.parent / "model-ownership-restore"
        self.service.restore_backup(BackupRestoreRequest(archive_path=str(archive), destination_root=str(destination)))
        restored_paths = WorkbenchPaths(destination)
        records = RecordStore(restored_paths)
        restored = records.get_bundle(bundle.id)
        verified = BundleService(restored_paths, records).verify_bundle(restored)
        self.assertTrue(verified.disk_matches, "existing weights must verify from the restored root")
        self.assertTrue(all(item.ownership == "external" for item in verified.files))
        self.assertEqual(verified.primary_path, str(weights))
        self.assertIsNone(verified.managed_root)
        self.assertEqual(weights.read_bytes(), b"preserved model bytes")
        self.assertEqual(RecordStore(self.paths).get_bundle(bundle.id).files[0].ownership, "managed")

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
