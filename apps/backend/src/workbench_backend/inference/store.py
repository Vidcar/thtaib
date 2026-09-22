"""JSON record store under the managed state directory."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter

from workbench_backend.inference.schemas import (
    Deployment,
    ImportJob,
    ModelBundle,
    RunProfile,
    RuntimeManifest,
)
from workbench_backend.paths import WorkbenchPaths

T = TypeVar("T", bound=BaseModel)
_STORE_LOCK = RLock()
_IMPORT_JOB_SCHEMA = """
CREATE TABLE IF NOT EXISTS import_jobs (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_evidence (
    id TEXT PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    tested_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class RecordStore:
    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.bundles_path = self.paths.state / "bundles.json"
        self.jobs_path = self.paths.state / "import_jobs.json"
        self.profiles_path = self.paths.state / "profiles.json"
        self.deployments_path = self.paths.state / "deployments.json"
        self.runtime_manifest_path = self.paths.runtimes / "runtime-manifest.json"
        self.application_db = self.paths.application_db
        self._ensure_import_job_table()
        self._migrate_json_jobs()

    def list_bundles(self) -> list[ModelBundle]:
        return self._read_list(self.bundles_path, ModelBundle)

    def put_bundle(self, bundle: ModelBundle) -> ModelBundle:
        return self._upsert(self.bundles_path, ModelBundle, bundle)

    def get_bundle(self, bundle_id: str) -> ModelBundle | None:
        return next((item for item in self.list_bundles() if item.id == bundle_id), None)

    def delete_bundle(self, bundle_id: str) -> None:
        with _STORE_LOCK:
            remaining = [item for item in self.list_bundles() if item.id != bundle_id]
            self._write_list(self.bundles_path, remaining)
            with closing(self._connect()) as conn:
                conn.execute("DELETE FROM app_settings WHERE key IN (?, ?, ?)",
                    (f"model-verification:{bundle_id}", f"model-inspection:{bundle_id}:runtime", f"model-inspection:{bundle_id}:full"))
                conn.commit()

    def set_bundle_disk_matches(self, bundle_id: str, matches: bool) -> ModelBundle | None:
        """Verification may finish after deletion; never recreate that record."""
        with _STORE_LOCK:
            bundle = self.get_bundle(bundle_id)
            if bundle is None:
                return None
            updated = bundle.model_copy(update={"disk_matches": matches})
            return self.put_bundle(updated) if updated != bundle else bundle

    def list_jobs(self) -> list[ImportJob]:
        with _STORE_LOCK, closing(self._connect()) as conn:
            rows = conn.execute("SELECT payload FROM import_jobs ORDER BY created_at, id").fetchall()
        return [ImportJob.model_validate_json(str(row["payload"])) for row in rows]

    def put_job(self, job: ImportJob) -> ImportJob:
        job = job.model_copy(update={"updated_at": getattr(job, "updated_at", None) or getattr(job, "created_at")})
        with _STORE_LOCK, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO import_jobs(id, payload, status, kind, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    status=excluded.status,
                    kind=excluded.kind,
                    updated_at=excluded.updated_at
                """,
                (
                    job.id,
                    job.model_dump_json(),
                    job.status.value,
                    job.kind.value,
                    job.created_at,
                    job.updated_at or job.created_at,
                ),
            )
            conn.commit()
        return job

    def get_job(self, job_id: str) -> ImportJob | None:
        with _STORE_LOCK, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload FROM import_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return ImportJob.model_validate_json(str(row["payload"]))

    def delete_job(self, job_id: str) -> None:
        with _STORE_LOCK, closing(self._connect()) as conn:
            conn.execute("DELETE FROM import_jobs WHERE id = ?", (job_id,))
            conn.commit()

    def update_job_fields(self, job_id: str, **fields) -> ImportJob:
        with _STORE_LOCK:
            current = self.get_job(job_id)
            if current is None:
                raise KeyError(job_id)
            return self.put_job(current.model_copy(update=fields))

    def list_active_jobs(self) -> list[ImportJob]:
        active = {"pending", "running", "stopping"}
        with _STORE_LOCK, closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT payload FROM import_jobs WHERE status IN ({','.join('?' for _ in active)}) ORDER BY created_at, id",
                tuple(sorted(active)),
            ).fetchall()
        return [ImportJob.model_validate_json(str(row["payload"])) for row in rows]

    def get_setting(self, key: str) -> str | None:
        with _STORE_LOCK, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])

    def put_setting(self, key: str, value: str) -> None:
        from workbench_backend.inference.ids import utc_now

        with _STORE_LOCK, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, utc_now()),
            )
            conn.commit()

    def list_profiles(self) -> list[RunProfile]:
        return self._read_list(self.profiles_path, RunProfile)

    def put_profile(self, profile: RunProfile) -> RunProfile:
        return self._upsert(self.profiles_path, RunProfile, profile)

    def get_profile(self, profile_id: str) -> RunProfile | None:
        return next((item for item in self.list_profiles() if item.id == profile_id), None)

    def delete_profile(self, profile_id: str) -> None:
        with _STORE_LOCK:
            remaining = [item for item in self.list_profiles() if item.id != profile_id]
            self._write_list(self.profiles_path, remaining)

    def list_deployments(self) -> list[Deployment]:
        deployments = self._read_list(self.deployments_path, Deployment)
        bundles = {bundle.id: bundle for bundle in self.list_bundles()}
        runtime = self.read_runtime_manifest()
        for deployment in deployments:
            deployment.capability_evidence = self.list_capability_evidence(deployment.id)
            bundle = bundles.get(deployment.bundle_id)
            deployment.inference_identity = {
                "runtime": ({"release": runtime.release_tag, "executable": runtime.executable, "sha256": runtime.sha256,
                             "companion_sha256": runtime.companion_sha256} if runtime and deployment.scope.value == "managed" else None),
                "bundle_files": ([{"path": item.path, "sha256": item.sha256, "role": item.role.value}
                                  for item in [*bundle.files, *bundle.shards, *bundle.companions]] if bundle else []),
            }
            if deployment.inference_identity == {"runtime": None, "bundle_files": []}:
                deployment.inference_identity = {}
        return deployments

    def put_deployment(self, deployment: Deployment) -> Deployment:
        self._upsert(self.deployments_path, Deployment, deployment.model_copy(update={"capability_evidence": [], "inference_identity": {}}))
        return self.get_deployment(deployment.id) or deployment

    def put_capability_evidence(self, evidence: dict[str, Any]) -> None:
        with _STORE_LOCK, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO capability_evidence(id, deployment_id, tested_at, payload) VALUES (?, ?, ?, ?)",
                (evidence["id"], evidence["deployment_id"], evidence["tested_at"], json.dumps(evidence)),
            )
            conn.commit()

    def list_capability_evidence(self, deployment_id: str) -> list[dict[str, Any]]:
        with _STORE_LOCK, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM capability_evidence WHERE deployment_id = ? ORDER BY tested_at, rowid",
                (deployment_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        return next(
            (item for item in self.list_deployments() if item.id == deployment_id),
            None,
        )

    def delete_deployment(self, deployment_id: str) -> None:
        with _STORE_LOCK:
            remaining = [item for item in self.list_deployments() if item.id != deployment_id]
            self._write_list(self.deployments_path, remaining)

    def read_runtime_manifest(self) -> RuntimeManifest | None:
        if not self.runtime_manifest_path.is_file():
            return None
        return RuntimeManifest.model_validate_json(
            self.runtime_manifest_path.read_text(encoding="utf-8")
        )

    def write_runtime_manifest(self, manifest: RuntimeManifest) -> RuntimeManifest:
        self._write_json(self.runtime_manifest_path, manifest.model_dump(mode="json"))
        return manifest

    def _read_list(self, path: Path, model: type[T]) -> list[T]:
        with _STORE_LOCK:
            if not path.is_file():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
            return TypeAdapter(list[model]).validate_python(raw)

    def _write_list(self, path: Path, items: list[BaseModel]) -> None:
        self._write_json(path, [item.model_dump(mode="json") for item in items])

    def _upsert(self, path: Path, model: type[T], item: T) -> T:
        with _STORE_LOCK:
            items = self._read_list(path, model)
            replaced = False
            next_items: list[T] = []
            for existing in items:
                if getattr(existing, "id") == getattr(item, "id"):
                    next_items.append(item)
                    replaced = True
                else:
                    next_items.append(existing)
            if not replaced:
                next_items.append(item)
            self._write_list(path, next_items)
        return item

    def _write_json(self, path: Path, payload: Any) -> None:
        with _STORE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
            try:
                tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.application_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_import_job_table(self) -> None:
        with _STORE_LOCK, closing(self._connect()) as conn:
            conn.executescript(_IMPORT_JOB_SCHEMA)
            conn.commit()

    def _migrate_json_jobs(self) -> None:
        if not self.jobs_path.is_file():
            return
        try:
            legacy = self._read_list(self.jobs_path, ImportJob)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        for job in legacy:
            if self.get_job(job.id) is None:
                self.put_job(job)
